import SwiftUI
import Combine

enum RecordingPhase: String {
    case countdown, hookCollecting, coaching, stopped
}

class RecordingViewModel: ObservableObject {
    @Published var phase: RecordingPhase = .countdown
    @Published var countdownText: String = "3"
    @Published var currentEvent: CoachingEvent?
    @Published var hookResult: CoachingEvent?
    @Published var latencyMs: Int = 0
    @Published var error: String?

    var hookIsWeak: Bool {
        hookResult?.event == "HOOK_WEAK"
    }

    let cameraService = CameraService()
    let audioService = AudioService()
    let hapticService = HapticService()
    private let networkService = NetworkService()
    private var analysisTask: Task<Void, Never>?
    @Published private(set) var sessionId = "session_\(UUID().uuidString.prefix(8))"

    private var serverURL: String {
        let stored = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        return stored.hasPrefix("http") ? stored : "http://\(stored)"
    }

    func setup() {
        cameraService.setupSession()
        cameraService.startSession()
        audioService.startCapture()
        startCountdown()
    }

    func teardown() {
        analysisTask?.cancel()
        cameraService.stopSession()
        audioService.stopCapture()
    }

    func redo() {
        // Cancel current loop, reset state, restart from countdown
        analysisTask?.cancel()
        currentEvent = nil
        hookResult = nil
        error = nil
        latencyMs = 0
        sessionId = "session_\(UUID().uuidString.prefix(8))"
        startCountdown()
    }

    private func startCountdown() {
        phase = .countdown
        Task { @MainActor in
            try? await networkService.resetSession(baseURL: serverURL, sessionId: sessionId)

            let steps: [(String, UInt64)] = [
                ("3", 1_000_000_000),
                ("2", 1_000_000_000),
                ("1", 1_000_000_000),
                ("GO!", 500_000_000),
            ]
            for (text, ns) in steps {
                countdownText = text
                hapticService.countdown(text)
                try? await Task.sleep(nanoseconds: ns)
            }

            phase = .hookCollecting
            startAnalysisLoop()
        }
    }

    private func startAnalysisLoop() {
        analysisTask = Task { @MainActor in
            while !Task.isCancelled && phase != .stopped {
                let start = CFAbsoluteTimeGetCurrent()

                guard let frame = cameraService.latestJPEG else {
                    try? await Task.sleep(nanoseconds: 500_000_000)
                    continue
                }

                let metrics = audioService.getMetrics()
                let wav = audioService.getWAVData()

                do {
                    let event = try await networkService.analyze(
                        baseURL: serverURL,
                        frame: frame,
                        audioClip: wav,
                        audioMetrics: metrics,
                        sessionId: sessionId
                    )

                    error = nil

                    // Play haptic feedback for buzz events
                    if event.buzz {
                        hapticService.play(pattern: event.buzzPattern)
                    }

                    // Capture hook result separately — it stays pinned
                    if event.event == "HOOK_GOOD" || event.event == "HOOK_WEAK" {
                        hookResult = event
                        if event.event == "HOOK_WEAK" {
                            hapticService.play(pattern: "double")
                        }
                    } else {
                        currentEvent = event
                    }

                    // Transition from hook to coaching
                    if event.phase == "normal" && phase == .hookCollecting {
                        phase = .coaching
                    }

                    let elapsed = CFAbsoluteTimeGetCurrent() - start
                    latencyMs = Int(elapsed * 1000)

                    let remaining = 2.0 - elapsed
                    if remaining > 0 {
                        try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
                    }
                } catch {
                    self.error = "Connection lost"
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                }
            }
        }
    }

    func stopRecording() {
        phase = .stopped
        analysisTask?.cancel()
        cameraService.stopSession()
        audioService.stopCapture()
    }
}
