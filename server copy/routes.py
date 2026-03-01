"""
routes.py — FastAPI route definitions for Neuro-Sync server.

Single endpoint: POST /analyze
  - Receives: JPEG image (multipart) + audio metrics (JSON form field)
  - Returns:  CoachingEvent JSON

The Pi calls this endpoint every ~3-4 seconds during a recording session.

Why one endpoint?
  Keeping it simple. The Pi has one job: send frame + audio, get coaching back.
  We don't need REST-style CRUD here — this is a real-time inference pipeline.
"""

import json
import logging
import time
from io import BytesIO

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image

from models import AudioMetrics, CoachingEvent, EventType, SessionState
from gemini_coach import analyze

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────
# SESSION STORE
# In a real app this would be Redis or a DB.
# For a hackathon, an in-memory dict keyed by session_id is fine.
# The Pi sends a session_id with every request so the server
# can maintain state (cooldowns, history) across the loop.
# ─────────────────────────────────────────────

_sessions: dict[str, SessionState] = {}

def get_or_create_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = SessionState()
        logger.info(f"New session created: {session_id}")
    return _sessions[session_id]


# ─────────────────────────────────────────────
# IMAGE VALIDATION + PREPROCESSING
# Before sending to Gemini, validate the image is real
# and resize it if it's too large (keeps API costs down
# and latency low — Gemini doesn't need a 4K frame)
# ─────────────────────────────────────────────

MAX_IMAGE_BYTES  = 5 * 1024 * 1024   # 5MB hard limit
TARGET_MAX_WIDTH = 640                # Resize down to this if wider
JPEG_QUALITY     = 82                 # Re-encode quality after resize

def validate_and_preprocess_image(raw_bytes: bytes) -> bytes:
    """
    Validates and optionally resizes the incoming JPEG.
    Returns processed JPEG bytes ready for Gemini.
    
    Raises HTTPException if the image is invalid.
    """
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large: {len(raw_bytes)} bytes (max {MAX_IMAGE_BYTES})"
        )

    try:
        img = Image.open(BytesIO(raw_bytes))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not decode image. Must be a valid JPEG."
        )

    # Convert to RGB if needed (handles grayscale or RGBA webcam frames)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if too wide — preserves aspect ratio
    if img.width > TARGET_MAX_WIDTH:
        ratio  = TARGET_MAX_WIDTH / img.width
        new_h  = int(img.height * ratio)
        img    = img.resize((TARGET_MAX_WIDTH, new_h), Image.LANCZOS)
        logger.debug(f"Resized image to {img.width}x{img.height}")

    # Re-encode to JPEG bytes
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────
# AUDIO METRICS PARSING
# The Pi sends audio_metrics as a JSON string in a form field
# (not a separate request body) because multipart forms can only
# have one structured file upload at a time.
# ─────────────────────────────────────────────

def parse_audio_metrics(raw_json: str) -> AudioMetrics:
    """
    Parses and validates the audio_metrics JSON string from the form field.
    Raises HTTPException with a clear message if anything is malformed.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"audio_metrics is not valid JSON: {e}"
        )

    try:
        return AudioMetrics(**data)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"audio_metrics validation failed: {e}"
        )


# ─────────────────────────────────────────────
# POST /analyze — THE MAIN ENDPOINT
# ─────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=CoachingEvent,
    summary="Analyze a webcam frame + audio metrics",
    description="""
    The Pi calls this every ~3-4 seconds during a recording session.
    
    Multipart form fields:
    - `frame`:         JPEG image file (webcam capture)
    - `audio_metrics`: JSON string with volume_rms, silence_ratio, estimated_wpm, etc.
    - `session_id`:    String ID for this recording session (e.g. "pi_session_001")
    
    Returns a CoachingEvent JSON with event type, score, LCD message, and buzz instructions.
    """,
)
async def analyze_frame(
    frame:         UploadFile = File(...,  description="JPEG webcam frame"),
    audio_metrics: str        = Form(...,  description="JSON string of AudioMetrics"),
    session_id:    str        = Form("default_session", description="Session identifier"),
):
    t_request_start = time.perf_counter()

    # ── 1. Read and validate image ──────────────────────────────────────
    raw_image_bytes = await frame.read()

    if not raw_image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    image_bytes = validate_and_preprocess_image(raw_image_bytes)

    # ── 2. Parse audio metrics ──────────────────────────────────────────
    audio = parse_audio_metrics(audio_metrics)

    # ── 3. Get or create session state ─────────────────────────────────
    session = get_or_create_session(session_id)

    # ── 4. Run Gemini inference ─────────────────────────────────────────
    event = await analyze(
        image_bytes=image_bytes,
        audio=audio,
        session=session,
    )

    # ── 5. Log timing ────────────────────────────────────────────────────
    total_ms = (time.perf_counter() - t_request_start) * 1000
    logger.info(
        f"[{session_id}] /analyze → {event.event.value:<14} "
        f"score={event.score:.2f}  total={total_ms:.0f}ms"
    )

    return event


# ─────────────────────────────────────────────
# GET /session/{session_id}/summary
# Returns a summary of the current session stats.
# Useful for the post-session review.
# ─────────────────────────────────────────────

@router.get(
    "/session/{session_id}/summary",
    summary="Get session summary",
)
async def session_summary(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    session = _sessions[session_id]
    history = session.history

    if not history:
        return {"session_id": session_id, "events": 0, "message": "No events recorded yet."}

    # Count events by type
    counts = {}
    for e in EventType:
        counts[e.value] = sum(1 for h in history if h.event == e)

    # Find worst moment
    worst = min(history, key=lambda e: e.score)

    # Find best moment
    best = max(history, key=lambda e: e.score)

    return {
        "session_id":    session_id,
        "total_events":  len(history),
        "avg_score":     round(session.average_score(len(history)), 3),
        "score_trend":   session.recent_score_trend(),
        "event_counts":  counts,
        "worst_moment":  {"score": worst.score, "event": worst.event.value, "message": worst.message},
        "best_moment":   {"score": best.score,  "event": best.event.value,  "message": best.message},
        "consecutive_good": session.consecutive_good,
        "consecutive_bad":  session.consecutive_bad,
    }


# ─────────────────────────────────────────────
# DELETE /session/{session_id}
# Clears the session state. Call this when starting a new take.
# ─────────────────────────────────────────────

@router.delete(
    "/session/{session_id}",
    summary="Reset session state",
)
async def reset_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
        logger.info(f"Session reset: {session_id}")
        return {"message": f"Session '{session_id}' cleared."}
    return {"message": f"Session '{session_id}' did not exist — nothing to clear."}


# ─────────────────────────────────────────────
# GET /health
# The Pi calls this once on startup to confirm the server is live
# and the Gemini key is configured before starting the main loop.
# ─────────────────────────────────────────────

@router.get("/health", summary="Health check")
async def health_check():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY", "")
    return {
        "status":      "ok",
        "gemini_key":  "configured" if key and key != "your_key_here" else "MISSING",
        "sessions":    len(_sessions),
    }
