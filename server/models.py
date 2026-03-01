"""
models.py — All data shapes for Neuro-Sync.

This is the single source of truth for what gets sent between
the Pi (client) and the laptop (server). Both sides import from here.

Flow:
  Pi sends  → AnalysisRequest  (image bytes + AudioMetrics)
  Server returns → CoachingEvent  (event type + LCD message + buzz)
"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
import time


# ─────────────────────────────────────────────
# ENUMS — the 5 possible coaching events
# ─────────────────────────────────────────────

class EventType(str, Enum):
    GOOD         = "GOOD"          # Creator is locked in — hold this energy
    SPEED_UP     = "SPEED_UP"      # Talking too slow / too many pauses
    VIBE_CHECK   = "VIBE_CHECK"    # Face is flat, energy doesn't match words
    RAISE_ENERGY = "RAISE_ENERGY"  # Vocal energy dropping, posture bad
    VISUAL_RESET = "VISUAL_RESET"  # Completely static — no movement
    HOOK_GOOD    = "HOOK_GOOD"     # Hook grabs attention — doom-scroller would stay
    HOOK_WEAK    = "HOOK_WEAK"     # Hook is weak — doom-scroller would scroll past


# ─────────────────────────────────────────────
# AUDIO METRICS — computed on the Pi from the sound sensor
# Sent up to the laptop with every analysis request
# ─────────────────────────────────────────────

class AudioMetrics(BaseModel):
    volume_rms: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="Root mean square of sound sensor readings. 0=silent, 1=very loud."
    )
    silence_ratio: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="Fraction of the sampling window that was below the silence threshold."
    )
    estimated_wpm: int = Field(
        ...,
        ge=0, le=400,
        description="Rough words-per-minute estimated from syllable burst counting."
    )
    peak_volume: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Highest single sample in the window. Good for detecting sudden loud moments."
    )
    volume_variance: float = Field(
        default=0.0,
        ge=0.0,
        description="Variance of volume samples. High variance = expressive. Low = monotone."
    )

    @field_validator("volume_rms", "silence_ratio", "peak_volume")
    @classmethod
    def clamp_float(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)


# ─────────────────────────────────────────────
# COACHING EVENT — what the laptop sends back to the Pi
# ─────────────────────────────────────────────

class CoachingEvent(BaseModel):
    event: EventType
    score: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="Retention score. 0=creator is losing audience, 1=perfect."
    )
    message: str = Field(
        ...,
        max_length=16,
        description="Text for LCD line 1. Max 16 chars (LCD screen width)."
    )
    detail: str = Field(
        default="",
        max_length=16,
        description="Text for LCD line 2. Score bar goes here."
    )
    buzz: bool = Field(
        default=False,
        description="Whether to fire the buzzer."
    )
    buzz_pattern: str = Field(
        default="single",
        description="Buzzer pattern: 'single' | 'double' | 'triple' | 'long'"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0, le=1.0,
        description="Gemini's confidence in this classification."
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of when this event was generated."
    )
    phase: str = Field(
        default="normal",
        description="Session phase when this event was generated: 'hook' or 'normal'."
    )
    reasoning: str = Field(
        default="",
        description="Gemini's reasoning for this classification."
    )

    def score_bar(self) -> str:
        """Renders a 10-char ASCII bar for the LCD line 2. e.g. '████████░░ 81%'"""
        filled = int(self.score * 10)
        bar = "█" * filled + "░" * (10 - filled)
        return f"{bar}{int(self.score * 100):3d}%"

    @field_validator("message", "detail")
    @classmethod
    def truncate_to_lcd_width(cls, v: str) -> str:
        return v[:16]


# ─────────────────────────────────────────────
# SESSION STATE — tracks the full recording session
# Used for cooldown logic and trend analysis
# ─────────────────────────────────────────────

class SessionState:
    """
    Tracks recent events to enable smarter coaching decisions.
    
    Examples of what this enables:
    - Don't fire SPEED_UP three times in a row — creator heard it, give them a chance to fix it
    - If score has been falling for 3 consecutive reads, upgrade alert severity
    - Track how long the creator has been in GOOD state (for positive reinforcement)
    """

    COOLDOWN_SECONDS = {
        EventType.GOOD:         0.0,   # Always show GOOD — positive feedback is free
        EventType.SPEED_UP:     8.0,   # Don't nag — wait 8s before repeating
        EventType.VIBE_CHECK:   10.0,  # Give them time to adjust expression
        EventType.RAISE_ENERGY: 10.0,  # Same
        EventType.VISUAL_RESET: 12.0,  # Movement changes take time
        EventType.HOOK_GOOD:    0.0,   # Hook events are one-shot, no cooldown
        EventType.HOOK_WEAK:    0.0,
    }

    HOOK_DURATION = 3.0  # seconds

    def __init__(self):
        self.history: list[CoachingEvent] = []
        self.last_event_time: dict[EventType, float] = {}
        self.consecutive_good: int = 0
        self.consecutive_bad:  int = 0
        self.phase: str = "hook"
        self.recording_start_time: float = 0.0
        self.hook_results: list[CoachingEvent] = []
        self.hook_evaluated: bool = False
        self.hook_buffer_image: bytes = b""   # last image captured during hook
        self.hook_buffer_audio: bytes = b""   # last audio captured during hook
        self.device_id: Optional[str] = None  # device UUID from iOS client

    def record(self, event: CoachingEvent):
        self.history.append(event)
        self.last_event_time[event.event] = time.time()

        if event.event == EventType.GOOD:
            self.consecutive_good += 1
            self.consecutive_bad = 0
        else:
            self.consecutive_bad += 1
            self.consecutive_good = 0

    def is_on_cooldown(self, event_type: EventType) -> bool:
        """Returns True if we should suppress this event to avoid repetition."""
        if event_type == EventType.GOOD:
            return False  # Never suppress positive feedback
        last = self.last_event_time.get(event_type, 0.0)
        cooldown = self.COOLDOWN_SECONDS.get(event_type, 8.0)
        return (time.time() - last) < cooldown

    def recent_score_trend(self, n: int = 3) -> str:
        """Returns 'rising', 'falling', or 'stable' based on last n scores."""
        if len(self.history) < n:
            return "stable"
        recent = [e.score for e in self.history[-n:]]
        delta = recent[-1] - recent[0]
        if delta > 0.08:
            return "rising"
        if delta < -0.08:
            return "falling"
        return "stable"

    def update_phase(self):
        """Transitions from 'hook' to 'normal' after HOOK_DURATION seconds elapsed."""
        if self.phase == "hook" and self.recording_start_time > 0:
            elapsed = time.time() - self.recording_start_time
            if elapsed >= self.HOOK_DURATION:
                self.phase = "normal"

    def average_score(self, last_n: int = 10) -> float:
        if not self.history:
            return 0.0
        window = self.history[-last_n:]
        return sum(e.score for e in window) / len(window)
