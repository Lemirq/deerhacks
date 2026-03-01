"""
pi/main.py — Main loop for the Neuro-Sync Pi client.

This is the entry point for the Raspberry Pi side of the project.
Run this on the Pi after the laptop server is already running:

    cd ~/neuro-sync/pi
    python3 main.py

What the loop does every ~4 seconds:
  1. capture.py   → grab one JPEG frame from the USB webcam
  2. audio.py     → sample the sound sensor for 2 seconds → compute metrics
  3. POST both to the laptop server at /analyze over WiFi
  4. Receive CoachingEvent JSON back
  5. feedback.py  → update LCD + fire buzzer if needed
  6. Log everything to terminal
  7. Repeat

The audio sampling in step 2 IS the loop timing — it takes 2 seconds
to sample, then Gemini takes ~0.5-1.5s, so total loop time is ~3-4s.
That's the right cadence — fast enough to feel live, slow enough to
give the creator time to actually respond to feedback before the next event.

Environment:
  Set SERVER_URL in pi/.env to your laptop's local IP before running.
  Example: SERVER_URL=http://192.168.1.45:8000
  The laptop server prints this URL for you when it starts.
"""

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

import capture
import audio
import feedback
import lcd

load_dotenv()


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("neuro-sync.pi")


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SERVER_URL     = os.getenv("SERVER_URL", "http://localhost:8000")
SESSION_ID     = f"pi_{uuid.uuid4().hex[:8]}"   # Unique ID per run
REQUEST_TIMEOUT= 12.0    # Seconds before giving up on a server request
MAX_RETRIES    = 3       # How many times to retry a failed request before showing error
SESSIONS_DIR   = Path(__file__).parent.parent / "sessions"


# ─────────────────────────────────────────────
# SESSION LOG
# Every event is appended here and saved to JSON on exit.
# Useful for the post-session review.
# ─────────────────────────────────────────────

class SessionLog:
    def __init__(self, session_id: str):
        self.session_id  = session_id
        self.start_time  = time.time()
        self.events: list[dict] = []

    def record(self, event: dict, audio_metrics: dict, latency_ms: float):
        self.events.append({
            "t":         round(time.time() - self.start_time, 2),
            "event":     event.get("event"),
            "score":     event.get("score"),
            "message":   event.get("message"),
            "wpm":       audio_metrics.get("estimated_wpm"),
            "volume":    audio_metrics.get("volume_rms"),
            "silence":   audio_metrics.get("silence_ratio"),
            "latency_ms": round(latency_ms, 1),
        })

    def save(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = SESSIONS_DIR / f"{ts}_{self.session_id}.json"

        with open(path, "w") as f:
            json.dump({
                "session_id":  self.session_id,
                "start_time":  datetime.fromtimestamp(self.start_time).isoformat(),
                "total_events": len(self.events),
                "events":       self.events,
            }, f, indent=2)

        logger.info(f"Session saved → {path}")
        return path

    def print_summary(self):
        if not self.events:
            print("  No events recorded.")
            return

        scores    = [e["score"] for e in self.events if e["score"] is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

        from collections import Counter
        counts = Counter(e["event"] for e in self.events)

        duration = time.time() - self.start_time
        mins     = int(duration // 60)
        secs     = int(duration % 60)

        print(f"\n{'━' * 44}")
        print(f"  SESSION SUMMARY — {self.session_id}")
        print(f"{'━' * 44}")
        print(f"  Duration:     {mins}m {secs}s")
        print(f"  Total events: {len(self.events)}")
        print(f"  Avg score:    {avg_score:.2f}")
        print(f"  Event breakdown:")
        for event_type, count in sorted(counts.items()):
            bar = "█" * count
            print(f"    {event_type:<14} {bar} ({count})")

        if scores:
            best  = max(self.events, key=lambda e: e["score"] or 0)
            worst = min(self.events, key=lambda e: e["score"] or 1)
            print(f"  Best moment:  t={best['t']}s  score={best['score']:.2f}  '{best['message']}'")
            print(f"  Worst moment: t={worst['t']}s  score={worst['score']:.2f}  '{worst['message']}'")

        print(f"{'━' * 44}\n")


# ─────────────────────────────────────────────
# SERVER HEALTH CHECK
# Called once on startup to verify the laptop server is reachable
# and has a valid Gemini key configured.
# ─────────────────────────────────────────────

def check_server(client: httpx.Client) -> bool:
    """
    Pings the server /health endpoint.
    Returns True if server is up and Gemini key is configured.
    Prints clear error messages if not.
    """
    try:
        resp = client.get(f"{SERVER_URL}/health", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        if data.get("gemini_key") != "configured":
            logger.error("Server is running but GEMINI_API_KEY is not set.")
            logger.error("→ Edit server/.env and restart the server.")
            return False

        logger.info(f"Server healthy at {SERVER_URL} ✓")
        return True

    except httpx.ConnectError:
        logger.error(f"Cannot connect to server at {SERVER_URL}")
        logger.error("→ Is the laptop server running?  cd server && python main.py")
        logger.error("→ Are the Pi and laptop on the same WiFi network?")
        logger.error(f"→ Is SERVER_URL correct in pi/.env?  Current: {SERVER_URL}")
        return False

    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}: {e}")
        return False


# ─────────────────────────────────────────────
# ANALYZE REQUEST
# Sends the JPEG frame + audio metrics to the server.
# Returns the CoachingEvent dict, or None on failure.
# ─────────────────────────────────────────────

def send_analyze_request(
    client:        httpx.Client,
    jpeg_bytes:    bytes,
    audio_metrics: dict,
    session_id:    str,
) -> tuple[dict | None, float]:
    """
    POSTs to /analyze. Returns (CoachingEvent dict, latency_ms).
    Returns (None, 0) on failure after MAX_RETRIES attempts.

    Uses multipart form:
      - frame:         JPEG file upload
      - audio_metrics: JSON string
      - session_id:    string
    """
    t_start = time.perf_counter()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.post(
                f"{SERVER_URL}/analyze",
                files={"frame": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                data={
                    "audio_metrics": json.dumps(audio_metrics),
                    "session_id":    session_id,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()

            latency_ms = (time.perf_counter() - t_start) * 1000
            return resp.json(), latency_ms

        except httpx.TimeoutException:
            logger.warning(f"Request timed out (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(0.5)

        except httpx.HTTPStatusError as e:
            logger.error(f"Server returned {e.response.status_code}: {e.response.text[:200]}")
            return None, 0.0

        except httpx.ConnectError:
            logger.error("Lost connection to server.")
            if attempt < MAX_RETRIES:
                time.sleep(1.0)

        except json.JSONDecodeError:
            logger.error("Server returned non-JSON response.")
            return None, 0.0

        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return None, 0.0

    logger.error(f"All {MAX_RETRIES} attempts failed.")
    return None, 0.0


# ─────────────────────────────────────────────
# STARTUP BANNER
# ─────────────────────────────────────────────

def print_banner():
    print()
    print("━" * 44)
    print("  ◈  NEURO-SYNC  Pi Client")
    print("━" * 44)
    print(f"  Session ID:  {SESSION_ID}")
    print(f"  Server URL:  {SERVER_URL}")
    print(f"  Press Ctrl+C to stop and save session.")
    print("━" * 44)
    print()


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def main():
    print_banner()

    # Play startup animation on the LCD
    lcd.startup_animation()

    session_log = SessionLog(SESSION_ID)

    # Use a persistent httpx.Client for connection reuse across requests.
    # This avoids re-doing the TCP handshake on every loop iteration (~50ms saving).
    with httpx.Client() as client:

        # ── Health check ───────────────────────────────────────────────
        lcd.show("Checking server", "please wait...", "STARTUP")

        if not check_server(client):
            lcd.show_error("Server offline")
            lcd.show("Check laptop &", "WiFi connection", "ERROR")
            logger.error("Startup failed — fix server connection and restart.")
            sys.exit(1)

        lcd.show("Server OK!", "Starting loop...", "GOOD")
        time.sleep(1.0)

        # ── Reset session state on server ──────────────────────────────
        try:
            client.delete(f"{SERVER_URL}/session/{SESSION_ID}", timeout=3.0)
        except Exception:
            pass  # Non-critical — server may not have this session yet

        logger.info("Entering main loop. Stand in front of the camera.\n")
        lcd.show("NEURO-SYNC", "Stand in frame!", "STARTUP")
        time.sleep(2.0)

        loop_count    = 0
        error_streak  = 0
        MAX_ERROR_STREAK = 5    # Show persistent error after this many consecutive failures

        try:
            while True:
                loop_count += 1
                t_loop_start = time.time()

                # ── Step 1: Capture frame ──────────────────────────────
                try:
                    jpeg_bytes = capture.capture_jpeg()
                except RuntimeError as e:
                    logger.error(f"Camera error: {e}")
                    feedback.apply_error("Camera error")
                    time.sleep(2.0)
                    continue

                # ── Step 2: Sample audio (this takes SAMPLE_WINDOW_SEC) ──
                # Show "analyzing" on LCD while we wait for audio sampling
                lcd.show("Listening...", f"loop #{loop_count}", "IDLE")
                audio_metrics = audio.get_audio_metrics()

                # ── Step 3: Send to server ─────────────────────────────
                lcd.show("Asking AI...", "", "IDLE")
                event, latency_ms = send_analyze_request(
                    client, jpeg_bytes, audio_metrics, SESSION_ID
                )

                # ── Step 4: Handle failure ─────────────────────────────
                if event is None:
                    error_streak += 1
                    logger.warning(f"No response from server (streak: {error_streak})")

                    if error_streak >= MAX_ERROR_STREAK:
                        feedback.apply_error("No server resp.")
                    else:
                        # Don't change LCD — show last known state
                        pass
                    continue

                error_streak = 0  # Reset on success

                # ── Step 5: Drive hardware ─────────────────────────────
                feedback.apply(event)

                # ── Step 6: Log ────────────────────────────────────────
                session_log.record(event, audio_metrics, latency_ms)

                loop_duration = time.time() - t_loop_start
                logger.info(
                    f"Loop #{loop_count:04d} | "
                    f"{event.get('event', '?'):<14} | "
                    f"score={event.get('score', 0):.2f} | "
                    f"wpm≈{audio_metrics['estimated_wpm']:3d} | "
                    f"vol={audio_metrics['volume_rms']:.3f} | "
                    f"server={latency_ms:.0f}ms | "
                    f"total={loop_duration:.1f}s"
                )

        except KeyboardInterrupt:
            print("\n\n  Stopping...")

    # ── Shutdown ───────────────────────────────────────────────────────
    lcd.show("Saving session", "please wait...", "STARTUP")

    saved_path = session_log.save()
    session_log.print_summary()

    lcd.show("Session saved!", f"{len(session_log.events)} events", "GOOD")
    time.sleep(2.0)
    lcd.clear()

    feedback.cleanup()
    capture.release_camera()

    print(f"  Session log saved to: {saved_path}")
    print("  Done. Goodbye.\n")


if __name__ == "__main__":
    main()
