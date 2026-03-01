"""
demo.py — Mac desktop demo for Neuro-Sync.

Replaces the Raspberry Pi hardware with a live OpenCV window.
Uses your Mac's built-in camera + microphone, and the local server.

Usage:
    1. Start the server:   cd server && python main.py
    2. Run the demo:       python demo.py

Press 'q' to quit.
"""

import json
import time
import threading
import logging
import sys
import statistics
import os
import io
import wave
from datetime import datetime
from pathlib import Path

import cv2
import httpx
import numpy as np
import sounddevice as sd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("neuro-sync.demo")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SERVER_URL = "http://localhost:8000"
SESSION_ID = "demo_mac"
WINDOW_NAME = "Neuro-Sync Demo"

# Colors (BGR for OpenCV)
COLORS = {
    "GOOD":         (80, 220, 0),     # Green
    "SPEED_UP":     (0, 30, 255),     # Red
    "VIBE_CHECK":   (0, 120, 255),    # Orange
    "RAISE_ENERGY": (0, 30, 255),     # Red
    "VISUAL_RESET": (255, 150, 0),    # Blue
    "IDLE":         (120, 120, 120),  # Gray
    "ERROR":        (200, 0, 255),    # Magenta
    "HOOK_GOOD":    (0, 200, 200),    # Yellow-gold
    "HOOK_WEAK":    (0, 80, 200),     # Dark orange
}

# Audio config
SAMPLE_RATE = 16000       # Hz
AUDIO_WINDOW_SEC = 1.5    # seconds of audio to analyze per cycle
SILENCE_THRESHOLD = 0.02  # normalized amplitude below this = silence
BURST_ON = 0.04           # amplitude above this = start of speech burst
BURST_OFF = 0.025         # amplitude below this = end of speech burst


# ─────────────────────────────────────────────
# REAL MICROPHONE AUDIO
# ─────────────────────────────────────────────

class MicCapture:
    """Continuously captures audio from the Mac microphone in a ring buffer."""

    def __init__(self, sample_rate=SAMPLE_RATE, window_sec=AUDIO_WINDOW_SEC):
        self.sample_rate = sample_rate
        self.window_sec = window_sec
        self.buffer_size = int(sample_rate * window_sec)
        self._buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self._lock = threading.Lock()
        self._stream = None

    def start(self):
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=self._callback,
        )
        self._stream.start()
        logger.info(f"Microphone started (rate={self.sample_rate}Hz, window={self.window_sec}s)")

    def _callback(self, indata, frames, time_info, status):
        mono = indata[:, 0]
        with self._lock:
            # Shift buffer left and append new samples
            n = len(mono)
            if n >= self.buffer_size:
                self._buffer[:] = mono[-self.buffer_size:]
            else:
                self._buffer[:-n] = self._buffer[n:]
                self._buffer[-n:] = mono

    def get_metrics(self) -> dict:
        with self._lock:
            samples = self._buffer.copy()

        # Take absolute values for amplitude analysis
        amp = np.abs(samples)

        # RMS
        rms = float(np.sqrt(np.mean(samples ** 2)))
        # Normalize to 0-1 range (mic typically peaks around 0.3-0.5)
        rms_normalized = min(1.0, rms * 3.0)

        # Peak
        peak = float(np.max(amp))
        peak_normalized = min(1.0, peak * 2.0)

        # Silence ratio
        silent_samples = np.sum(amp < SILENCE_THRESHOLD)
        silence_ratio = float(silent_samples / len(amp))

        # Volume variance (expressiveness)
        # Compute on windowed chunks to get meaningful variance
        chunk_size = self.sample_rate // 10  # 100ms chunks
        chunk_rms = []
        for i in range(0, len(samples) - chunk_size, chunk_size):
            chunk = samples[i:i + chunk_size]
            chunk_rms.append(float(np.sqrt(np.mean(chunk ** 2))))
        variance = statistics.variance(chunk_rms) if len(chunk_rms) > 1 else 0.0

        # WPM estimation from speech bursts
        burst_count = 0
        in_burst = False
        for a in amp:
            if not in_burst and a >= BURST_ON:
                burst_count += 1
                in_burst = True
            elif in_burst and a < BURST_OFF:
                in_burst = False

        # Each burst ~ 1 syllable group, ~1.5 syllables/word
        if burst_count > 0:
            bursts_per_sec = burst_count / self.window_sec
            wpm = int((bursts_per_sec / 1.5) * 60)
        else:
            wpm = 0
        wpm = max(0, min(350, wpm))

        return {
            "volume_rms": round(rms_normalized, 4),
            "silence_ratio": round(silence_ratio, 4),
            "estimated_wpm": wpm,
            "peak_volume": round(peak_normalized, 4),
            "volume_variance": round(variance, 6),
        }

    def get_wav_bytes(self) -> bytes:
        """Return the current audio buffer as WAV bytes for sending to Gemini."""
        with self._lock:
            samples = self._buffer.copy()
        # Convert float32 [-1,1] to int16 PCM
        pcm = (samples * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()


# ─────────────────────────────────────────────
# OVERLAY DRAWING
# ─────────────────────────────────────────────

def draw_overlay(frame, event_data, latency_ms, audio_metrics=None):
    """Draw the coaching HUD on the camera frame."""
    h, w = frame.shape[:2]
    overlay = frame.copy()

    event_type = event_data.get("event", "IDLE")
    score = float(event_data.get("score", 0.0))
    message = event_data.get("message", "")
    reasoning = event_data.get("reasoning", "")
    buzz = event_data.get("buzz", False)
    color = COLORS.get(event_type, COLORS["IDLE"])

    # Top banner
    banner_h = 70
    cv2.rectangle(overlay, (0, 0), (w, banner_h), color, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    # Event type label
    cv2.putText(frame, event_type, (16, 44),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)

    # Score on right side of banner
    score_text = f"{int(score * 100)}%"
    (tw, _), _ = cv2.getTextSize(score_text, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
    cv2.putText(frame, score_text, (w - tw - 16, 44),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)

    # Phase indicator (hook mode)
    phase = event_data.get("phase", "normal")
    if phase == "hook":
        phase_label = "HOOK EVAL"
        (pw, _), _ = cv2.getTextSize(phase_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        phase_x = (w - pw) // 2
        cv2.putText(frame, phase_label, (phase_x, banner_h + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA)

    # Buzz indicator
    if buzz:
        cv2.putText(frame, "BUZZ", (w - 80, banner_h + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)

    # Score bar at bottom
    bar_y = h - 50
    bar_x = 16
    bar_w = w - 32
    bar_h = 24
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  (40, 40, 40), -1)
    filled_w = int(bar_w * score)
    if filled_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + filled_w, bar_y + bar_h),
                      color, -1)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  (200, 200, 200), 1)

    # Message box
    if message:
        msg_y = h - 90
        cv2.rectangle(frame, (12, msg_y - 28), (w - 12, msg_y + 8),
                      (0, 0, 0), -1)
        cv2.rectangle(frame, (12, msg_y - 28), (w - 12, msg_y + 8),
                      color, 2)
        cv2.putText(frame, message, (20, msg_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)

    # Reasoning text
    if reasoning:
        max_chars = w // 9
        if len(reasoning) > max_chars:
            reasoning = reasoning[:max_chars - 3] + "..."
        cv2.putText(frame, reasoning, (16, banner_h + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    # Audio meters (bottom-left)
    if audio_metrics:
        ay = h - 8
        vol = audio_metrics.get("volume_rms", 0)
        wpm = audio_metrics.get("estimated_wpm", 0)
        cv2.putText(frame, f"VOL:{vol:.2f} WPM:{wpm}", (16, ay),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1, cv2.LINE_AA)

    # Latency indicator
    lat_text = f"{int(latency_ms)}ms"
    cv2.putText(frame, lat_text, (w - 70, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1, cv2.LINE_AA)

    # Border glow
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), color, 3)

    return frame


def draw_status(frame, text):
    """Draw a simple centered status message."""
    h, w = frame.shape[:2]
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
    x = (w - tw) // 2
    y = (h + th) // 2
    cv2.rectangle(frame, (x - 10, y - th - 10), (x + tw + 10, y + 10), (0, 0, 0), -1)
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def draw_countdown(frame, text, color=(0, 200, 255)):
    """Draw a large centered countdown number/text with darkened background."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    font_scale = 4.0
    thickness = 8
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    x = (w - tw) // 2
    y = (h + th) // 2
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)

    # Border
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), color, 4)
    return frame


# ─────────────────────────────────────────────
# ANALYSIS THREAD
# ─────────────────────────────────────────────

class Analyzer:
    """Runs server calls in a background thread so the camera stays smooth."""

    def __init__(self, mic: MicCapture):
        self.mic = mic
        self.latest_event = None
        self.latest_latency = 0.0
        self.latest_audio = None
        self.status = "Starting..."
        self.running = True
        self._frame_lock = threading.Lock()
        self._current_jpeg = None
        self._client = httpx.Client()
        # Create session frame dump directory
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._dump_dir = Path("sessions") / f"frames_{ts}"
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        self._call_count = 0
        logger.info(f"Saving frames to {self._dump_dir}/")

    def set_frame(self, jpeg_bytes: bytes):
        with self._frame_lock:
            self._current_jpeg = jpeg_bytes

    def _get_frame(self) -> bytes | None:
        with self._frame_lock:
            return self._current_jpeg

    def run(self):
        # Health check
        self.status = "Checking server..."
        try:
            resp = self._client.get(f"{SERVER_URL}/health", timeout=5.0)
            data = resp.json()
            if data.get("gemini_key") != "configured":
                self.status = "ERROR: Gemini key not set on server"
                logger.error("Server running but GEMINI_API_KEY not configured")
                return
            logger.info("Server healthy")
        except httpx.ConnectError:
            self.status = "ERROR: Server not running (start server/ first)"
            logger.error(f"Cannot connect to {SERVER_URL}")
            return
        except Exception as e:
            self.status = f"ERROR: {e}"
            return

        # Reset session
        try:
            self._client.delete(f"{SERVER_URL}/session/{SESSION_ID}", timeout=3.0)
        except Exception:
            pass

        self.status = "Ready - analyzing..."

        while self.running:
            jpeg = self._get_frame()
            if jpeg is None:
                time.sleep(0.1)
                continue

            audio = self.mic.get_metrics()
            audio_wav = self.mic.get_wav_bytes()
            self.latest_audio = audio
            self._call_count += 1
            call_num = self._call_count
            t_start = time.perf_counter()

            try:
                resp = self._client.post(
                    f"{SERVER_URL}/analyze",
                    files={
                        "frame": ("frame.jpg", jpeg, "image/jpeg"),
                        "audio_clip": ("audio.wav", audio_wav, "audio/wav"),
                    },
                    data={
                        "audio_metrics": json.dumps(audio),
                        "session_id": SESSION_ID,
                    },
                    timeout=12.0,
                )
                resp.raise_for_status()
                latency = (time.perf_counter() - t_start) * 1000

                event = resp.json()
                self.latest_event = event
                self.latest_latency = latency
                self.status = "Live"

                # Save frame + audio + metadata
                prefix = f"{call_num:04d}"
                frame_path = self._dump_dir / f"{prefix}.jpg"
                audio_path = self._dump_dir / f"{prefix}.wav"
                meta_path = self._dump_dir / f"{prefix}.json"
                frame_path.write_bytes(jpeg)
                audio_path.write_bytes(audio_wav)
                meta_path.write_text(json.dumps({
                    "call": call_num,
                    "timestamp": datetime.now().isoformat(),
                    "latency_ms": round(latency, 1),
                    "audio": audio,
                    "event": event,
                }, indent=2))

                logger.info(
                    f"{event.get('event', '?'):<14} "
                    f"score={event.get('score', 0):.2f}  "
                    f"{latency:.0f}ms  "
                    f"vol={audio['volume_rms']:.2f} wpm={audio['estimated_wpm']}  "
                    f"{event.get('message', '')}"
                )

            except Exception as e:
                logger.error(f"Analyze failed: {e}")
                self.status = f"Error: {type(e).__name__}"
                time.sleep(3.0)
            finally:
                # Min 2s between requests to stay within rate limits
                elapsed = time.perf_counter() - t_start
                remaining = 2.0 - elapsed
                if remaining > 0:
                    time.sleep(remaining)

    def stop(self):
        self.running = False
        self._client.close()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print()
    print("=" * 50)
    print("  NEURO-SYNC  Mac Demo")
    print("=" * 50)
    print(f"  Server: {SERVER_URL}")
    print(f"  Camera + Microphone (real audio)")
    print(f"  Press 'q' to quit")
    print("=" * 50)
    print()

    # Start mic capture
    mic = MicCapture()
    mic.start()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera. Check permissions.")
        print("  System Preferences > Privacy & Security > Camera")
        mic.stop()
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Warm up camera
    for _ in range(5):
        cap.read()

    # ── 3-2-1 Countdown ─────────────────────────────────────────────
    countdown_items = [("3", 1.0), ("2", 1.0), ("1", 1.0), ("GO!", 0.5)]
    for text, duration in countdown_items:
        color = (0, 255, 0) if text == "GO!" else (0, 200, 255)
        t_end = time.time() + duration
        while time.time() < t_end:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            frame = draw_countdown(frame, text, color)
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                mic.stop()
                cap.release()
                cv2.destroyAllWindows()
                return

    analyzer = Analyzer(mic)
    thread = threading.Thread(target=analyzer.run, daemon=True)
    thread.start()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.error("Camera read failed")
                break

            frame = cv2.flip(frame, 1)

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            analyzer.set_frame(buf.tobytes())

            if analyzer.latest_event:
                frame = draw_overlay(frame, analyzer.latest_event,
                                     analyzer.latest_latency, analyzer.latest_audio)
            else:
                frame = draw_status(frame, analyzer.status)

            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        analyzer.stop()
        mic.stop()
        cap.release()
        cv2.destroyAllWindows()

        # ── Fetch and save post-session report ───────────────────────
        print("\nFetching session report...")
        try:
            with httpx.Client() as c:
                resp = c.get(f"{SERVER_URL}/session/{SESSION_ID}/report", timeout=5.0)
                if resp.status_code == 200:
                    report = resp.json()
                    report_path = analyzer._dump_dir / "report.json"
                    report_path.write_text(json.dumps(report, indent=2))
                    print(f"Report saved to {report_path}")

                    # Print summary to terminal
                    print()
                    print("=" * 50)
                    print("  SESSION REPORT")
                    print("=" * 50)

                    # Hook evaluation
                    hook = report.get("hook_evaluation")
                    if hook:
                        print(f"\n  Hook Verdict: {hook['verdict']}")
                        print(f"  Hook Avg Score: {hook['avg_score']:.1%}")
                        for ev in hook.get("evaluations", []):
                            print(f"    {ev['event']}: {ev['score']:.1%} — {ev.get('reasoning', '')}")

                    # Stats
                    stats = report.get("stats", {})
                    print(f"\n  Total Events: {stats.get('total_events', 0)}")
                    print(f"  Avg Score: {stats.get('avg_score', 0):.1%}")
                    print(f"  Min/Max: {stats.get('min_score', 0):.1%} / {stats.get('max_score', 0):.1%}")
                    counts = stats.get("event_counts", {})
                    if counts:
                        print(f"  Events: {counts}")

                    # Best/worst
                    best = report.get("best_moment", {})
                    worst = report.get("worst_moment", {})
                    if best:
                        print(f"\n  Best:  frame #{best.get('frame_index', '?')} — {best.get('event', '')} {best.get('score', 0):.1%}")
                    if worst:
                        print(f"  Worst: frame #{worst.get('frame_index', '?')} — {worst.get('event', '')} {worst.get('score', 0):.1%}")

                    # Problem zones
                    zones = report.get("problem_zones", [])
                    if zones:
                        print(f"\n  Problem Zones ({len(zones)}):")
                        for z in zones:
                            print(f"    Frames {z['start_frame']}-{z['end_frame']} ({z['length']} frames, avg {z['avg_score']:.1%})")

                    print()
                    print("=" * 50)
                else:
                    print(f"Could not fetch report (HTTP {resp.status_code})")
        except Exception as e:
            print(f"Report fetch failed: {e}")

        print("\nDemo stopped.")


if __name__ == "__main__":
    main()
