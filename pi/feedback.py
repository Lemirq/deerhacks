"""
pi/feedback.py — Maps a CoachingEvent to physical hardware output.

Receives the CoachingEvent dict returned by the laptop server and:
  1. Drives the Grove Buzzer (port D16) with the correct pattern
  2. Updates the Grove LCD with the message + score bar
  3. Sets the LCD backlight color to match the event type

This is the final step in the pipeline — everything before this
was data collection and AI inference. This is where it becomes physical.

Buzzer patterns (each maps to a distinct, learnable sensation):
  SPEED_UP     → 3 short rapid beeps   (urgent, staccato)
  VIBE_CHECK   → 2 medium beeps        (attention, double-tap)
  RAISE_ENERGY → 1 long beep           (sustained warning)
  VISUAL_RESET → silent                (creator is talking, don't interrupt)
  GOOD         → silent                (no news is good news)

Grove Buzzer — port D16 on the Grove Base HAT.
GPIO pin 16 in BCM mode.
"""

import logging
import time
from typing import Optional

import RPi.GPIO as GPIO

from lcd import show as lcd_show, show_error as lcd_error

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

BUZZER_PIN = 16     # D16 port on Grove Base HAT → GPIO 16 BCM

# Buzz pattern timing (seconds)
PATTERNS = {
    "triple": {
        "count":  3,
        "on_ms":  80,
        "off_ms": 70,
    },
    "double": {
        "count":  2,
        "on_ms":  160,
        "off_ms": 120,
    },
    "long": {
        "count":  1,
        "on_ms":  450,
        "off_ms": 0,
    },
    "single": {
        "count":  1,
        "on_ms":  120,
        "off_ms": 0,
    },
}

# Maps each event to its default buzz pattern
# (can be overridden by buzz_pattern field in CoachingEvent)
EVENT_DEFAULT_PATTERNS = {
    "SPEED_UP":     "triple",
    "VIBE_CHECK":   "double",
    "RAISE_ENERGY": "long",
    "VISUAL_RESET": None,      # No buzz — creator is talking
    "GOOD":         None,      # No buzz — positive feedback is silent
}


# ─────────────────────────────────────────────
# GPIO SETUP WITH MOCK FALLBACK
# On the Pi: uses real RPi.GPIO.
# On a laptop: logs buzzer state to terminal.
# ─────────────────────────────────────────────

_gpio_available = False
_gpio_initialized = False

def _init_gpio():
    global _gpio_available, _gpio_initialized

    if _gpio_initialized:
        return

    # NO BUZZER HARDWARE — GPIO disabled.
    # To re-enable later, set _gpio_available = True and
    # uncomment the GPIO block below.
    _gpio_available = False
    _gpio_initialized = True
    logger.info("Buzzer disabled (no hardware) — LCD-only feedback mode.")

    # Uncomment to re-enable buzzer:
    # try:
    #     GPIO.setmode(GPIO.BCM)
    #     GPIO.setwarnings(False)
    #     GPIO.setup(BUZZER_PIN, GPIO.OUT)
    #     GPIO.output(BUZZER_PIN, GPIO.LOW)
    #     _gpio_available = True
    # except Exception as e:
    #     logger.warning(f"GPIO init failed: {e}")
    #     _gpio_available = False


def _buzzer_on():
    if _gpio_available:
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
    else:
        logger.debug("  [BUZZ ON]")

def _buzzer_off():
    if _gpio_available:
        GPIO.output(BUZZER_PIN, GPIO.LOW)
    else:
        logger.debug("  [BUZZ OFF]")


# ─────────────────────────────────────────────
# BUZZ PATTERNS
# ─────────────────────────────────────────────

def _play_pattern(pattern_name: Optional[str]):
    """
    Plays a buzz pattern by name.
    Non-blocking in the sense that it returns as soon as the
    pattern finishes — the pattern durations are short enough
    (max ~500ms) that blocking is fine in our 3-4s loop.
    """
    if pattern_name is None:
        return  # Silent events

    pattern = PATTERNS.get(pattern_name, PATTERNS["single"])
    count  = pattern["count"]
    on_s   = pattern["on_ms"]  / 1000
    off_s  = pattern["off_ms"] / 1000

    for i in range(count):
        _buzzer_on()
        time.sleep(on_s)
        _buzzer_off()
        if i < count - 1 and off_s > 0:
            time.sleep(off_s)


# ─────────────────────────────────────────────
# SCORE BAR BUILDER
# Renders a visual progress bar for LCD line 2.
# Score 0.0 → "░░░░░░░░░░  0%"
# Score 0.81 → "████████░░ 81%"
# Score 1.0 → "██████████100%"
# 10 blocks + 3-char percentage = exactly 16 chars
# ─────────────────────────────────────────────

def _score_bar(score: float) -> str:
    score   = max(0.0, min(1.0, score))
    filled  = int(score * 10)
    empty   = 10 - filled
    pct     = int(score * 100)
    return f"{'█' * filled}{'░' * empty}{pct:3d}%"


# ─────────────────────────────────────────────
# MAIN FEEDBACK FUNCTION
# ─────────────────────────────────────────────

def apply(event: dict):
    """
    Takes a CoachingEvent dict (as returned by the server JSON response)
    and drives the LCD + buzzer accordingly.

    Args:
        event: dict with keys:
                 event        (str)   — event type
                 score        (float) — retention score 0.0-1.0
                 message      (str)   — LCD line 1 text
                 detail       (str)   — LCD line 2 text (score bar from server)
                 buzz         (bool)  — whether to fire the buzzer
                 buzz_pattern (str)   — which buzz pattern to use

    Called from pi/main.py on every loop iteration.
    """
    _init_gpio()

    event_type   = event.get("event",        "GOOD")
    score        = float(event.get("score",  0.70))
    message      = event.get("message",      "")
    detail       = event.get("detail",       "")
    should_buzz  = bool(event.get("buzz",    False))
    buzz_pattern = event.get("buzz_pattern", None)

    # Build score bar locally as fallback if server didn't send detail
    score_line = detail if detail.strip() else _score_bar(score)

    # ── 1. Update LCD ──────────────────────────────────────────────────
    lcd_show(message, score_line, event_type)

    # ── 2. Fire buzzer ─────────────────────────────────────────────────
    if should_buzz:
        # Use the pattern from the server response if provided,
        # otherwise fall back to the default for this event type
        pattern = (
            buzz_pattern
            if buzz_pattern and buzz_pattern in PATTERNS
            else EVENT_DEFAULT_PATTERNS.get(event_type)
        )
        _play_pattern(pattern)

    # ── 3. Log to terminal ─────────────────────────────────────────────
    buzz_indicator = "🔔" if should_buzz else "  "
    logger.info(
        f"{buzz_indicator} {event_type:<14}  "
        f"score={score:.2f}  "
        f"msg='{message}'"
    )


def apply_error(message: str = "Server error"):
    """
    Called when the server is unreachable or returns a bad response.
    Shows an error state on LCD. Does not buzz.
    """
    _init_gpio()
    lcd_error(message[:16])
    logger.warning(f"Error state displayed: {message}")


def cleanup():
    """
    Release GPIO resources. Call on shutdown.
    """
    if _gpio_available:
        try:
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            GPIO.cleanup()
            logger.info("GPIO cleaned up.")
        except Exception as e:
            logger.warning(f"GPIO cleanup error: {e}")


# ─────────────────────────────────────────────
# QUICK TEST
# Run directly to verify buzzer patterns + LCD colors:
#   python3 feedback.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s"
    )

    print("Testing feedback output — all 5 events\n")

    test_events = [
        {
            "event":        "GOOD",
            "score":        0.88,
            "message":      "GREAT ENERGY!",
            "detail":       "",
            "buzz":         False,
            "buzz_pattern": None,
        },
        {
            "event":        "SPEED_UP",
            "score":        0.51,
            "message":      "SPEED IT UP!",
            "detail":       "",
            "buzz":         True,
            "buzz_pattern": "triple",
        },
        {
            "event":        "VIBE_CHECK",
            "score":        0.58,
            "message":      "SHOW ENERGY!",
            "detail":       "",
            "buzz":         True,
            "buzz_pattern": "double",
        },
        {
            "event":        "RAISE_ENERGY",
            "score":        0.43,
            "message":      "RAISE ENERGY!",
            "detail":       "",
            "buzz":         True,
            "buzz_pattern": "long",
        },
        {
            "event":        "VISUAL_RESET",
            "score":        0.64,
            "message":      "MOVE AROUND!",
            "detail":       "",
            "buzz":         False,
            "buzz_pattern": None,
        },
    ]

    for ev in test_events:
        print(f"\n--- Testing: {ev['event']} ---")
        apply(ev)
        time.sleep(2.0)

    cleanup()
    print("\n✓ Feedback test complete.")
