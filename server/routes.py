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
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image

from models import AudioMetrics, CoachingEvent, EventType, SessionState
from gemini_coach import analyze

# ─────────────────────────────────────────────
# REPORT STORAGE
# Persists session reports as JSON files under server/reports/{device_id}/
# ─────────────────────────────────────────────

REPORTS_DIR = Path(__file__).parent / "reports"


def _save_report(device_id: str, session_id: str, report_data: dict):
    """Save a report JSON file to disk for a given device and session."""
    device_dir = REPORTS_DIR / device_id
    device_dir.mkdir(parents=True, exist_ok=True)
    report_path = device_dir / f"{session_id}.json"
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)
    logger.info(f"Report saved: {report_path}")


def _load_report(device_id: str, session_id: str) -> dict | None:
    """Load a saved report from disk. Returns None if not found."""
    report_path = REPORTS_DIR / device_id / f"{session_id}.json"
    if not report_path.exists():
        return None
    with open(report_path, "r") as f:
        return json.load(f)

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
    audio_clip:    UploadFile = File(None, description="WAV audio clip for native audio analysis"),
    device_id:     str        = Form(None, description="Device UUID from iOS client"),
):
    t_request_start = time.perf_counter()

    # ── 1. Read and validate image ──────────────────────────────────────
    raw_image_bytes = await frame.read()

    if not raw_image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    image_bytes = validate_and_preprocess_image(raw_image_bytes)

    # ── 1b. Read audio clip if provided ─────────────────────────────────
    audio_bytes = None
    if audio_clip is not None:
        audio_bytes = await audio_clip.read()
        if not audio_bytes:
            audio_bytes = None

    # ── 2. Parse audio metrics ──────────────────────────────────────────
    audio = parse_audio_metrics(audio_metrics)

    # ── 3. Get or create session state ─────────────────────────────────
    session = get_or_create_session(session_id)

    # ── 3a. Store device_id if provided ──────────────────────────────
    if device_id and not session.device_id:
        session.device_id = device_id

    # ── 3b. Set recording start time on first call ───────────────────
    if session.recording_start_time == 0.0:
        session.recording_start_time = time.time()

    # ── 4. Run Gemini inference ─────────────────────────────────────────
    event = await analyze(
        image_bytes=image_bytes,
        audio=audio,
        session=session,
        audio_bytes=audio_bytes,
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
# GET /session/{session_id}/report
# Comprehensive post-session report with hook evaluation,
# full timeline, stats, best/worst moments, and problem zones.
# ─────────────────────────────────────────────

@router.get(
    "/session/{session_id}/report",
    summary="Get comprehensive session report",
)
async def session_report(session_id: str, device_id: Optional[str] = Query(None, description="Device UUID — if provided, overrides session device_id")):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    session = _sessions[session_id]
    history = session.history

    if not history:
        return {"session_id": session_id, "events": 0, "message": "No events recorded yet."}

    # ── Hook evaluation summary ──────────────────────────────────────
    hook_events = session.hook_results
    hook_evaluation = None
    if hook_events:
        hook_scores = [e.score for e in hook_events]
        hook_avg = sum(hook_scores) / len(hook_scores)
        has_weak = any(e.event == EventType.HOOK_WEAK for e in hook_events)
        hook_evaluation = {
            "verdict": "WEAK" if has_weak else "STRONG",
            "avg_score": round(hook_avg, 3),
            "evaluations": [
                {
                    "event": e.event.value,
                    "score": e.score,
                    "message": e.message,
                    "reasoning": e.reasoning,
                    "timestamp": e.timestamp,
                }
                for e in hook_events
            ],
        }

    # ── Full timeline ────────────────────────────────────────────────
    timeline = []
    for i, e in enumerate(history):
        frame_index = i + 1
        timeline.append({
            "frame_index": frame_index,
            "frame_files": f"{frame_index:04d}.jpg / {frame_index:04d}.wav / {frame_index:04d}.json",
            "event": e.event.value,
            "score": e.score,
            "message": e.message,
            "phase": e.phase,
            "reasoning": e.reasoning,
            "confidence": e.confidence,
            "buzz": e.buzz,
            "timestamp": e.timestamp,
        })

    # ── Overall stats ────────────────────────────────────────────────
    all_scores = [e.score for e in history]
    normal_events = [e for e in history if e.phase == "normal"]
    normal_scores = [e.score for e in normal_events] if normal_events else all_scores

    counts = {}
    for et in EventType:
        counts[et.value] = sum(1 for h in history if h.event == et)

    stats = {
        "total_events": len(history),
        "avg_score": round(sum(all_scores) / len(all_scores), 3),
        "min_score": round(min(all_scores), 3),
        "max_score": round(max(all_scores), 3),
        "normal_avg_score": round(sum(normal_scores) / len(normal_scores), 3) if normal_scores else 0.0,
        "event_counts": counts,
    }

    # ── Best / worst moments ─────────────────────────────────────────
    best_idx = max(range(len(history)), key=lambda i: history[i].score)
    worst_idx = min(range(len(history)), key=lambda i: history[i].score)
    best_moments = {
        "frame_index": best_idx + 1,
        "event": history[best_idx].event.value,
        "score": history[best_idx].score,
        "message": history[best_idx].message,
        "reasoning": history[best_idx].reasoning,
    }
    worst_moments = {
        "frame_index": worst_idx + 1,
        "event": history[worst_idx].event.value,
        "score": history[worst_idx].score,
        "message": history[worst_idx].message,
        "reasoning": history[worst_idx].reasoning,
    }

    # ── Problem zones (consecutive low-score stretches) ──────────────
    problem_zones = []
    LOW_THRESHOLD = 0.60
    zone_start = None
    for i, e in enumerate(history):
        if e.score < LOW_THRESHOLD:
            if zone_start is None:
                zone_start = i
        else:
            if zone_start is not None and (i - zone_start) >= 2:
                zone_scores = [history[j].score for j in range(zone_start, i)]
                problem_zones.append({
                    "start_frame": zone_start + 1,
                    "end_frame": i,
                    "length": i - zone_start,
                    "avg_score": round(sum(zone_scores) / len(zone_scores), 3),
                    "events": [history[j].event.value for j in range(zone_start, i)],
                })
            zone_start = None
    # Handle zone that extends to end
    if zone_start is not None and (len(history) - zone_start) >= 2:
        zone_scores = [history[j].score for j in range(zone_start, len(history))]
        problem_zones.append({
            "start_frame": zone_start + 1,
            "end_frame": len(history),
            "length": len(history) - zone_start,
            "avg_score": round(sum(zone_scores) / len(zone_scores), 3),
            "events": [history[j].event.value for j in range(zone_start, len(history))],
        })

    report_data = {
        "session_id": session_id,
        "hook_evaluation": hook_evaluation,
        "stats": stats,
        "best_moment": best_moments,
        "worst_moment": worst_moments,
        "problem_zones": problem_zones,
        "timeline": timeline,
    }

    # ── Persist report to disk if we know the device ─────────────────
    effective_device_id = device_id or session.device_id
    if effective_device_id:
        _save_report(effective_device_id, session_id, report_data)

    return report_data


# ─────────────────────────────────────────────
# GET /reports/{device_id} — list all saved reports for a device
# GET /reports/{device_id}/{session_id} — full saved report
# ─────────────────────────────────────────────

@router.get(
    "/reports/{device_id}",
    summary="List saved reports for a device (newest first)",
)
async def list_device_reports(device_id: str):
    device_dir = REPORTS_DIR / device_id
    if not device_dir.exists():
        return []

    summaries = []
    for report_file in device_dir.glob("*.json"):
        try:
            with open(report_file, "r") as f:
                data = json.load(f)
            # Extract lightweight summary fields
            stats = data.get("stats", {})
            timeline = data.get("timeline", [])
            hook_eval = data.get("hook_evaluation")
            timestamp = timeline[0]["timestamp"] if timeline else 0.0
            summaries.append({
                "session_id": data.get("session_id", report_file.stem),
                "timestamp": timestamp,
                "avg_score": stats.get("avg_score", 0.0),
                "hook_verdict": hook_eval.get("verdict") if hook_eval else None,
                "total_events": stats.get("total_events", 0),
            })
        except Exception as e:
            logger.warning(f"Skipping corrupt report {report_file}: {e}")
            continue

    # Sort newest first
    summaries.sort(key=lambda s: s["timestamp"], reverse=True)
    return summaries


@router.get(
    "/reports/{device_id}/{session_id}",
    summary="Get a specific saved report for a device",
)
async def get_saved_report(device_id: str, session_id: str):
    report = _load_report(device_id, session_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found for device '{device_id}', session '{session_id}'.")
    return report


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
