# ◈ Neuro-Sync — AI-Powered Creator Coaching System

> **Real-time feedback for content creators. Built on Raspberry Pi + Gemini Vision.**  
> Point the camera at yourself. Start recording. Get live light + buzzer signals telling you when your energy drops, when you're rambling, and when you're in the zone.

---

## What It Does

Most creators film 10 takes, pick the least-bad one, and wonder why it still flops. Neuro-Sync fixes the act of recording itself — not in post.

While you record, a **camera watches your face and body** and a **microphone listens to your voice**. A Gemini Vision pipeline analyzes your energy, pacing, eye contact, and emotion in real-time. A physical **LED strip and buzzer** give you immediate, wordless feedback — no earbuds, no phone to glance at, just light and sound that your body learns to react to instinctively.

**Green light** = you're locked in. Keep going.  
**Red light + buzz** = something dropped. Fix it now.

---

## Hardware You Need

Everything visible in the build photo:

| Component | What It Does |
|---|---|
| Raspberry Pi 4 (or 3B+) | Runs the entire pipeline — video capture, Gemini API calls, sensor output |
| USB Webcam (or Pi Camera Module v2) | Captures your face + body at 30fps |
| Grove Sound Sensor | Picks up your voice — detects when you go silent or drop volume |
| Grove Light Sensor | Optional ambient light check — flags if your face is underlit |
| Grove LED (Red + Green) or LED strip | Primary real-time feedback output |
| Grove Buzzer | Audio feedback for critical alerts (not in your ear — on the desk) |
| Grove Base HAT for Raspberry Pi | Connects all Grove modules cleanly to Pi GPIO |
| MicroSD card (32GB+) | OS + project files |
| USB power supply (5V 3A) | Powers the Pi |
| USB-C cable + laptop (optional) | For SSH / development |

**Grove wiring (Base HAT ports):**

```
Sound Sensor  → A0  (analog)
Light Sensor  → A2  (analog)
Green LED     → D5  (digital)
Red LED       → D6  (digital)
Buzzer        → D16 (digital)
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RASPBERRY PI                        │
│                                                     │
│  ┌──────────┐    ┌───────────────────────────────┐  │
│  │ USB Cam  │───▶│  capture.py                   │  │
│  │ 30fps    │    │  • Grabs frame every 2s        │  │
│  └──────────┘    │  • Encodes to base64 JPEG      │  │
│                  └──────────────┬────────────────┘  │
│  ┌──────────┐                   │                   │
│  │ Sound    │───▶ audio.py      │                   │
│  │ Sensor   │    • RMS volume   │                   │
│  │ (Grove)  │    • Silence det. │                   │
│  └──────────┘         │         │                   │
│                       ▼         ▼                   │
│               ┌───────────────────────┐             │
│               │   signal_fusion.py    │             │
│               │   Combines all inputs │             │
│               │   into one payload    │             │
│               └──────────┬────────────┘             │
│                          │                          │
│                          ▼                          │
│               ┌───────────────────────┐             │
│               │   gemini_coach.py     │             │
│               │   Gemini 1.5 Flash    │             │
│               │   Vision API call     │             │
│               │   Returns JSON event  │             │
│               └──────────┬────────────┘             │
│                          │                          │
│                          ▼                          │
│               ┌───────────────────────┐             │
│               │   feedback.py         │             │
│               │   Maps event →        │             │
│               │   LED color + buzz    │             │
│               └──────────┬────────────┘             │
│                          │                          │
│            ┌─────────────┼─────────────┐            │
│            ▼             ▼             ▼            │
│       Green LED      Red LED        Buzzer          │
│       (on desk,      (on desk)      (on desk)       │
│        facing you)                                  │
└─────────────────────────────────────────────────────┘
```

---

## Gemini Input → Output

This is the core of the system. Here's exactly what gets sent to Gemini and what comes back.

### Input Payload (sent every ~2 seconds)

```python
prompt = """
You are a real-time video coaching assistant for content creators.

Analyze this frame and the audio metrics below. Return ONLY a JSON object — 
no markdown, no explanation, just raw JSON.

Audio metrics:
- volume_rms: {volume_rms}        # 0.0 (silent) to 1.0 (loud)
- silence_ratio: {silence_ratio}  # ratio of silence in last 3s
- estimated_wpm: {estimated_wpm}  # words per minute estimate

Return this exact schema:
{{
  "event": "GOOD" | "SPEED_UP" | "VIBE_CHECK" | "RAISE_ENERGY" | "VISUAL_RESET",
  "retention_score": <float 0.0-1.0>,
  "reason": "<one short sentence>",
  "led": "green" | "red" | "off",
  "buzz": true | false
}}

Event definitions:
- GOOD: Creator energy is high, face engaged, pacing normal. Score > 0.72.
- SPEED_UP: Talking too slowly or too many pauses. WPM < 80 or silence > 40%.
- VIBE_CHECK: Face looks flat/bored but body language suggests they know the content.
- RAISE_ENERGY: Vocal energy dropping, slouching, eye contact lost.
- VISUAL_RESET: Creator has been static/in same position for too long.
"""
```

**The frame** is a base64-encoded JPEG from the webcam, attached as a Gemini vision input alongside this text prompt.

### Output (what Gemini returns)

```json
{
  "event": "SPEED_UP",
  "retention_score": 0.54,
  "reason": "Speaking pace very slow, multiple long pauses in last 3 seconds.",
  "led": "red",
  "buzz": true
}
```

### How the output maps to physical hardware

| `event` | LED State | Buzzer | What It Means |
|---|---|---|---|
| `GOOD` | Green ON | Silent | You're locked in — hold this energy |
| `SPEED_UP` | Red flash (3x fast) | 3 short beeps | Rambling or too many pauses — tighten up |
| `VIBE_CHECK` | Red ON steady | 2 medium beeps | Your face disagrees with your energy |
| `RAISE_ENERGY` | Red pulse slow | 1 long beep | Vocal energy falling — project more |
| `VISUAL_RESET` | Red + Green alternate | 1 sweep beep | You've been static too long — move |

---

## Project File Structure

```
neuro-sync/
├── README.md
├── requirements.txt
├── .env                    ← your GEMINI_API_KEY goes here
│
├── main.py                 ← entry point, runs the main loop
│
├── capture.py              ← webcam frame capture + base64 encoding
├── audio.py                ← Grove sound sensor reading + WPM estimation  
├── signal_fusion.py        ← combines camera + audio into one payload
├── gemini_coach.py         ← Gemini API call + response parsing
├── feedback.py             ← maps Gemini output to LED + buzzer signals
│
├── calibrate.py            ← one-time baseline calibration script
└── review.py               ← post-session: prints event log + score timeline
```

---

## Step-by-Step Setup

### Step 1: Flash the Raspberry Pi

1. Download **Raspberry Pi OS Lite (64-bit)** from raspberrypi.com/software
2. Flash to MicroSD using Raspberry Pi Imager
3. In Imager advanced settings: enable SSH, set hostname `neurosync.local`, set your WiFi credentials
4. Boot the Pi, SSH in: `ssh pi@neurosync.local`

### Step 2: Install Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git libopencv-dev python3-opencv

# Enable camera interface
sudo raspi-config
# → Interface Options → Camera → Enable
# Reboot after

git clone https://github.com/yourname/neuro-sync.git
cd neuro-sync

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

**requirements.txt:**
```
google-generativeai>=0.5.0
opencv-python-headless>=4.8.0
numpy>=1.24.0
RPi.GPIO>=0.7.1
grove.py>=0.6.0
python-dotenv>=1.0.0
pillow>=10.0.0
```

### Step 3: Wire the Grove Sensors

1. Attach the **Grove Base HAT** to the Raspberry Pi GPIO header (press down firmly)
2. Connect sensors using Grove cables (the 4-pin white connectors):

```
Grove Sound Sensor  →  Port A0  on Base HAT
Grove Light Sensor  →  Port A2  on Base HAT
Grove Green LED     →  Port D5  on Base HAT
Grove Red LED       →  Port D6  on Base HAT
Grove Buzzer        →  Port D16 on Base HAT
```

3. Position the sound sensor facing toward where you'll be standing/sitting
4. Position both LEDs so they're visible to you while you face the camera
5. Place the buzzer on the desk — not too close to the camera mic

### Step 4: Connect the Camera

**Option A — USB Webcam:**
```bash
# Plug in USB webcam. Verify it's detected:
ls /dev/video*
# Should show /dev/video0

# Test capture:
python3 -c "import cv2; cap = cv2.VideoCapture(0); ret, frame = cap.read(); print('Camera OK' if ret else 'FAILED')"
```

**Option B — Pi Camera Module:**
```bash
# Enable in raspi-config → Interface Options → Legacy Camera → Enable
# Then reboot. Test:
raspistill -o test.jpg
# If you get a test.jpg, it's working
```

Update `capture.py` line 8: set `CAMERA_INDEX = 0` for USB or `CAMERA_INDEX = -1` for Pi Camera.

### Step 5: Set Your Gemini API Key

```bash
# Get your key from: aistudio.google.com
echo "GEMINI_API_KEY=your_key_here" > .env
```

### Step 6: Run Calibration

```bash
python3 calibrate.py
```

This records 10 seconds of you talking normally. It sets your baseline volume RMS and typical WPM so the system can compute *relative* changes rather than absolute thresholds. Your calibration profile is saved to `calibration.json`.

### Step 7: Run the System

```bash
python3 main.py
```

You'll see output like:
```
[00:03] GOOD          score=0.81  Green ON
[00:05] GOOD          score=0.79  Green ON
[00:07] SPEED_UP      score=0.52  Red flash + 3 beeps
[00:09] GOOD          score=0.74  Green ON
[00:11] RAISE_ENERGY  score=0.61  Red pulse + 1 long beep
```

Press `Ctrl+C` to stop. The session log is auto-saved to `sessions/YYYY-MM-DD_HH-MM.json`.

---

## The Core Code

### main.py
```python
import time
import json
from datetime import datetime
from capture import get_frame
from audio import get_audio_metrics
from signal_fusion import build_payload
from gemini_coach import get_coaching_event
from feedback import apply_feedback

SESSION_LOG = []
LOOP_INTERVAL = 2.0  # analyze every 2 seconds

def main():
    print("◈ Neuro-Sync starting...")
    print("Press Ctrl+C to stop and save session.\n")
    
    start_time = time.time()
    
    try:
        while True:
            loop_start = time.time()
            
            # 1. Capture
            frame_b64 = get_frame()
            audio_metrics = get_audio_metrics()
            
            # 2. Fuse signals
            payload = build_payload(frame_b64, audio_metrics)
            
            # 3. Ask Gemini
            result = get_coaching_event(payload)
            
            # 4. Output to hardware
            apply_feedback(result)
            
            # 5. Log
            elapsed = round(time.time() - start_time, 1)
            print(f"[{elapsed:06.1f}s] {result['event']:<14} score={result['retention_score']:.2f}  {result['reason']}")
            SESSION_LOG.append({"t": elapsed, **result})
            
            # Sleep to maintain loop interval
            time.sleep(max(0, LOOP_INTERVAL - (time.time() - loop_start)))
            
    except KeyboardInterrupt:
        save_session()
        print("\n✓ Session saved.")

def save_session():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = f"sessions/{ts}.json"
    with open(path, "w") as f:
        json.dump(SESSION_LOG, f, indent=2)

if __name__ == "__main__":
    main()
```

### capture.py
```python
import cv2
import base64
import numpy as np
from PIL import Image
import io

CAMERA_INDEX = 0
_cap = None

def _get_cap():
    global _cap
    if _cap is None:
        _cap = cv2.VideoCapture(CAMERA_INDEX)
        _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return _cap

def get_frame() -> str:
    """Capture one frame, return as base64-encoded JPEG string."""
    cap = _get_cap()
    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Camera read failed")
    
    # Encode to JPEG at 85% quality (balance: detail vs API payload size)
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode('utf-8')
```

### audio.py
```python
import time
from grove.grove_sound_sensor import GroveSoundSensor

SOUND_PIN = 0  # A0 on Base HAT
_sensor = GroveSoundSensor(SOUND_PIN)

SAMPLE_WINDOW = 3.0   # seconds of audio to analyze
SAMPLE_RATE = 20      # readings per second

def get_audio_metrics() -> dict:
    """Sample the sound sensor for SAMPLE_WINDOW seconds. Return volume and silence metrics."""
    samples = []
    interval = 1.0 / SAMPLE_RATE
    n_samples = int(SAMPLE_WINDOW * SAMPLE_RATE)
    
    for _ in range(n_samples):
        samples.append(_sensor.sound)
        time.sleep(interval)
    
    # Normalize to 0.0–1.0 (Grove sound sensor returns 0–1023)
    normalized = [s / 1023.0 for s in samples]
    
    rms = (sum(s**2 for s in normalized) / len(normalized)) ** 0.5
    silence_threshold = 0.05
    silence_ratio = sum(1 for s in normalized if s < silence_threshold) / len(normalized)
    
    # Rough WPM estimate: count "bursts" of sound above threshold
    # Each burst roughly corresponds to a stressed syllable
    bursts = 0
    in_burst = False
    for s in normalized:
        if s > 0.12 and not in_burst:
            bursts += 1
            in_burst = True
        elif s < 0.08:
            in_burst = False
    
    # ~1.4 syllables per word average, 3s window → extrapolate to WPM
    estimated_wpm = int((bursts / 1.4) * (60 / SAMPLE_WINDOW))
    
    return {
        "volume_rms": round(rms, 3),
        "silence_ratio": round(silence_ratio, 3),
        "estimated_wpm": estimated_wpm
    }
```

### gemini_coach.py
```python
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT_TEMPLATE = """
You are a real-time video coaching assistant for content creators.

Analyze this frame and audio metrics. Return ONLY a JSON object — no markdown, no extra text.

Audio metrics:
- volume_rms: {volume_rms}
- silence_ratio: {silence_ratio}
- estimated_wpm: {estimated_wpm}

Return exactly this schema:
{{
  "event": "GOOD" | "SPEED_UP" | "VIBE_CHECK" | "RAISE_ENERGY" | "VISUAL_RESET",
  "retention_score": <float 0.0-1.0>,
  "reason": "<one sentence max>",
  "led": "green" | "red" | "off",
  "buzz": true | false
}}

Event rules:
- GOOD: engaged face, normal pacing (WPM 85-160), eye contact. Score > 0.72. led=green, buzz=false.
- SPEED_UP: WPM < 80 OR silence_ratio > 0.40. Score < 0.65. led=red, buzz=true.
- VIBE_CHECK: face flat/neutral while content seems high-energy. Score 0.50-0.68. led=red, buzz=true.
- RAISE_ENERGY: slouching, low volume (rms < 0.15), eyes down. Score < 0.60. led=red, buzz=true.
- VISUAL_RESET: body very static, no movement for extended period. Score 0.55-0.70. led=red, buzz=false.
"""

FALLBACK = {"event": "GOOD", "retention_score": 0.70, "reason": "API unavailable", "led": "green", "buzz": False}

def get_coaching_event(payload: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(**payload["audio_metrics"])
    
    image_part = {
        "mime_type": "image/jpeg",
        "data": payload["frame_b64"]
    }
    
    try:
        response = model.generate_content([prompt, image_part])
        text = response.text.strip()
        
        # Strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        result = json.loads(text)
        
        # Validate required keys
        required = {"event", "retention_score", "reason", "led", "buzz"}
        if not required.issubset(result.keys()):
            return FALLBACK
            
        return result
        
    except Exception as e:
        print(f"  [gemini error] {e}")
        return FALLBACK
```

### feedback.py
```python
import time
import RPi.GPIO as GPIO

# GPIO pin numbers (BCM mode)
GREEN_LED_PIN = 5
RED_LED_PIN   = 6
BUZZER_PIN    = 16

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
GPIO.setup(RED_LED_PIN,   GPIO.OUT)
GPIO.setup(BUZZER_PIN,    GPIO.OUT)

def _all_off():
    GPIO.output(GREEN_LED_PIN, GPIO.LOW)
    GPIO.output(RED_LED_PIN,   GPIO.LOW)
    GPIO.output(BUZZER_PIN,    GPIO.LOW)

def _beep(count: int, duration: float, gap: float):
    for _ in range(count):
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        time.sleep(gap)

def apply_feedback(result: dict):
    event = result.get("event", "GOOD")
    _all_off()

    if event == "GOOD":
        # Solid green
        GPIO.output(GREEN_LED_PIN, GPIO.HIGH)

    elif event == "SPEED_UP":
        # 3 fast red flashes + 3 short beeps
        for _ in range(3):
            GPIO.output(RED_LED_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(RED_LED_PIN, GPIO.LOW)
            time.sleep(0.1)
        _beep(3, 0.08, 0.08)

    elif event == "VIBE_CHECK":
        # Steady red + 2 medium beeps
        GPIO.output(RED_LED_PIN, GPIO.HIGH)
        _beep(2, 0.2, 0.15)

    elif event == "RAISE_ENERGY":
        # Slow red pulse + 1 long beep
        for _ in range(3):
            GPIO.output(RED_LED_PIN, GPIO.HIGH)
            time.sleep(0.3)
            GPIO.output(RED_LED_PIN, GPIO.LOW)
            time.sleep(0.3)
        _beep(1, 0.5, 0)

    elif event == "VISUAL_RESET":
        # Green + Red alternate (move signal) — no buzz (you're talking)
        for _ in range(4):
            GPIO.output(GREEN_LED_PIN, GPIO.HIGH)
            GPIO.output(RED_LED_PIN,   GPIO.LOW)
            time.sleep(0.15)
            GPIO.output(GREEN_LED_PIN, GPIO.LOW)
            GPIO.output(RED_LED_PIN,   GPIO.HIGH)
            time.sleep(0.15)
        _all_off()
        GPIO.output(GREEN_LED_PIN, GPIO.HIGH)  # end on green as encouragement
```

---

## Signal Dictionary — What Each Signal Means

Learn these. After 20 minutes of use, your body reacts to them automatically without thinking.

| Signal | Pattern | Meaning | Your Action |
|---|---|---|---|
| **Solid Green** | Green LED on steady | You're in the zone — hold it | Don't change anything |
| **3 Fast Red Flashes + 3 Beeps** | Red blinks rapidly | Too slow / too many pauses | Speed up, cut the filler words |
| **Steady Red + 2 Beeps** | Red on + 2 medium beeps | Face is flat, energy doesn't match words | Smile bigger, open your eyes, lift energy |
| **Slow Red Pulse + 1 Long Beep** | Red fades in and out + long buzz | Vocal energy fading, posture dropping | Chin up, project your voice, breathe |
| **Green/Red Alternating** | Both LEDs flicker alternately | You haven't moved in ages | Step closer, shift angle, create movement |

---

## Calibration Details

Run `python3 calibrate.py` once before your first real session. It does three things:

1. **Baseline volume** — samples your natural speaking volume RMS so the system knows your typical loudness. A quiet creator and a loud creator need different thresholds.
2. **Baseline WPM** — samples your natural speaking pace. The system targets ±20% of your natural rate, not a fixed number.
3. **Ambient light check** — measures the room's current light level so the light sensor can flag if you step out of your lighting setup.

Output is saved to `calibration.json` and loaded automatically on every run.

---

## Post-Session Review

After each session, run:

```bash
python3 review.py sessions/2024-01-15_14-32.json
```

Output:
```
◈ Session Review — 2024-01-15 14:32
Duration: 4m 12s  |  Total events: 126  |  Avg score: 0.74

Timeline:
  0:00 – 0:45  ████████░░  GOOD     (avg 0.81)
  0:45 – 1:10  ████░░░░░░  SPEED_UP (avg 0.53)  ← rambling segment
  1:10 – 2:30  █████████░  GOOD     (avg 0.79)
  2:30 – 2:45  ███░░░░░░░  RAISE_E  (avg 0.48)  ← energy dip
  2:45 – 4:12  ████████░░  GOOD     (avg 0.77)

Hook Score: B+  (74th percentile — your first 8 seconds)
Biggest issue: 28-second ramble at 0:45. Cut this in edit.
Best moment: 1:10 – 2:30. Best take segment. Use this energy.
```

---

## Troubleshooting

**Camera not found:**
```bash
ls /dev/video*          # Check if camera is visible
v4l2-ctl --list-devices # Detailed device list
# Try changing CAMERA_INDEX = 1 in capture.py if 0 fails
```

**Grove sensors not reading:**
```bash
# Test the Base HAT
python3 -c "from grove.factory import Factory; s = Factory.getGpioWrapper('LED', 5); s.on(); import time; time.sleep(1); s.off()"
# If that fails: sudo pip3 install grove.py
```

**Gemini returning non-JSON:**
- The model occasionally wraps output in markdown fences. `gemini_coach.py` strips these automatically.
- If errors persist, check your API key in `.env` and verify quota at aistudio.google.com.

**Loop running too slow (> 3s per cycle):**
- Reduce JPEG quality in `capture.py`: change `85` to `65`
- Increase `LOOP_INTERVAL` in `main.py` to `3.0`
- Upgrade from Pi 3B+ to Pi 4 if available

**Buzzer too loud:**
- Add a 100Ω resistor between the buzzer and the GPIO pin
- Or reduce buzz duration in `feedback.py` (change `0.5` → `0.2`)

---

## How It Works — The Full Loop

```
Every 2 seconds:

1. capture.py        → webcam grabs 1 frame → encode to base64 JPEG (~40KB)
                                                        ↓
2. audio.py          → sound sensor samples 3s of audio → compute RMS, silence%, WPM
                                                        ↓
3. signal_fusion.py  → bundle frame + audio metrics into one payload dict
                                                        ↓
4. gemini_coach.py   → POST to Gemini 1.5 Flash Vision API
                       Input:  base64 frame + audio metrics (~60 tokens text + image)
                       Output: JSON {event, score, reason, led, buzz}
                       Latency: ~400–800ms on Pi 4 with good WiFi
                                                        ↓
5. feedback.py       → parse JSON → drive GPIO pins → LED + buzzer fires
                       Latency: < 5ms
                                                        ↓
6. main.py           → log event to console + session file → sleep → repeat
```

**Total loop latency: ~500–900ms.** Fast enough to feel responsive. The creator gets feedback within 1 second of something dropping.

---

## Demo Script (For Presenting)

1. Boot the Pi, run `python3 main.py`
2. Stand in front of the camera. Green light should come on.
3. **Demo SPEED_UP:** Go silent for 4 seconds. → Red flashes + 3 beeps.
4. **Demo RAISE_ENERGY:** Slouch, look down, speak quietly. → Slow red pulse + long beep.
5. **Demo GOOD:** Stand up straight, smile, speak at normal pace. → Solid green.
6. Show the terminal output — live score stream printed in real-time.
7. Stop with Ctrl+C, run `python3 review.py` on the saved session.

---

## Built At

**MLH Hackathon**  
Hardware: Raspberry Pi 4 + Grove Sensor Kit + USB Webcam  
AI: Google Gemini 1.5 Flash (Vision)  
Team: [your names]

---

*"You aren't analyzing a video. You're training yourself to be a better performer — in real time."*
