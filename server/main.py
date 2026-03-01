from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import instagram_routes

app = FastAPI(title="Deerhacks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
"""
server/main.py — FastAPI application entry point.

Run this on your LAPTOP (not the Pi):
    cd server/
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

The Pi will connect to this server over WiFi using your laptop's local IP.
This script prints that IP for you on startup so you can paste it into the Pi's .env.

What this file does:
  - Creates the FastAPI app
  - Mounts the routes from routes.py
  - Configures logging so you can see every event in the terminal
  - Prints a startup banner with the local IP + the URL the Pi needs
  - Runs the uvicorn server
"""

import logging
import os
import socket
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes import router

load_dotenv()


# ─────────────────────────────────────────────
# LOGGING
# Format: timestamp | level | logger name | message
# All INFO and above goes to stdout so you can watch events live
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Quiet down the noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # suppress per-request access logs (we have our own)

logger = logging.getLogger("neuro-sync.server")


# ─────────────────────────────────────────────
# LOCAL IP HELPER
# Finds your laptop's LAN IP so the Pi knows where to connect.
# Much easier than asking the user to find it manually.
# ─────────────────────────────────────────────

def get_local_ip() -> str:
    """
    Gets the laptop's local network IP address.
    Uses a UDP connect trick — doesn't actually send any packets,
    just forces the OS to pick the right network interface.
    Falls back to localhost if something goes wrong.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ─────────────────────────────────────────────
# STARTUP / SHUTDOWN LIFECYCLE
# FastAPI lifespan context manager — runs setup before
# the server accepts requests, and cleanup on shutdown.
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────────
    local_ip   = get_local_ip()
    port       = int(os.getenv("SERVER_PORT", 8000))
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    print()
    print("━" * 52)
    print("  ◈  NEURO-SYNC  SERVER")
    print("━" * 52)

    # Gemini key check
    if not gemini_key or gemini_key == "your_key_here":
        print("  ✗  GEMINI_API_KEY not set in server/.env")
        print("     Get one at: https://aistudio.google.com")
        print("━" * 52)
        # Don't exit — let the server start so /health returns the error
    else:
        print(f"  ✓  Gemini API key loaded")

    print(f"  ✓  Server running at:  http://{local_ip}:{port}")
    print()
    print(f"  → On the Pi, set SERVER_URL in pi/.env to:")
    print(f"     http://{local_ip}:{port}")
    print()
    print(f"  Endpoints:")
    print(f"     POST   http://{local_ip}:{port}/analyze")
    print(f"     GET    http://{local_ip}:{port}/health")
    print(f"     GET    http://{local_ip}:{port}/session/{{id}}/summary")
    print(f"     GET    http://{local_ip}:{port}/session/{{id}}/report")
    print(f"     DELETE http://{local_ip}:{port}/session/{{id}}")
    print(f"     GET    http://{local_ip}:{port}/reports/{{device_id}}")
    print(f"     GET    http://{local_ip}:{port}/reports/{{device_id}}/{{session_id}}")
    print(f"     GET    http://{local_ip}:{port}/docs   ← interactive API docs")
    print("━" * 52)
    print()
    print("  Waiting for Pi to connect...")
    print("  (Live event log will appear below)\n")

    yield  # Server runs here — everything above is startup, below is shutdown

    # ── SHUTDOWN ──────────────────────────────────────────────────────────
    print("\n  Server shutting down.")


# ─────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="Neuro-Sync Server",
    description="Real-time creator coaching via Gemini Vision. Runs on laptop, Pi connects over WiFi.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow requests from any origin (the Pi's local IP will vary)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(instagram_routes.router, prefix="/api/instagram", tags=["instagram"])
# Mount all routes from routes.py
app.include_router(router)


# ─────────────────────────────────────────────
# REQUEST TIMING MIDDLEWARE
# Logs every request with its duration.
# Helps you spot if Gemini is getting slow mid-demo.
# ─────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    # Only log /analyze calls (skip /health polling noise)
    if request.url.path == "/analyze":
        status = response.status_code
        symbol = "✓" if status < 400 else "✗"
        logger.info(f"{symbol} {request.method} {request.url.path} → {status}  ({duration_ms:.0f}ms)")

    return response


# ─────────────────────────────────────────────
# GLOBAL ERROR HANDLER
# Catches any unhandled exception and returns a clean JSON error
# instead of crashing the server mid-demo.
# ─────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception on {request.url.path}: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}"},
    )


# ─────────────────────────────────────────────
# ENTRY POINT
# Run directly: python main.py
# Or via uvicorn: uvicorn main:app --reload
# ─────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", 8000)),
        reload=True,       # Auto-reload when you edit files — great for dev
        reload_dirs=["."], # Only watch the server/ directory
        log_level="warning",  # Uvicorn's own logs — we handle ours above
    )
