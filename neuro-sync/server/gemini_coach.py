"""
gemini_coach.py — Gemini 1.5 Flash Vision inference engine.

This is the core AI brain of Neuro-Sync. It receives:
  - A JPEG frame from the webcam (bytes)
  - AudioMetrics from the Pi's sound sensor
  - The current SessionState (for smarter context-aware decisions)

And returns a CoachingEvent telling the Pi what to show + whether to buzz.

How Gemini is being used here:
  We're NOT doing simple threshold detection ("if wpm < 80 then SPEED_UP").
  We're asking Gemini to reason across MULTIPLE signals simultaneously:
    - What does the face look like? (visual)
    - Does facial energy match the audio energy? (cross-modal)
    - Is the pacing appropriate for what the body language suggests? (contextual)
  
  This catches things a simple rule system would miss — like a creator who's
  speaking at normal WPM but their face has completely checked out.
"""

import json
import os
import time
import base64
import logging
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from models import AudioMetrics, CoachingEvent, EventType, SessionState

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# GEMINI SETUP
# ─────────────────────────────────────────────

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=genai.GenerationConfig(
        temperature=0.2,        # Low temp = consistent, predictable JSON output
        max_output_tokens=256,  # We only need a small JSON blob back
        response_mime_type="application/json",  # Tell Gemini to return pure JSON
    )
)


# ─────────────────────────────────────────────
# PROMPT BUILDER
# The prompt is dynamically built each call so it includes
# live context: audio metrics, session trend, cooldown state
# ─────────────────────────────────────────────

def _build_prompt(audio: AudioMetrics, session: SessionState) -> str:
    trend = session.recent_score_trend()
    avg   = session.average_score()
    consecutive_bad = session.consecutive_bad

    # Build a context hint so Gemini knows what's already been flagged
    # This prevents Gemini from ignoring a problem just because it's persistent
    context_hint = ""
    if consecutive_bad >= 3:
        context_hint = f"Note: The creator has received {consecutive_bad} non-GOOD events in a row. Score trend is {trend}. Be direct."
    elif trend == "rising":
        context_hint = "Note: Score has been improving recently. Acknowledge if things look good."
    elif trend == "falling":
        context_hint = "Note: Score has been declining. Be specific about what's dropping."

    # Interpret the audio numbers into plain English for Gemini
    # This gives the model a pre-computed reading to reason about
    wpm_note = (
        "very slow (under 70 wpm)" if audio.estimated_wpm < 70 else
        "slow (70-85 wpm)"         if audio.estimated_wpm < 85 else
        "good pace (85-150 wpm)"   if audio.estimated_wpm < 150 else
        "very fast (over 150 wpm)"
    )
    volume_note = (
        "nearly silent"  if audio.volume_rms < 0.08 else
        "quiet"          if audio.volume_rms < 0.18 else
        "normal volume"  if audio.volume_rms < 0.55 else
        "loud"
    )
    silence_note = (
        "talking almost continuously" if audio.silence_ratio < 0.15 else
        "occasional pauses (normal)"  if audio.silence_ratio < 0.35 else
        "lots of pauses (too many)"   if audio.silence_ratio < 0.55 else
        "mostly silent (barely talking)"
    )
    expressiveness = (
        "very monotone delivery (low volume variance)" if audio.volume_variance < 0.005 else
        "slightly flat delivery"                       if audio.volume_variance < 0.015 else
        "expressive delivery (good variance)"
    )

    return f"""You are an expert real-time coaching system for short-form video creators (TikTok, Reels, YouTube Shorts).

Analyze the provided camera frame and audio data. Return a single JSON object — nothing else.

=== AUDIO DATA (from wrist mic sensor) ===
- Pace: {wpm_note} ({audio.estimated_wpm} wpm)
- Volume: {volume_note} (rms={audio.volume_rms:.3f})
- Silence: {silence_note} ({audio.silence_ratio:.1%} of last 2 seconds was silent)
- Expressiveness: {expressiveness} (variance={audio.volume_variance:.4f})
- Peak volume this window: {audio.peak_volume:.3f}

=== SESSION CONTEXT ===
- Session avg score so far: {avg:.2f}
- Score trend (last 3 reads): {trend}
{context_hint}

=== YOUR TASK ===
Look at the face and body in the frame. Cross-reference with the audio data above.
Determine the single most important coaching signal RIGHT NOW.

Choose ONE event type from this list. Pick the MOST URGENT issue — don't pick GOOD if there's a real problem:

GOOD         → Face engaged, eyes forward, energy matches or exceeds the audio energy. Pacing is normal. Nothing to fix.
SPEED_UP     → Pacing is too slow OR there are too many pauses. Audio says slow/silent. Creator needs to trim filler and push forward.
VIBE_CHECK   → Audio pace/volume seems okay BUT face looks flat, bored, or disconnected. Energy mismatch between audio and visual.
RAISE_ENERGY → Both face AND audio show low energy. Creator is physically deflating — slouching, looking away, voice going quiet.
VISUAL_RESET → Creator has been completely static — no body movement, same position, no visual dynamism. Need to shift frame or move.

=== OUTPUT FORMAT ===
Return ONLY this JSON. No markdown. No explanation:
{{
  "event": "<one of the 5 event types above>",
  "score": <float 0.0-1.0 — how well the creator is performing RIGHT NOW>,
  "message": "<max 14 chars — shown on physical LCD screen>",
  "buzz": <true if this needs an audible alert, false if not>,
  "buzz_pattern": "<single | double | triple | long>",
  "confidence": <float 0.0-1.0 — how confident you are in this classification>,
  "reasoning": "<one sentence explaining what you saw>"
}}

=== SCORING GUIDE ===
0.85-1.0 → Creator is excellent. Energy high, engaged, good pace.
0.70-0.84 → Good but minor issues. Still mostly on track.
0.55-0.69 → Noticeable problems. Audience attention at risk.
0.40-0.54 → Clear issues. Something needs to change now.
0.00-0.39 → Multiple things wrong simultaneously.

=== LCD MESSAGE EXAMPLES (14 chars max) ===
GOOD:         "GREAT ENERGY!", "IN THE ZONE!", "NAILED IT!"
SPEED_UP:     "SPEED UP!", "CUT THE PAUSE", "KEEP MOVING!"
VIBE_CHECK:   "SHOW IT!", "WAKE UP FACE", "MATCH ENERGY!"
RAISE_ENERGY: "MORE ENERGY!", "CHIN UP LOUD", "PROJECT MORE"
VISUAL_RESET: "MOVE AROUND!", "CHANGE ANGLE", "STEP CLOSER!"

=== BUZZ RULES ===
- GOOD → buzz=false always
- VISUAL_RESET → buzz=false (they're talking, don't interrupt)
- SPEED_UP, VIBE_CHECK, RAISE_ENERGY → buzz=true
- buzz_pattern: "triple" for SPEED_UP, "double" for VIBE_CHECK, "long" for RAISE_ENERGY
"""


# ─────────────────────────────────────────────
# SAFE JSON PARSER
# Gemini sometimes wraps output in ```json ``` even with response_mime_type set.
# This handles all the edge cases.
# ─────────────────────────────────────────────

def _parse_gemini_response(text: str) -> dict:
    text = text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()

    parsed = json.loads(text)  # Let this raise — caller handles it

    # Validate all required keys exist
    required = {"event", "score", "message", "buzz", "buzz_pattern", "confidence"}
    missing = required - parsed.keys()
    if missing:
        raise ValueError(f"Gemini response missing keys: {missing}")

    # Validate event is a known type
    if parsed["event"] not in [e.value for e in EventType]:
        raise ValueError(f"Unknown event type: {parsed['event']}")

    # Clamp score and confidence to valid range
    parsed["score"]      = max(0.0, min(1.0, float(parsed["score"])))
    parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))

    # Truncate message to 14 chars (LCD line 1 is 16 but we want padding)
    parsed["message"] = str(parsed["message"])[:14]

    return parsed


# ─────────────────────────────────────────────
# FALLBACK EVENTS
# Used when Gemini fails (API error, rate limit, bad JSON, timeout)
# Degrade gracefully — don't crash the demo
# ─────────────────────────────────────────────

FALLBACK_EVENTS = {
    # If we can't reach Gemini, return GOOD so we don't spam false alerts
    "default": CoachingEvent(
        event=EventType.GOOD,
        score=0.70,
        message="CONNECTING...",
        detail="",
        buzz=False,
        buzz_pattern="single",
        confidence=0.0
    )
}


# ─────────────────────────────────────────────
# COOLDOWN OVERRIDE
# Even if Gemini says to fire an event, check if it's been
# suppressed by the session cooldown manager first
# ─────────────────────────────────────────────

def _apply_cooldown(event: CoachingEvent, session: SessionState) -> CoachingEvent:
    """
    If the same event was fired very recently, suppress the buzz but
    still update the LCD message and score. This way the creator still
    sees the issue on screen without getting constantly buzzed.
    """
    if session.is_on_cooldown(event.event):
        return CoachingEvent(
            event=event.event,
            score=event.score,
            message=event.message,
            detail=event.detail,
            buzz=False,           # Suppress buzz — they already know
            buzz_pattern="single",
            confidence=event.confidence,
            timestamp=event.timestamp
        )
    return event


# ─────────────────────────────────────────────
# MAIN INFERENCE FUNCTION
# This is the function called by routes.py on every request
# ─────────────────────────────────────────────

async def analyze(
    image_bytes: bytes,
    audio: AudioMetrics,
    session: SessionState,
) -> CoachingEvent:
    """
    Core inference call. Sends image + audio to Gemini, returns a CoachingEvent.
    
    Args:
        image_bytes: Raw JPEG bytes from the webcam
        audio:       AudioMetrics computed by the Pi's sound sensor
        session:     Current session state for context + cooldown management
    
    Returns:
        CoachingEvent ready to be sent back to the Pi
    """

    prompt = _build_prompt(audio, session)

    # Gemini expects the image as a Part with mime_type
    image_part = {
        "mime_type": "image/jpeg",
        "data": base64.b64encode(image_bytes).decode("utf-8")
    }

    t_start = time.perf_counter()

    try:
        response = await model.generate_content_async(
            contents=[prompt, image_part],
            request_options={"timeout": 8}  # Don't wait more than 8s
        )

        latency_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"Gemini latency: {latency_ms:.0f}ms")

        raw = _parse_gemini_response(response.text)

        # Build the score bar for LCD line 2
        score = raw["score"]
        filled = int(score * 10)
        score_bar = "█" * filled + "░" * (10 - filled) + f"{int(score*100):3d}%"

        event = CoachingEvent(
            event=EventType(raw["event"]),
            score=score,
            message=raw["message"],
            detail=score_bar,
            buzz=raw["buzz"],
            buzz_pattern=raw.get("buzz_pattern", "single"),
            confidence=raw.get("confidence", 1.0),
        )

        # Log what Gemini saw
        reasoning = raw.get("reasoning", "")
        logger.info(
            f"Event: {event.event.value:<14} "
            f"Score: {event.score:.2f}  "
            f"Confidence: {event.confidence:.2f}  "
            f"| {reasoning}"
        )

        # Apply cooldown before returning
        event = _apply_cooldown(event, session)

        # Record to session history
        session.record(event)

        return event

    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned non-JSON: {e} | Raw: {response.text[:200]}")
        return FALLBACK_EVENTS["default"]

    except ValueError as e:
        logger.error(f"Gemini response validation failed: {e}")
        return FALLBACK_EVENTS["default"]

    except Exception as e:
        logger.error(f"Gemini call failed: {type(e).__name__}: {e}")
        return FALLBACK_EVENTS["default"]
