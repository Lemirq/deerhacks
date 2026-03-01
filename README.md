# Neuro-Sync — AI-Powered Creator Coaching

> **Real-time feedback for content creators. Phone + Gemini AI.**
> Open the app, hit record, get live coaching on your energy, pacing, eye contact, and hook quality — while you're still filming.

---

## What It Does

Most creators film 10 takes, pick the least-bad one, and wonder why it still flops. Neuro-Sync fixes the act of recording itself — not in post.

While you record on your phone, the camera frame and microphone audio are streamed to a FastAPI server running Gemini's native audio + vision models. The AI analyzes your energy, pacing, facial expression, and body language in real-time and sends coaching events back to the app — color-coded overlays, haptic buzzes, and actionable messages you can react to mid-take.

**3-2-1 Countdown** → **Hook Evaluation** (first 3 seconds judged by a doom-scroller persona) → **Live Coaching** → **Post-Session Report**

---

## Architecture

```
┌─────────────────────────────┐         ┌─────────────────────────────────┐
│         iOS App             │         │       FastAPI Server            │
│        (Swift)              │         │        (Laptop)                 │
│                             │         │                                 │
│  ┌───────────┐              │  HTTP   │  ┌───────────────────────────┐  │
│  │ Camera    │──┐           │ ──────▶ │  │  routes.py                │  │
│  │ (phone)   │  │ JPEG +    │         │  │  POST /analyze            │  │
│  └───────────┘  │ WAV +     │         │  │  GET  /session/{id}/report│  │
│  ┌───────────┐  │ metrics   │         │  └──────────┬────────────────┘  │
│  │ Mic       │──┘           │         │             │                   │
│  │ (phone)   │              │         │             ▼                   │
│  └───────────┘              │         │  ┌───────────────────────────┐  │
│                             │         │  │  gemini_coach.py          │  │
│  ┌───────────────────────┐  │         │  │                           │  │
│  │ Coaching HUD          │  │  ◀────  │  │  Audio: Live API          │  │
│  │ • Score bar           │  │  JSON   │  │  (native audio model)     │  │
│  │ • Event type + color  │  │         │  │                           │  │
│  │ • Hook verdict        │  │         │  │  Vision: generateContent  │  │
│  │ • Haptic feedback     │  │         │  │  (flash-lite)             │  │
│  └───────────────────────┘  │         │  │                           │  │
│                             │         │  │  Hook: doom-scroller eval │  │
│  ┌───────────────────────┐  │         │  └──────────┬────────────────┘  │
│  │ Post-Session Report   │  │         │             │                   │
│  │ • Hook verdict        │  │         │             ▼                   │
│  │ • Timeline            │  │         │  ┌───────────────────────────┐  │
│  │ • Problem zones       │  │         │  │  models.py                │  │
│  │ • Best/worst moments  │  │         │  │  SessionState + events    │  │
│  └───────────────────────┘  │         │  └───────────────────────────┘  │
└─────────────────────────────┘         └─────────────────────────────────┘
```

**No external hardware.** Your phone's camera and microphone are the only sensors. The laptop runs the AI inference server.

---

## How It Works

### Recording Flow

1. **Countdown** — 3-2-1-GO displayed on screen so the creator can get ready
2. **Hook Phase (0–3s)** — The first 3 seconds of audio + video are collected, then analyzed by a "bored doom-scroller" persona that judges whether the opening would make someone stay or scroll past
3. **Normal Coaching (3s+)** — Continuous real-time analysis every ~2 seconds. Audio model hears tone/energy/pace. Vision model sees face/posture/movement. Results are merged and sent back as coaching events
4. **Post-Session Report** — When recording stops, a full report is generated: hook verdict, timeline of every event, best/worst moments, and problem zones

### Coaching Events

| Event | What It Means | App Feedback |
|---|---|---|
| `GOOD` | Locked in — energy, pacing, expression all working | Green overlay |
| `SPEED_UP` | Talking too slowly, too many pauses | Red overlay + haptic |
| `VIBE_CHECK` | Face is flat, energy doesn't match words | Orange overlay + haptic |
| `RAISE_ENERGY` | Vocal energy dropping, posture bad | Red overlay + haptic |
| `VISUAL_RESET` | Completely static — need movement | Blue overlay |
| `HOOK_GOOD` | Opening grabs attention — doom-scroller would stay | Gold overlay |
| `HOOK_WEAK` | Opening is weak — doom-scroller would scroll past | Dark orange overlay + haptic |

### Gemini Models

- **Audio analysis:** `gemini-2.5-flash-native-audio` via the Live API (persistent WebSocket session). Hears tone, pitch, emotion, pacing natively — not computed metrics.
- **Vision analysis:** `gemini-2.5-flash-lite` via `generateContent`. Sees facial expression, eye contact, body language, movement.
- **Hook evaluation:** Same `gemini-2.5-flash-lite` via one-shot `generateContent` with a doom-scroller persona prompt. Runs audio + vision in parallel after the 3-second collection window.

Both audio and vision run in parallel on every analysis cycle. Results are merged with audio weighted 60% and vision 40% (audio matters more for short-form content).

---

## Project Structure

```
neuro-sync/
├── README.md
├── server/
│   ├── main.py              ← FastAPI entry point (uvicorn)
│   ├── models.py            ← EventType, CoachingEvent, SessionState, AudioMetrics
│   ├── gemini_coach.py      ← Gemini inference: audio (Live API) + vision + hook eval
│   ├── routes.py            ← POST /analyze, GET /session/{id}/report, GET /health
│   └── .env                 ← GEMINI_API_KEY goes here
│
├── ios/                     ← Swift iOS app (camera, mic, coaching HUD, reports)
│   └── ...
│
└── demo.py                  ← Desktop demo using OpenCV + Mac camera/mic (for testing)
```

---

## API Endpoints

### `POST /analyze`

The iOS app calls this every ~2-3 seconds during recording.

**Multipart form fields:**
- `frame` — JPEG image from the phone camera
- `audio_clip` — WAV audio clip from the phone microphone
- `audio_metrics` — JSON string with `volume_rms`, `silence_ratio`, `estimated_wpm`, `peak_volume`, `volume_variance`
- `session_id` — Unique session identifier

**Returns:** `CoachingEvent` JSON

```json
{
  "event": "GOOD",
  "score": 0.85,
  "message": "LOCKED IN",
  "detail": "████████░░ 85%",
  "buzz": false,
  "buzz_pattern": "single",
  "confidence": 0.92,
  "phase": "normal",
  "reasoning": "Audio: Strong energy and pace | Visual: Good eye contact"
}
```

### `GET /session/{session_id}/report`

Called when recording ends. Returns a comprehensive session report.

```json
{
  "session_id": "session_123",
  "hook_evaluation": {
    "verdict": "STRONG",
    "avg_score": 0.82,
    "evaluations": [...]
  },
  "stats": {
    "total_events": 45,
    "avg_score": 0.76,
    "min_score": 0.42,
    "max_score": 0.95,
    "event_counts": {"GOOD": 30, "SPEED_UP": 5, ...}
  },
  "best_moment": {"frame_index": 12, "score": 0.95, ...},
  "worst_moment": {"frame_index": 8, "score": 0.42, ...},
  "problem_zones": [
    {"start_frame": 7, "end_frame": 10, "avg_score": 0.48, ...}
  ],
  "timeline": [...]
}
```

### `GET /health`

Health check — confirms server is running and Gemini API key is configured.

### `DELETE /session/{session_id}`

Resets session state for a new take.

---

## Server Setup

### 1. Install dependencies

```bash
cd server
pip install fastapi uvicorn google-genai python-dotenv pillow
```

### 2. Set your Gemini API key

```bash
echo "GEMINI_API_KEY=your_key_here" > server/.env
```

Get a key from [aistudio.google.com](https://aistudio.google.com).

### 3. Run the server

```bash
cd server && python main.py
```

Server starts on `http://0.0.0.0:8000`. The iOS app connects to your laptop's local IP on this port.

---

## iOS App

The Swift app handles:

- **Camera capture** — Phone's rear or front camera, encoded as JPEG
- **Microphone capture** — Phone's mic, encoded as 16kHz mono WAV
- **Audio metrics** — Volume RMS, silence ratio, WPM estimation computed on-device
- **3-2-1 countdown** — Displayed before recording starts
- **Coaching HUD** — Real-time overlay showing event type, score bar, reasoning, and phase indicator during hook evaluation
- **Haptic feedback** — Maps buzz patterns from the server to phone haptics
- **Post-session report** — Fetched from the server when recording stops, displayed in-app

---

## Desktop Demo (for testing without the iOS app)

```bash
# Terminal 1: Start server
cd server && python main.py

# Terminal 2: Run demo
python demo.py
```

Uses your Mac's webcam + microphone. Shows a 3-2-1 countdown, hook evaluation, then live coaching overlay. Press `q` to quit and see the session report.

---

## Scoring

- `0.85–1.0` — Excellent. Audience is hooked.
- `0.70–0.84` — Good. Minor tweaks possible.
- `0.55–0.69` — Issues. Something is off — check the event type.
- `0.40–0.54` — Bad. Multiple signals are dropping.
- `< 0.40` — Very bad. Reset and start over.

---

*"You aren't analyzing a video. You're training yourself to be a better performer — in real time."*
