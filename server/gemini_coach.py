"""
gemini_coach.py — Gemini multimodal inference engine.

Uses the Gemini Live API with native audio model to actually HEAR
the creator's tone, pitch, emotion, and pacing — not just computed numbers.

Model: gemini-2.5-flash-native-audio (via bidiGenerateContent / Live API)
Fallback: gemini-2.5-flash-lite (regular generateContent, vision only)
"""

import asyncio
import json
import os
import time
import io
import wave
import logging
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from models import AudioMetrics, CoachingEvent, EventType, SessionState

load_dotenv()
logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"
VISION_MODEL = "gemini-2.5-flash-lite"

# ─────────────────────────────────────────────
# SYSTEM INSTRUCTION (set once at session connect)
# ─────────────────────────────────────────────

AUDIO_SYSTEM_INSTRUCTION = """You are an expert real-time audio coach for short-form video creators (TikTok, Reels, YouTube Shorts).

You receive an audio clip of the creator speaking. Analyze ONLY what you hear.

=== WHAT TO LISTEN FOR ===
- Vocal ENERGY — excited, confident, flat, bored?
- Speaking PACE — rushing, dragging, natural rhythm?
- TONE — enthusiastic, hesitant, monotone, dynamic?
- PAUSES — awkward silences vs natural breathing?
- PITCH VARIATION — expressive vs flat delivery?
- EMOTION — genuinely engaged or going through motions?

=== EVENT TYPES ===
GOOD         → Sounds engaged. Energy is good. Pace is natural.
SPEED_UP     → Speaking too slowly, too many pauses, long silences.
RAISE_ENERGY → Voice shows low energy. Flat tone, quiet, monotone.

=== CRITICAL RULE ===
If the creator sounds excited, happy, and energetic — that IS good. Return GOOD.
Do NOT second-guess genuine enthusiasm. Trust what you hear.

=== OUTPUT ===
Always respond with ONLY a JSON object. No markdown. No explanation. No extra text.
{
  "event": "<GOOD|SPEED_UP|RAISE_ENERGY>",
  "score": <float 0.0-1.0>,
  "message": "<max 14 chars>",
  "buzz": <true|false>,
  "buzz_pattern": "<single|double|triple|long>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}

Buzz rules: GOOD → false. SPEED_UP → triple. RAISE_ENERGY → long.
Scoring: 0.85-1.0 excellent, 0.70-0.84 good, 0.55-0.69 issues, 0.40-0.54 bad, <0.40 very bad."""

VISION_SYSTEM_INSTRUCTION = """You are an expert real-time visual coach for short-form video creators (TikTok, Reels, YouTube Shorts).

You receive a camera frame showing the creator. Analyze ONLY what you see.

=== WHAT TO LOOK FOR ===
- Facial EXPRESSION — smiling, flat, engaged, checked out?
- EYE CONTACT — looking at camera or away?
- BODY LANGUAGE — upright and energetic, or slouching?
- MOVEMENT — dynamic or completely static?

=== EVENT TYPES ===
GOOD         → Looks engaged. Expression is lively.
VIBE_CHECK   → Face looks flat/bored. Low visual energy.
VISUAL_RESET → Body completely static too long. Need movement.

=== OUTPUT ===
Always respond with ONLY a JSON object. No markdown. No explanation. No extra text.
{
  "event": "<GOOD|VIBE_CHECK|VISUAL_RESET>",
  "score": <float 0.0-1.0>,
  "message": "<max 14 chars>",
  "buzz": <true|false>,
  "buzz_pattern": "<single|double|triple|long>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}

Buzz rules: GOOD/VISUAL_RESET → false. VIBE_CHECK → double.
Scoring: 0.85-1.0 excellent, 0.70-0.84 good, 0.55-0.69 issues, 0.40-0.54 bad, <0.40 very bad."""


# ─────────────────────────────────────────────
# HOOK EVALUATION PROMPTS (first 3 seconds)
# Uses one-shot generateContent, NOT the persistent Live session
# ─────────────────────────────────────────────

HOOK_AUDIO_SYSTEM_INSTRUCTION = """You are a casual TikTok/Reels viewer evaluating the opening of a short-form video. You're interested but have other options.

You just heard the first 3 seconds. Judge the audio hook fairly — most creators are NOT professional broadcasters.

=== HOOK_GOOD (default — lean toward this) ===
- Speaker sounds confident, even if casual
- Any clear energy or enthusiasm
- Gets to a point quickly (doesn't have to be instant)
- Natural conversational tone counts as good
- "Hey so I found this thing..." with real energy = GOOD

=== HOOK_WEAK (only for clearly bad starts) ===
- Dead silence or mumbling for multiple seconds
- Sounds genuinely bored or confused about what to say
- Multiple false starts with no recovery ("um... uh... so... yeah...")
- Whispering or inaudible

=== IMPORTANT ===
Default to HOOK_GOOD when unsure. A casual but confident opening IS a good hook.
Do NOT penalize: casual language, "hey guys", normal speaking pace, slight pauses.
Real creators are informal — that's fine. Judge energy and intent, not polish.

=== OUTPUT ===
Respond with ONLY a JSON object:
{
  "event": "<HOOK_GOOD|HOOK_WEAK>",
  "score": <float 0.0-1.0>,
  "message": "<max 14 chars>",
  "buzz": <true|false>,
  "buzz_pattern": "<single|double|triple|long>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one short sentence>"
}

Buzz rules: HOOK_GOOD → false. HOOK_WEAK → double.
Scoring: 0.80+ strong, 0.65-0.79 solid, 0.50-0.64 borderline, <0.50 genuinely weak."""

HOOK_VISION_SYSTEM_INSTRUCTION = """You are a casual TikTok/Reels viewer evaluating the opening frame of a short-form video.

You see the first frame. Judge the visual hook fairly — most creators film on phones in normal rooms.

=== HOOK_GOOD (default — lean toward this) ===
- Person is visible and facing the camera (even roughly)
- Any expression beyond completely blank
- Reasonable framing — doesn't have to be perfect
- Normal selfie-style framing is fine

=== HOOK_WEAK (only for clearly bad visuals) ===
- Camera is pointing at ceiling/floor/nothing
- Person is completely out of frame or turned away
- Screen is black, blurry, or unrecognizable
- Genuinely zero effort in setup

=== IMPORTANT ===
Default to HOOK_GOOD when unsure. Normal phone selfie framing IS good enough.
Do NOT penalize: imperfect lighting, casual settings, slight off-center framing, neutral resting face.
This is social media, not a movie. Judge presence and intent, not production quality.

=== OUTPUT ===
Respond with ONLY a JSON object:
{
  "event": "<HOOK_GOOD|HOOK_WEAK>",
  "score": <float 0.0-1.0>,
  "message": "<max 14 chars>",
  "buzz": <true|false>,
  "buzz_pattern": "<single|double|triple|long>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one short sentence>"
}

Buzz rules: HOOK_GOOD → false. HOOK_WEAK → double.
Scoring: 0.80+ strong, 0.65-0.79 solid, 0.50-0.64 borderline, <0.50 genuinely weak."""

HOOK_FALLBACK = CoachingEvent(
    event=EventType.HOOK_GOOD,
    score=0.65,
    message="HOOK EVAL...",
    detail="",
    buzz=False,
    buzz_pattern="single",
    confidence=0.0,
    phase="hook",
    reasoning="Hook evaluation in progress",
)


# ─────────────────────────────────────────────
# LIVE API SESSION MANAGER
# ─────────────────────────────────────────────

class LiveCoach:
    """Maintains a persistent Live API session for native audio analysis."""

    def __init__(self):
        self._session = None
        self._ctx = None
        self._lock = asyncio.Lock()

    async def _connect(self):
        """Open a new Live API WebSocket session."""
        # Clean up old session
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass

        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=AUDIO_SYSTEM_INSTRUCTION)]
            ),
        )

        self._ctx = client.aio.live.connect(model=LIVE_MODEL, config=config)
        self._session = await self._ctx.__aenter__()
        logger.info(f"Live session connected to {LIVE_MODEL}")

    async def analyze(self, image_bytes: bytes, audio_wav_bytes: bytes, turn_prompt: str) -> str:
        """
        Send audio + context through the Live session.
        Native audio model only accepts audio — no image input.
        Returns the raw text response from Gemini.
        """
        async with self._lock:
            try:
                if self._session is None:
                    await self._connect()

                # Convert WAV to raw PCM (Live API wants raw PCM, not WAV)
                pcm_bytes = self._wav_to_pcm(audio_wav_bytes)

                # Send audio first (native audio model requires audio)
                await self._session.send(
                    input={"data": pcm_bytes, "mime_type": "audio/pcm;rate=16000"},
                )

                # Send context prompt and end turn
                await self._session.send(
                    input=turn_prompt,
                    end_of_turn=True,
                )

                # Collect response text
                text = ""
                async for msg in self._session.receive():
                    if msg.text:
                        text += msg.text

                return text

            except Exception as e:
                logger.error(f"Live session error: {type(e).__name__}: {e}")
                # Reset session so next call reconnects
                self._session = None
                self._ctx = None
                raise

    async def close(self):
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
            self._ctx = None

    @staticmethod
    def _wav_to_pcm(wav_bytes: bytes) -> bytes:
        """Extract raw PCM int16 data from WAV bytes."""
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            return wf.readframes(wf.getnframes())


# Singleton live coach
_live_coach = LiveCoach()


# ─────────────────────────────────────────────
# PER-TURN PROMPT (session context only)
# ─────────────────────────────────────────────

def _build_turn_prompt(session: SessionState) -> str:
    trend = session.recent_score_trend()
    avg = session.average_score()
    consecutive_bad = session.consecutive_bad

    context = f"Session avg score: {avg:.2f} | Trend: {trend}"
    if consecutive_bad >= 3:
        context += f" | {consecutive_bad} non-GOOD events in a row — be direct."

    return f"[Context: {context}] Analyze this frame and audio clip. Return JSON only."


# ─────────────────────────────────────────────
# JSON PARSER
# ─────────────────────────────────────────────

def _parse_gemini_response(text: str) -> dict:
    text = text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()

    # Try to find JSON in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    parsed = json.loads(text)

    required = {"event", "score", "message"}
    missing = required - parsed.keys()
    if missing:
        raise ValueError(f"Missing keys: {missing}")

    # Fill defaults for optional fields
    parsed.setdefault("buzz", False)
    parsed.setdefault("buzz_pattern", "single")
    parsed.setdefault("confidence", 0.8)

    if parsed["event"] not in [e.value for e in EventType]:
        raise ValueError(f"Unknown event: {parsed['event']}")

    parsed["score"] = max(0.0, min(1.0, float(parsed["score"])))
    parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))
    parsed["message"] = str(parsed["message"])[:14]

    return parsed


# ─────────────────────────────────────────────
# FALLBACK
# ─────────────────────────────────────────────

FALLBACK = CoachingEvent(
    event=EventType.GOOD,
    score=0.70,
    message="CONNECTING...",
    detail="",
    buzz=False,
    buzz_pattern="single",
    confidence=0.0
)


def _apply_cooldown(event: CoachingEvent, session: SessionState) -> CoachingEvent:
    if session.is_on_cooldown(event.event):
        return CoachingEvent(
            event=event.event, score=event.score, message=event.message,
            detail=event.detail, buzz=False, buzz_pattern="single",
            confidence=event.confidence, timestamp=event.timestamp
        )
    return event


# ─────────────────────────────────────────────
# VISION-ONLY FALLBACK (when no audio)
# ─────────────────────────────────────────────

async def _analyze_vision_only(image_bytes: bytes, session: SessionState) -> CoachingEvent:
    """Fallback: use regular generateContent with vision model when no audio."""
    prompt = f"""{VISION_SYSTEM_INSTRUCTION}

Session context: avg={session.average_score():.2f}, trend={session.recent_score_trend()}

Analyze this frame now. Return ONLY the JSON object."""

    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[prompt, image_part],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=256,
            response_mime_type="application/json",
        ),
    )

    text = ""
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text += part.text

    return text


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def _merge_results(audio_raw: dict, vision_raw: dict) -> dict:
    """
    Merge audio (native) and vision analysis into one coaching event.
    Audio is weighted higher (0.6) since tone/energy is more important for creators.
    """
    audio_score = audio_raw.get("score", 0.7)
    vision_score = vision_raw.get("score", 0.7)
    merged_score = audio_score * 0.6 + vision_score * 0.4

    # Pick the worse event as the primary signal
    priority = {"RAISE_ENERGY": 0, "SPEED_UP": 1, "VIBE_CHECK": 2, "VISUAL_RESET": 3, "GOOD": 4}
    audio_event = audio_raw.get("event", "GOOD")
    vision_event = vision_raw.get("event", "GOOD")

    if priority.get(audio_event, 4) <= priority.get(vision_event, 4):
        event = audio_event
        message = audio_raw.get("message", "")
        buzz = audio_raw.get("buzz", False)
        buzz_pattern = audio_raw.get("buzz_pattern", "single")
    else:
        event = vision_event
        message = vision_raw.get("message", "")
        buzz = vision_raw.get("buzz", False)
        buzz_pattern = vision_raw.get("buzz_pattern", "single")

    # But if audio says GOOD and vision says something minor, trust audio
    if audio_event == "GOOD" and audio_raw.get("confidence", 0) > 0.7:
        event = "GOOD"
        message = audio_raw.get("message", "LOCKED IN")
        buzz = False
        buzz_pattern = "single"
        merged_score = max(merged_score, audio_score)

    audio_reason = audio_raw.get("reasoning", "")
    vision_reason = vision_raw.get("reasoning", "")
    reasoning = f"Audio: {audio_reason} | Visual: {vision_reason}"

    confidence = min(audio_raw.get("confidence", 1.0), vision_raw.get("confidence", 1.0))

    return {
        "event": event,
        "score": round(merged_score, 3),
        "message": message[:14],
        "buzz": buzz,
        "buzz_pattern": buzz_pattern,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def _merge_hook_results(audio_raw: dict | None, vision_raw: dict | None) -> dict:
    """
    Merge hook audio (65%) and vision (35%) evaluations.
    If either says HOOK_WEAK, the result is HOOK_WEAK.
    """
    if audio_raw and vision_raw:
        audio_score = audio_raw.get("score", 0.7)
        vision_score = vision_raw.get("score", 0.7)
        merged_score = audio_score * 0.65 + vision_score * 0.35

        audio_event = audio_raw.get("event", "HOOK_GOOD")
        vision_event = vision_raw.get("event", "HOOK_GOOD")

        # Both must say weak for it to be weak — one weak isn't enough
        if audio_event == "HOOK_WEAK" and vision_event == "HOOK_WEAK":
            event = "HOOK_WEAK"
        elif merged_score < 0.45:
            event = "HOOK_WEAK"
        else:
            event = "HOOK_GOOD"

        audio_reason = audio_raw.get("reasoning", "")
        vision_reason = vision_raw.get("reasoning", "")
        reasoning = f"Audio: {audio_reason} | Visual: {vision_reason}"
        confidence = min(audio_raw.get("confidence", 1.0), vision_raw.get("confidence", 1.0))
        message = audio_raw.get("message", "") if audio_event == "HOOK_WEAK" else vision_raw.get("message", "")
        if event == "HOOK_GOOD":
            message = audio_raw.get("message", "GREAT HOOK!")
        buzz = event == "HOOK_WEAK"

        return {
            "event": event,
            "score": round(merged_score, 3),
            "message": message[:14],
            "buzz": buzz,
            "buzz_pattern": "double" if buzz else "single",
            "confidence": confidence,
            "reasoning": reasoning,
        }
    elif audio_raw:
        return audio_raw
    elif vision_raw:
        return vision_raw
    else:
        return {"event": "HOOK_GOOD", "score": 0.65, "message": "HOOK EVAL...", "confidence": 0.0, "reasoning": ""}


async def _analyze_hook_audio(audio_wav_bytes: bytes) -> str | None:
    """One-shot audio hook analysis using generateContent (not Live session)."""
    pcm_bytes = LiveCoach._wav_to_pcm(audio_wav_bytes)
    audio_part = types.Part.from_bytes(data=pcm_bytes, mime_type="audio/pcm;rate=16000")

    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[HOOK_AUDIO_SYSTEM_INSTRUCTION + "\n\nAnalyze this audio opening. Return ONLY JSON.", audio_part],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=256,
            response_mime_type="application/json",
        ),
    )

    text = ""
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text += part.text
    return text or None


async def _analyze_hook_vision(image_bytes: bytes) -> str | None:
    """One-shot vision hook analysis using generateContent."""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[HOOK_VISION_SYSTEM_INSTRUCTION + "\n\nAnalyze this opening frame. Return ONLY JSON.", image_part],
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=256,
            response_mime_type="application/json",
        ),
    )

    text = ""
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text += part.text
    return text or None


async def _analyze_hook(
    image_bytes: bytes,
    session: SessionState,
    audio_bytes: Optional[bytes] = None,
) -> CoachingEvent:
    """
    Hook evaluation: runs audio + vision hook analysis in parallel
    using one-shot generateContent (not the persistent Live session).
    """
    t_start = time.perf_counter()

    try:
        has_audio = audio_bytes is not None and len(audio_bytes) > 100
        tasks = []
        task_names = []

        if has_audio:
            tasks.append(_analyze_hook_audio(audio_bytes))
            task_names.append("audio")

        tasks.append(_analyze_hook_vision(image_bytes))
        task_names.append("vision")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        latency_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"Hook eval latency: {latency_ms:.0f}ms ({'+'.join(task_names)})")

        audio_raw = None
        vision_raw = None

        for name, result in zip(task_names, results):
            if isinstance(result, str) and result:
                try:
                    parsed = _parse_gemini_response(result)
                    # Force hook event types
                    if parsed["event"] not in ("HOOK_GOOD", "HOOK_WEAK"):
                        parsed["event"] = "HOOK_GOOD" if parsed["score"] >= 0.45 else "HOOK_WEAK"
                    logger.info(f"  Hook {name}: {parsed['event']:<14} score={parsed['score']:.2f} | {parsed.get('reasoning', '')}")
                    if name == "audio":
                        audio_raw = parsed
                    else:
                        vision_raw = parsed
                except Exception as e:
                    logger.error(f"  Hook {name} parse failed: {e}")
            elif isinstance(result, Exception):
                logger.error(f"  Hook {name} error: {result}")

        if not audio_raw and not vision_raw:
            return HOOK_FALLBACK

        raw = _merge_hook_results(audio_raw, vision_raw)

        score = raw["score"]
        filled = int(score * 10)
        score_bar = "█" * filled + "░" * (10 - filled) + f"{int(score * 100):3d}%"
        reasoning = raw.get("reasoning", "")

        event = CoachingEvent(
            event=EventType(raw["event"]),
            score=score,
            message=raw.get("message", "")[:14],
            detail=score_bar,
            buzz=raw.get("buzz", False),
            buzz_pattern=raw.get("buzz_pattern", "single"),
            confidence=raw.get("confidence", 1.0),
            phase="hook",
            reasoning=reasoning,
        )

        logger.info(f"Hook result: {event.event.value} score={event.score:.2f} | {reasoning}")

        session.hook_results.append(event)
        session.record(event)
        return event

    except Exception as e:
        logger.error(f"Hook analysis failed: {type(e).__name__}: {e}")
        return HOOK_FALLBACK


async def analyze(
    image_bytes: bytes,
    audio: AudioMetrics,
    session: SessionState,
    audio_bytes: Optional[bytes] = None,
) -> CoachingEvent:
    """
    Core inference. When audio is available, runs BOTH:
      1. Native audio model (Live API) — hears tone, pitch, emotion
      2. Vision model (generateContent) — sees face, posture, movement
    Then merges results. Falls back to vision-only when no audio.

    During hook phase (first 3s), branches to _analyze_hook() instead.
    """
    # Check/update phase transition
    prev_phase = session.phase
    session.update_phase()

    # During hook phase: buffer data and return a "collecting" placeholder
    if session.phase == "hook":
        session.hook_buffer_image = image_bytes
        if audio_bytes and len(audio_bytes) > 100:
            session.hook_buffer_audio = audio_bytes
        logger.info("Hook phase: collecting data...")
        collecting = CoachingEvent(
            event=EventType.GOOD,
            score=0.5,
            message="HOOK EVAL...",
            detail="Collecting...",
            buzz=False,
            phase="hook",
            reasoning="Analyzing your opening...",
        )
        return collecting

    # Phase just transitioned from hook → normal: run the hook analysis once
    if prev_phase == "hook" and not session.hook_evaluated:
        session.hook_evaluated = True
        hook_image = session.hook_buffer_image or image_bytes
        hook_audio = session.hook_buffer_audio if session.hook_buffer_audio else audio_bytes
        hook_event = await _analyze_hook(hook_image, session, hook_audio)
        # Clear buffers
        session.hook_buffer_image = b""
        session.hook_buffer_audio = b""
        return hook_event

    has_audio = audio_bytes is not None and len(audio_bytes) > 100
    t_start = time.perf_counter()

    try:
        if has_audio:
            # Run audio + vision in parallel
            turn_prompt = _build_turn_prompt(session)
            audio_task = _live_coach.analyze(image_bytes, audio_bytes, turn_prompt)
            vision_task = _analyze_vision_only(image_bytes, session)
            audio_text, vision_text = await asyncio.gather(
                audio_task, vision_task, return_exceptions=True
            )

            latency_ms = (time.perf_counter() - t_start) * 1000
            logger.info(f"Gemini latency: {latency_ms:.0f}ms (audio+vision parallel)")

            # Parse whichever succeeded
            audio_raw = None
            vision_raw = None

            if isinstance(audio_text, str) and audio_text:
                try:
                    audio_raw = _parse_gemini_response(audio_text)
                    logger.info(f"  Audio:  {audio_raw['event']:<14} score={audio_raw['score']:.2f} | {audio_raw.get('reasoning', '')}")
                except Exception as e:
                    logger.error(f"  Audio parse failed: {e}")

            if isinstance(vision_text, str) and vision_text:
                try:
                    vision_raw = _parse_gemini_response(vision_text)
                    logger.info(f"  Vision: {vision_raw['event']:<14} score={vision_raw['score']:.2f} | {vision_raw.get('reasoning', '')}")
                except Exception as e:
                    logger.error(f"  Vision parse failed: {e}")

            if audio_raw and vision_raw:
                raw = _merge_results(audio_raw, vision_raw)
            elif audio_raw:
                raw = audio_raw
            elif vision_raw:
                raw = vision_raw
            else:
                logger.error("Both audio and vision failed")
                if isinstance(audio_text, Exception):
                    logger.error(f"  Audio error: {audio_text}")
                if isinstance(vision_text, Exception):
                    logger.error(f"  Vision error: {vision_text}")
                return FALLBACK
        else:
            # Vision-only fallback
            response_text = await _analyze_vision_only(image_bytes, session)
            latency_ms = (time.perf_counter() - t_start) * 1000
            logger.info(f"Gemini latency: {latency_ms:.0f}ms (vision-only)")

            if not response_text:
                logger.error("Empty response from Gemini")
                return FALLBACK

            raw = _parse_gemini_response(response_text)

        score = raw["score"]
        filled = int(score * 10)
        score_bar = "█" * filled + "░" * (10 - filled) + f"{int(score * 100):3d}%"

        reasoning = raw.get("reasoning", "")
        event = CoachingEvent(
            event=EventType(raw["event"]),
            score=score,
            message=raw["message"],
            detail=score_bar,
            buzz=raw["buzz"],
            buzz_pattern=raw.get("buzz_pattern", "single"),
            confidence=raw.get("confidence", 1.0),
            phase="normal",
            reasoning=reasoning,
        )

        logger.info(
            f"Event: {event.event.value:<14} "
            f"Score: {event.score:.2f}  "
            f"Confidence: {event.confidence:.2f}  "
            f"| {reasoning}"
        )

        event = _apply_cooldown(event, session)
        session.record(event)
        return event

    except json.JSONDecodeError as e:
        logger.error(f"Non-JSON response: {e}")
        return FALLBACK

    except ValueError as e:
        logger.error(f"Validation failed: {e}")
        return FALLBACK

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Gemini call failed: {type(e).__name__}: {error_msg[:200]}")
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            import re
            match = re.search(r'retryDelay.*?(\d+)', error_msg)
            wait = int(match.group(1)) if match else 15
            logger.warning(f"Rate limited — waiting {wait}s")
            await asyncio.sleep(wait)
        return FALLBACK
