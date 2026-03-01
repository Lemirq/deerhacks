# Neuro-Sync iOS Sprint Plan

> Converting from Raspberry Pi + desktop demo to a native SwiftUI app that talks to the existing FastAPI server.

---

## Pre-Sprint: What Already Exists vs What Needs Building

### Server (KEEP AS-IS)
The FastAPI server is fully functional. The iOS app is a drop-in replacement for `demo.py` / the Pi client. No server changes needed.

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `POST /analyze` | Send frame + audio, get coaching event | Ready |
| `GET /health` | Verify server + API key on startup | Ready |
| `DELETE /session/{id}` | Reset before new take | Ready |
| `GET /session/{id}/report` | Full post-session report | Ready |
| `GET /session/{id}/summary` | Quick mid-session stats | Ready |

### Client (BUILD FROM SCRATCH)
Everything in `demo.py` and `pi/` needs to be rebuilt as a SwiftUI app.

---

## Sprint 1: Project Skeleton + Camera Preview (Day 1 morning)

**Goal:** Xcode project compiles, camera shows on screen, app runs on a real device.

### Tasks

#### 1.1 — Create Xcode project
- New SwiftUI project targeting iOS 17+
- Bundle ID: `com.neurosync.app` (or team equivalent)
- Add `Info.plist` entries:
  - `NSCameraUsageDescription` — "Neuro-Sync needs camera access to analyze your performance while recording"
  - `NSMicrophoneUsageDescription` — "Neuro-Sync needs microphone access to analyze your vocal energy and pacing"
- Directory structure:
  ```
  ios/NeuroSync/
  ├── NeuroSyncApp.swift          ← App entry point
  ├── Models/
  │   ├── CoachingEvent.swift     ← Codable structs matching server models
  │   ├── AudioMetrics.swift
  │   └── SessionReport.swift
  ├── Services/
  │   ├── CameraService.swift     ← AVCaptureSession wrapper
  │   ├── AudioService.swift      ← AVAudioEngine mic capture + metrics
  │   ├── NetworkService.swift    ← URLSession multipart POST
  │   └── HapticService.swift     ← UIFeedbackGenerator wrapper
  ├── ViewModels/
  │   ├── RecordingViewModel.swift  ← Orchestrates camera+audio+networking
  │   └── ReportViewModel.swift     ← Fetches and holds report data
  ├── Views/
  │   ├── HomeView.swift            ← Server config + start recording
  │   ├── RecordingView.swift       ← Camera preview + coaching HUD
  │   ├── CountdownView.swift       ← 3-2-1-GO overlay
  │   ├── CoachingOverlay.swift     ← Score bar, event banner, messages
  │   └── ReportView.swift          ← Post-session report display
  └── Utilities/
      └── Constants.swift           ← Colors, thresholds, config values
  ```

#### 1.2 — CameraService
- Wrap `AVCaptureSession` with front camera (`builtInWideAngleCamera`, position `.front`)
- Resolution: `.hd1280x720` (will be resized server-side to 640px)
- Provide a `PreviewLayer` that SwiftUI can display via `UIViewRepresentable`
- Implement `AVCaptureVideoDataOutputSampleBufferDelegate` to grab frames
- Convert `CMSampleBuffer` → JPEG `Data` (quality 0.82) using `CIImage` → `UIImage` → `jpegData()`
- Mirror the preview horizontally (selfie mode)
- Store latest JPEG in a thread-safe property (like demo.py's `_frame_lock` pattern)

#### 1.3 — Basic RecordingView
- Full-screen camera preview (edge-to-edge, no safe area insets on preview)
- "Recording" indicator (red dot)
- Stop button

### Definition of Done
- App launches on a real iPhone, shows live front camera feed
- Can tap stop to go back to home screen
- No crashes, no permission dialogs failing

---

## Sprint 2: Audio Capture + Metrics (Day 1 afternoon)

**Goal:** Microphone captures audio in real-time, computes the same 5 metrics as `demo.py`, and can export WAV bytes.

### Tasks

#### 2.1 — AudioService (ring buffer + metrics)

Port `MicCapture` from demo.py to Swift using `AVAudioEngine`:

```
AVAudioEngine → installTap(on: inputNode) → ring buffer → metrics
```

**Ring buffer spec:**
- Sample rate: 16000 Hz
- Format: mono Float32
- Buffer duration: 1.5 seconds (24,000 samples)
- Use `AVAudioConverter` to downsample from device native rate (typically 48kHz) to 16kHz

**Metrics to compute (matching demo.py exactly):**

| Metric | Formula | Notes |
|--------|---------|-------|
| `volume_rms` | `sqrt(mean(samples^2)) * 3.0`, clamped to [0, 1] | ×3.0 normalization matches demo.py |
| `silence_ratio` | `count(abs(sample) < 0.02) / total` | Threshold = 0.02 |
| `estimated_wpm` | Count burst transitions (ON > 0.04, OFF < 0.025), scale to WPM | `(bursts / 1.5) * 60`, clamp 0-350 |
| `peak_volume` | `max(abs(samples)) * 2.0`, clamped to [0, 1] | ×2.0 normalization |
| `volume_variance` | Variance of 100ms chunk RMS values | Chunk = 1600 samples at 16kHz |

**WAV export:**
- Convert Float32 buffer → Int16 PCM (`sample * 32767`)
- Write WAV header (1ch, 16-bit, 16000Hz) + PCM data
- Return as `Data`

#### 2.2 — Verify metrics match
- Print metrics to console
- Compare against demo.py running simultaneously with same audio source
- Variance within 10% is acceptable (slight differences from sample timing are fine)

### Definition of Done
- AudioService starts/stops cleanly
- `getMetrics()` returns all 5 values
- `getWAVBytes()` returns valid WAV data
- Console output shows reasonable values when speaking / silent

---

## Sprint 3: Networking Layer (Day 1 evening)

**Goal:** App can talk to the FastAPI server — health check, analyze, session management.

### Tasks

#### 3.1 — Models (Codable structs)

```swift
// CoachingEvent.swift
struct CoachingEvent: Codable {
    let event: String          // "GOOD", "SPEED_UP", etc.
    let score: Double          // 0.0-1.0
    let message: String        // max 16 chars
    let detail: String         // score bar string
    let buzz: Bool
    let buzzPattern: String    // "single", "double", "triple", "long"
    let confidence: Double
    let timestamp: Double
    let phase: String          // "hook" or "normal"
    let reasoning: String

    enum CodingKeys: String, CodingKey {
        case event, score, message, detail, buzz
        case buzzPattern = "buzz_pattern"
        case confidence, timestamp, phase, reasoning
    }
}

// AudioMetrics.swift
struct AudioMetrics: Codable {
    let volumeRms: Double
    let silenceRatio: Double
    let estimatedWpm: Int
    let peakVolume: Double
    let volumeVariance: Double

    enum CodingKeys: String, CodingKey {
        case volumeRms = "volume_rms"
        case silenceRatio = "silence_ratio"
        case estimatedWpm = "estimated_wpm"
        case peakVolume = "peak_volume"
        case volumeVariance = "volume_variance"
    }
}

// SessionReport.swift — matches GET /session/{id}/report response
struct SessionReport: Codable { ... }
```

#### 3.2 — NetworkService

**Health check:**
```swift
func healthCheck() async throws -> HealthResponse
// GET {serverURL}/health
```

**Analyze (main endpoint):**
```swift
func analyze(
    frame: Data,          // JPEG bytes
    audioClip: Data,      // WAV bytes
    audioMetrics: AudioMetrics,
    sessionId: String
) async throws -> CoachingEvent
```

Build a `multipart/form-data` request manually:
- Part 1: `frame` — filename `frame.jpg`, content-type `image/jpeg`
- Part 2: `audio_clip` — filename `audio.wav`, content-type `audio/wav`
- Part 3: `audio_metrics` — JSON string as form field
- Part 4: `session_id` — plain text form field

Timeout: 12 seconds (matching demo.py).

**Session reset:**
```swift
func resetSession(_ sessionId: String) async throws
// DELETE {serverURL}/session/{sessionId}
```

**Report:**
```swift
func fetchReport(_ sessionId: String) async throws -> SessionReport
// GET {serverURL}/session/{sessionId}/report
```

#### 3.3 — Server URL configuration
- `HomeView` has a text field for server URL (default: `http://<laptop-ip>:8000`)
- Store in `UserDefaults`
- Show health check result (green checkmark / red X)

### Definition of Done
- App connects to server, health check shows green
- Can manually trigger an `/analyze` call and see the JSON response logged
- Network errors are caught and displayed (not crashes)

---

## Sprint 4: Recording Loop + Live Coaching (Day 2 morning)

**Goal:** Full recording pipeline — camera + audio → server → coaching events displayed live.

### Tasks

#### 4.1 — RecordingViewModel (orchestration)

This is the equivalent of `Analyzer.run()` in demo.py. It ties everything together.

**State machine:**
```
idle → countdown → hook_collecting → hook_result → coaching → stopped
```

**Properties (published for SwiftUI):**
```swift
@Published var currentEvent: CoachingEvent?
@Published var phase: String = "idle"       // drives UI state
@Published var latencyMs: Int = 0
@Published var audioMetrics: AudioMetrics?
@Published var isRecording: Bool = false
```

**Analysis loop (runs on background Task):**
```swift
func startRecording() {
    // 1. Reset session on server
    // 2. Start camera + audio services
    // 3. Run countdown (delegate to view)
    // 4. Enter analysis loop:
    while isRecording {
        let frame = cameraService.latestJPEG
        let metrics = audioService.getMetrics()
        let wav = audioService.getWAVBytes()

        let event = try await networkService.analyze(
            frame: frame,
            audioClip: wav,
            audioMetrics: metrics,
            sessionId: sessionId
        )

        await MainActor.run {
            self.currentEvent = event
            self.phase = event.phase
        }

        // Rate limit: minimum 2 seconds between requests
        try await Task.sleep(for: .seconds(max(0, 2.0 - elapsed)))
    }
}
```

**Error handling:**
- Network timeout → show "Reconnecting..." status, retry
- 3+ consecutive failures → show error banner, keep retrying
- Server unreachable → stop recording, show error

#### 4.2 — CoachingOverlay (HUD)

SwiftUI overlay on top of camera preview. Replicates `draw_overlay()` from demo.py.

**Layout (top to bottom):**

```
┌────────────────────────────────────────┐
│  [EVENT TYPE]              [SCORE %]   │  ← colored banner
│  reasoning text...                     │  ← small gray text
│                                        │
│          (camera preview)              │
│                                        │
│  ┌────────────────────────────────┐    │
│  │  MESSAGE TEXT                  │    │  ← bordered message box
│  └────────────────────────────────┘    │
│  ████████████░░░░░  78%                │  ← score bar
│  VOL:0.45 WPM:142            1200ms   │  ← audio meters + latency
└────────────────────────────────────────┘
     ↑ colored border around entire view
```

**Phase indicator:**
- When `phase == "hook"` → show "HOOK EVAL" badge centered below banner

**Color mapping (RGB, matching demo.py but converted from BGR):**
```swift
static let colors: [String: Color] = [
    "GOOD":         Color(red: 0/255, green: 220/255, blue: 80/255),
    "SPEED_UP":     Color(red: 255/255, green: 30/255, blue: 0/255),
    "VIBE_CHECK":   Color(red: 255/255, green: 120/255, blue: 0/255),
    "RAISE_ENERGY": Color(red: 255/255, green: 30/255, blue: 0/255),
    "VISUAL_RESET": Color(red: 0/255, green: 150/255, blue: 255/255),
    "HOOK_GOOD":    Color(red: 200/255, green: 200/255, blue: 0/255),
    "HOOK_WEAK":    Color(red: 200/255, green: 80/255, blue: 0/255),
]
```

### Definition of Done
- Start recording → 3-2-1 countdown → hook phase (shows "HOOK EVAL...") → hook verdict flashes → normal coaching begins
- Score bar, event type, message, reasoning all update live
- Colored border pulses with event type
- Stop recording → transitions to report screen
- Minimum 2s between server calls, latency displayed

---

## Sprint 5: Countdown + Haptics (Day 2 midday)

**Goal:** Polish the recording start experience and add physical feedback.

### Tasks

#### 5.1 — CountdownView

Full-screen overlay during countdown phase. Replicates `draw_countdown()` from demo.py.

**Sequence:**
| Text | Duration | Color | Haptic |
|------|----------|-------|--------|
| "3" | 1.0s | Yellow | Medium impact |
| "2" | 1.0s | Yellow | Medium impact |
| "1" | 1.0s | Yellow | Heavy impact |
| "GO!" | 0.5s | Green | Success notification |

**Visual spec:**
- Camera preview visible but dimmed (60% dark overlay)
- Large centered number (system font, ~120pt, bold)
- Number scales up slightly on appear (spring animation)
- Colored border matches number color

#### 5.2 — HapticService

Map server buzz patterns to iOS haptics using `UIImpactFeedbackGenerator` and `UINotificationFeedbackGenerator`.

```swift
class HapticService {
    func play(pattern: String) {
        switch pattern {
        case "triple":
            // SPEED_UP — 3 rapid taps
            // 3x UIImpactFeedbackGenerator(.light) with 80ms gaps
        case "double":
            // VIBE_CHECK — 2 medium taps
            // 2x UIImpactFeedbackGenerator(.medium) with 150ms gaps
        case "long":
            // RAISE_ENERGY — 1 sustained vibration
            // UINotificationFeedbackGenerator(.warning)
        case "single":
            // Fallback — 1 light tap
            // UIImpactFeedbackGenerator(.light)
        default:
            break
        }
    }
}
```

**Integration:** When `RecordingViewModel` receives a `CoachingEvent` with `buzz == true`, call `hapticService.play(event.buzzPattern)`.

### Definition of Done
- Countdown plays with haptics on each number
- "GO!" flashes green, then transitions to recording
- Coaching events trigger appropriate haptic patterns
- Haptics feel distinct for each event type

---

## Sprint 6: Post-Session Report (Day 2 afternoon)

**Goal:** When recording stops, fetch and display the full session report.

### Tasks

#### 6.1 — ReportViewModel

```swift
class ReportViewModel: ObservableObject {
    @Published var report: SessionReport?
    @Published var isLoading = true
    @Published var error: String?

    func fetchReport(sessionId: String) async {
        // GET /session/{sessionId}/report
        // Parse into SessionReport
    }
}
```

#### 6.2 — ReportView

**Sections:**

**Header:**
- Session duration (calculated from first/last event timestamps)
- Total events count
- Overall average score (large, colored)

**Hook Evaluation Card:**
- Verdict badge: "STRONG HOOK" (green) or "WEAK HOOK" (red/orange)
- Average hook score
- Each evaluation's reasoning (expandable)

**Score Timeline:**
- Horizontal scrollable chart showing score over time
- Color-coded dots for each event type
- Tap a dot to see details (event type, score, reasoning, frame index)
- Use SwiftUI `Chart` (iOS 16+ Charts framework)

**Best & Worst Moments:**
- Two cards side by side
- Frame index, event type, score, reasoning
- Color-coded borders

**Problem Zones:**
- List of consecutive low-score stretches
- Each shows: frame range, duration (frames), average score
- Red/orange tinted background

**Event Breakdown:**
- Pie chart or horizontal bar chart showing count per event type
- Color-coded to match event colors

**Stats Grid:**
- Avg / Min / Max score
- Total events
- Event counts per type

#### 6.3 — Report sharing
- "Share Report" button → export as JSON to Files app
- "New Take" button → reset session, go back to recording

### Definition of Done
- Stop recording → loading spinner → report appears
- All sections render with real data from the server
- Hook verdict is prominently displayed
- Timeline chart is scrollable and tappable
- Can share report as JSON
- Can start a new take from report screen

---

## Sprint 7: Polish + Edge Cases (Day 2 evening / Day 3)

**Goal:** Handle real-world usage gracefully.

### Tasks

#### 7.1 — Server discovery
- On `HomeView`, scan local network for the server (try common ports, or mDNS/Bonjour)
- Fallback: manual IP entry
- Remember last working server URL

#### 7.2 — Connection loss handling
- If server becomes unreachable mid-recording:
  - Show yellow "Reconnecting..." banner (don't stop recording)
  - Retry every 3 seconds
  - After 30 seconds of failure, offer to stop or keep trying
- If server returns 429 (rate limited):
  - Back off automatically (server already handles this, but client should show status)

#### 7.3 — App lifecycle
- Backgrounding during recording → pause analysis loop, keep camera/audio alive briefly
- Returning to foreground → resume analysis
- If app is killed during recording → data is lost (acceptable for v1)

#### 7.4 — Recording indicator
- While recording, show a subtle red dot in the status bar area
- Prevent screen from dimming (`UIApplication.shared.isIdleTimerDisabled = true`)

#### 7.5 — Settings
- Server URL (with health check indicator)
- Camera selection (front / back)
- Haptic feedback toggle (on/off)

#### 7.6 — Orientation lock
- Lock to portrait during recording (content creators typically film portrait)
- Report view can rotate

### Definition of Done
- App handles WiFi drops gracefully
- Screen doesn't dim during recording
- Settings persist across launches
- No crashes from edge cases (permissions denied, server offline, empty responses)

---

## File-by-File Build Order

This is the recommended order to write each Swift file, based on dependencies:

| Order | File | Depends On | Effort |
|-------|------|------------|--------|
| 1 | `Constants.swift` | Nothing | Small |
| 2 | `AudioMetrics.swift` | Nothing | Small |
| 3 | `CoachingEvent.swift` | Nothing | Small |
| 4 | `SessionReport.swift` | `CoachingEvent` | Small |
| 5 | `NetworkService.swift` | Models | Medium |
| 6 | `CameraService.swift` | Nothing | Medium |
| 7 | `AudioService.swift` | `AudioMetrics` | Medium-Large |
| 8 | `HapticService.swift` | Nothing | Small |
| 9 | `RecordingViewModel.swift` | All services + models | Large |
| 10 | `CoachingOverlay.swift` | `CoachingEvent`, `Constants` | Medium |
| 11 | `CountdownView.swift` | Nothing | Small |
| 12 | `RecordingView.swift` | `RecordingViewModel`, overlay, countdown | Medium |
| 13 | `ReportViewModel.swift` | `NetworkService`, `SessionReport` | Small |
| 14 | `ReportView.swift` | `ReportViewModel` | Medium-Large |
| 15 | `HomeView.swift` | `NetworkService` | Small |
| 16 | `NeuroSyncApp.swift` | `HomeView` | Small |

---

## API Contract Reference

### POST /analyze — Multipart Form Data

```
Content-Type: multipart/form-data; boundary=----NeuroSync

------NeuroSync
Content-Disposition: form-data; name="frame"; filename="frame.jpg"
Content-Type: image/jpeg

<JPEG bytes>
------NeuroSync
Content-Disposition: form-data; name="audio_clip"; filename="audio.wav"
Content-Type: audio/wav

<WAV bytes>
------NeuroSync
Content-Disposition: form-data; name="audio_metrics"

{"volume_rms":0.45,"silence_ratio":0.12,"estimated_wpm":142,"peak_volume":0.78,"volume_variance":0.0023}
------NeuroSync
Content-Disposition: form-data; name="session_id"

session_abc123
------NeuroSync--
```

### Response — CoachingEvent JSON

```json
{
    "event": "GOOD",
    "score": 0.85,
    "message": "LOCKED IN",
    "detail": "████████░░ 85%",
    "buzz": false,
    "buzz_pattern": "single",
    "confidence": 0.92,
    "timestamp": 1709234567.89,
    "phase": "normal",
    "reasoning": "Audio: Strong energy | Visual: Good eye contact"
}
```

---

## Key Thresholds & Constants (must match server)

```swift
// Audio metrics computation
let sampleRate: Int = 16000
let audioWindowSec: Double = 1.5
let silenceThreshold: Float = 0.02
let burstOnThreshold: Float = 0.04
let burstOffThreshold: Float = 0.025
let rmsNormFactor: Float = 3.0
let peakNormFactor: Float = 2.0
let varianceChunkMs: Int = 100

// JPEG encoding
let jpegQuality: CGFloat = 0.82

// Networking
let analyzeTimeoutSec: Double = 12.0
let minRequestIntervalSec: Double = 2.0

// Hook phase
let hookDurationSec: Double = 3.0    // server-controlled, but client shows UI for it

// Countdown
let countdownSteps: [(String, Double)] = [("3", 1.0), ("2", 1.0), ("1", 1.0), ("GO!", 0.5)]
```

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| AVAudioEngine 16kHz conversion is lossy | Audio metrics differ from demo.py | Test with same audio source, allow 10% variance |
| Multipart form encoding bugs | Server rejects requests | Test against server with curl first, match exact format |
| Camera frame rate vs analysis rate mismatch | Stale frames sent to server | Always grab latest frame, don't queue |
| WiFi latency on phone | Slow coaching feedback | Show "analyzing..." state, don't block UI |
| iOS background restrictions | Analysis stops when backgrounded | Accept for v1, document limitation |
| Large WAV uploads on cellular | Slow/failing requests | Only support WiFi for v1 (server is local anyway) |
