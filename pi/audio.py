"""
pi/audio.py — Sound sensor signal processing for Neuro-Sync Pi client.

Reads the Grove Sound Sensor on port A0 of the Grove Base HAT.
Samples for a configurable window, then computes:

  volume_rms      — overall loudness (root mean square)
  silence_ratio   — fraction of time the creator wasn't speaking
  estimated_wpm   — rough words-per-minute from syllable burst detection
  peak_volume     — loudest single spike in the window
  volume_variance — how much the volume varied (high = expressive, low = monotone)

These five numbers get bundled into an AudioMetrics object and sent to
the laptop server alongside the camera frame on every analysis cycle.

Why compute these locally on the Pi instead of sending raw audio?
  1. Raw audio would be megabytes per request — too slow over WiFi.
  2. These five numbers are ~100 bytes of JSON — fast.
  3. The Grove sound sensor outputs a simple analog value (0-1023),
     not a PCM audio stream, so we can't do FFT pitch analysis anyway.
     Gemini handles the visual pitch/energy analysis from the face.

Grove Sound Sensor — port A0 on the Base HAT.
Sampling rate: 50 readings/second (one every 20ms).
"""

import logging
import time
import statistics
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SAMPLE_WINDOW_SEC  = 2.0    # How many seconds to sample before computing metrics
SAMPLE_RATE_HZ     = 50     # Readings per second from the sound sensor
SILENCE_THRESHOLD  = 0.045  # Below this normalized value = silence (tune per environment)
BURST_ON_THRESHOLD = 0.10   # Above this = start of a speech burst (syllable group)
BURST_OFF_THRESHOLD= 0.07   # Below this = end of a speech burst
SENSOR_PORT        = 0      # A0 on the Grove Base HAT


# ─────────────────────────────────────────────
# GROVE SENSOR IMPORT WITH FALLBACK
# If running on the Pi, import the real Grove library.
# If running on a laptop for testing, use a mock that
# generates sine-wave fake audio so you can test without hardware.
# ─────────────────────────────────────────────

try:
    from grove.grove_sound_sensor import GroveSoundSensor
    _sensor = GroveSoundSensor(SENSOR_PORT)
    IS_MOCK = False
    logger.info(f"Grove Sound Sensor initialized on port A{SENSOR_PORT}")
except ImportError:
    logger.warning("grove library not found — using mock sound sensor for testing")
    IS_MOCK = True
    _sensor = None

except Exception as e:
    logger.error(f"Failed to initialize Grove Sound Sensor: {e}")
    IS_MOCK = True
    _sensor = None


# ─────────────────────────────────────────────
# MOCK SENSOR
# Generates fake but realistic audio data for testing on a laptop.
# Simulates someone talking — alternating bursts and silences.
# ─────────────────────────────────────────────

class MockSoundSensor:
    """Generates fake sound sensor readings for laptop testing."""

    def __init__(self):
        self._t = 0.0

    @property
    def sound(self) -> int:
        """
        Returns a value in range 0-1023 that mimics natural speech patterns.
        Uses a combination of sine waves + noise to fake syllable bursts.
        """
        import math, random
        self._t += 0.02

        # Slow "breathing" cycle — simulates speech rhythm at ~100 WPM
        speech_cycle = (math.sin(self._t * 6.0) + 1) / 2   # 0.0 to 1.0, ~3Hz
        is_speaking  = speech_cycle > 0.3                    # ~70% speaking, 30% silence

        if is_speaking:
            base   = 0.35 + (speech_cycle * 0.4)
            noise  = random.gauss(0, 0.06)
            value  = max(0.0, min(1.0, base + noise))
        else:
            noise  = random.gauss(0, 0.02)
            value  = max(0.0, abs(noise))

        return int(value * 1023)

_mock_sensor = MockSoundSensor()


# ─────────────────────────────────────────────
# RAW SAMPLING
# ─────────────────────────────────────────────

def _read_raw() -> int:
    """Read one raw value from the sensor (0-1023)."""
    if IS_MOCK or _sensor is None:
        return _mock_sensor.sound
    return _sensor.sound

def _sample_window(duration_sec: float = SAMPLE_WINDOW_SEC) -> list[float]:
    """
    Sample the sensor for `duration_sec` seconds at SAMPLE_RATE_HZ.
    Returns a list of normalized floats (0.0 to 1.0).
    
    Uses precise timing to maintain consistent sample rate despite
    slight variations in the time each read takes.
    """
    n_samples    = int(duration_sec * SAMPLE_RATE_HZ)
    interval_sec = 1.0 / SAMPLE_RATE_HZ
    samples      = []

    t_next = time.monotonic()

    for _ in range(n_samples):
        raw = _read_raw()
        samples.append(raw / 1023.0)

        t_next += interval_sec
        sleep_for = t_next - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    return samples


# ─────────────────────────────────────────────
# SIGNAL PROCESSING
# ─────────────────────────────────────────────

def _compute_rms(samples: list[float]) -> float:
    """Root mean square — the standard measure of signal power/loudness."""
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return mean_sq ** 0.5

def _compute_silence_ratio(samples: list[float]) -> float:
    """Fraction of samples below the silence threshold."""
    if not samples:
        return 1.0
    silent = sum(1 for s in samples if s < SILENCE_THRESHOLD)
    return silent / len(samples)

def _compute_peak(samples: list[float]) -> float:
    """Highest single sample value."""
    return max(samples) if samples else 0.0

def _compute_variance(samples: list[float]) -> float:
    """
    Statistical variance of the sample window.
    High variance = creator is being expressive (volume changing a lot).
    Low variance = flat, monotone delivery.
    """
    if len(samples) < 2:
        return 0.0
    try:
        return statistics.variance(samples)
    except statistics.StatisticsError:
        return 0.0

def _estimate_wpm(samples: list[float], window_sec: float) -> int:
    """
    Estimates words per minute by counting speech bursts.

    Algorithm:
      1. Scan the normalized samples for transitions above BURST_ON_THRESHOLD
         (start of a syllable group) and below BURST_OFF_THRESHOLD (end).
      2. Each on→off transition = one burst ≈ one stressed syllable group.
      3. Average English speech has ~1.5 syllables per word.
      4. Extrapolate from the sample window duration to a per-minute rate.

    This is a rough estimate, not transcription-level accuracy.
    It's good enough to distinguish "rambling slowly" from "talking normally"
    from "rushing through content too fast."

    Minimum meaningful window: 1.5 seconds.
    """
    if window_sec < 1.0:
        return 0

    burst_count = 0
    in_burst    = False

    for s in samples:
        if not in_burst and s >= BURST_ON_THRESHOLD:
            burst_count += 1
            in_burst = True
        elif in_burst and s < BURST_OFF_THRESHOLD:
            in_burst = False

    if burst_count == 0:
        return 0

    # Bursts per second → extrapolate to WPM
    bursts_per_sec  = burst_count / window_sec
    syllables_per_sec = bursts_per_sec          # Each burst ~ a syllable group
    words_per_sec   = syllables_per_sec / 1.5   # ~1.5 syllables per word
    wpm             = int(words_per_sec * 60)

    # Clamp to a realistic range — sensor noise can produce nonsense values
    return max(0, min(350, wpm))


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def get_audio_metrics() -> dict:
    """
    Main function called by pi/main.py.

    Samples the sound sensor for SAMPLE_WINDOW_SEC seconds,
    computes all five signal metrics, and returns them as a dict
    matching the AudioMetrics schema expected by the server.

    This function is blocking — it takes SAMPLE_WINDOW_SEC seconds to return.
    That's intentional: the audio sampling window IS the loop timing.
    The Pi captures audio while the previous Gemini result is being displayed.

    Returns:
        dict with keys: volume_rms, silence_ratio, estimated_wpm,
                        peak_volume, volume_variance
    """
    samples = _sample_window(SAMPLE_WINDOW_SEC)

    rms      = round(_compute_rms(samples),              4)
    silence  = round(_compute_silence_ratio(samples),    4)
    peak     = round(_compute_peak(samples),             4)
    variance = round(_compute_variance(samples),         6)
    wpm      = _estimate_wpm(samples, SAMPLE_WINDOW_SEC)

    metrics = {
        "volume_rms":      rms,
        "silence_ratio":   silence,
        "estimated_wpm":   wpm,
        "peak_volume":     peak,
        "volume_variance": variance,
    }

    logger.debug(
        f"Audio: rms={rms:.3f}  silence={silence:.1%}  "
        f"wpm≈{wpm}  peak={peak:.3f}  var={variance:.5f}"
    )

    return metrics


# ─────────────────────────────────────────────
# QUICK TEST
# Run directly to verify sensor is reading:
#   python3 audio.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    mode = "MOCK (laptop)" if IS_MOCK else "LIVE (Grove sensor)"
    print(f"Testing audio metrics — mode: {mode}")
    print(f"Sampling for {SAMPLE_WINDOW_SEC}s... speak into the mic\n")

    for i in range(5):
        metrics = get_audio_metrics()
        bar_len = int(metrics["volume_rms"] * 30)
        bar     = "█" * bar_len + "░" * (30 - bar_len)
        print(
            f"  [{bar}] "
            f"rms={metrics['volume_rms']:.3f}  "
            f"silence={metrics['silence_ratio']:.0%}  "
            f"wpm≈{metrics['estimated_wpm']}  "
            f"peak={metrics['peak_volume']:.3f}"
        )
