# ◈ Neuro-Sync

**AI-Powered Creator Coaching System**

Real-time feedback for content creators. Built on Raspberry Pi + Gemini Vision.

Most creators film 10 takes, pick the least-bad one, and wonder why it still flops. Neuro-Sync fixes the act of recording itself — not in post. While you record, a camera watches your face and body and a microphone listens to your voice. A Gemini Vision pipeline analyzes your energy, pacing, eye contact, and emotion in real-time. A physical LED strip and buzzer give you immediate, wordless feedback — no earbuds, no phone to glance at, just light and sound that your body learns to react to instinctively.

* **Green light** = you're locked in. Keep going.
* **Red light + buzz** = something dropped. Fix it now.

## System Architecture

The project is split into two parts:

1. **Pi Client (`pi/`)**: Captures webcam frames (JPEG) and records audio via a Grove sound sensor. It calculates audio metrics (RMS volume, silence ratio, WPM) and sends a fused payload to the laptop server.
2. **Laptop Server (`server/`)**: A FastAPI server that receives the Pi's payload, prompts Gemini 1.5 Flash Vision for an analysis of the speaker's engagement/energy, and returns a coaching event (e.g., `SPEED_UP`, `RAISE_ENERGY`, `GOOD`).

## Setup

### Server (Laptop)

1. Navigate to the `neuro-sync` directory.
2. Create python virtual environment: `python3 -m venv venv`
3. Activate the virtual environment: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements_server.txt`
5. Ensure your `.env` file in the `server/` directory has your `GEMINI_API_KEY` set.
6. Run the server: `cd server && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### Client (Raspberry Pi)

*See detailed hardware requirements and setup instructions in the project root if needed.*

1. Install system dependencies: `sudo apt install -y python3-pip python3-venv git libopencv-dev python3-opencv`
2. Clone repository and install requirements from `requirements_pi.txt`.
3. Set up the Grove Base HAT and connect sensors/LEDs/Buzzer as specified.
4. Run the main loop: `python3 main.py`

## Event Dictionary

| Event | LED State | Buzzer | What It Means |
| :--- | :--- | :--- | :--- |
| `GOOD` | Solid Green | Silent | You're in the zone — hold this energy |
| `SPEED_UP` | Red flash (3x fast) | 3 short beeps | Rambling or too many pauses — tighten up |
| `VIBE_CHECK` | Steady Red | 2 medium beeps | Your face disagrees with your energy |
| `RAISE_ENERGY` | Slow Red pulse | 1 long beep | Vocal energy falling — project more |
| `VISUAL_RESET` | Green + Red alternate| 1 sweep beep | You've been static too long — move |
