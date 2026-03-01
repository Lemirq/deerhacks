import SwiftUI
import Combine
import AVFoundation

enum ConnectionState: Equatable {
    case disconnected
    case connecting
    case connected
    case error(String)

    var label: String {
        switch self {
        case .disconnected: return "DISCONNECTED"
        case .connecting: return "CONNECTING..."
        case .connected: return "CONNECTED"
        case .error: return "ERROR"
        }
    }

    var dotColor: Color {
        switch self {
        case .disconnected: return Color(hex: "27272A")
        case .connecting: return Color.yellow
        case .connected: return Color.green
        case .error: return Color.red
        }
    }
}

class OnboardingViewModel: ObservableObject {
    @Published var serverURL: String = "" {
        didSet { debounceCheck() }
    }
    @Published var connectionState: ConnectionState = .disconnected
    @Published var micEnabled: Bool = false {
        didSet { UserDefaults.standard.set(micEnabled, forKey: "micEnabled") }
    }
    @Published var cameraEnabled: Bool = false {
        didSet { UserDefaults.standard.set(cameraEnabled, forKey: "cameraEnabled") }
    }
    @Published var micSubtitle: String = "LIVE AUDIO COACHING"
    @Published var cameraSubtitle: String = "VISUAL ENERGY ANALYSIS"

    private let networkService = NetworkService()
    private var checkTask: Task<Void, Never>?

    var isReady: Bool {
        connectionState == .connected
    }

    init() {
        serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        micEnabled = UserDefaults.standard.bool(forKey: "micEnabled")
        cameraEnabled = UserDefaults.standard.bool(forKey: "cameraEnabled")
        checkCurrentPermissions()
    }

    private func checkCurrentPermissions() {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            micEnabled = true
        case .denied, .restricted:
            micSubtitle = "DENIED — OPEN SETTINGS"
        default: break
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            cameraEnabled = true
        case .denied, .restricted:
            cameraSubtitle = "DENIED — OPEN SETTINGS"
        default: break
        }
    }

    func toggleMic() {
        if micEnabled {
            micEnabled = false
            return
        }
        let status = AVCaptureDevice.authorizationStatus(for: .audio)
        if status == .notDetermined {
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                Task { @MainActor in
                    self.micEnabled = granted
                    if !granted { self.micSubtitle = "DENIED — OPEN SETTINGS" }
                }
            }
        } else if status == .authorized {
            micEnabled = true
        } else {
            micSubtitle = "DENIED — OPEN SETTINGS"
        }
    }

    func toggleCamera() {
        if cameraEnabled {
            cameraEnabled = false
            return
        }
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        if status == .notDetermined {
            AVCaptureDevice.requestAccess(for: .video) { granted in
                Task { @MainActor in
                    self.cameraEnabled = granted
                    if !granted { self.cameraSubtitle = "DENIED — OPEN SETTINGS" }
                }
            }
        } else if status == .authorized {
            cameraEnabled = true
        } else {
            cameraSubtitle = "DENIED — OPEN SETTINGS"
        }
    }

    @MainActor func checkConnection() async {
        guard !serverURL.trimmingCharacters(in: .whitespaces).isEmpty else {
            connectionState = .disconnected
            return
        }
        connectionState = .connecting
        do {
            let url = serverURL.hasPrefix("http") ? serverURL : "http://\(serverURL)"
            let health = try await networkService.healthCheck(baseURL: url)
            if health.geminiKey == "configured" {
                connectionState = .connected
            } else {
                connectionState = .error("Gemini key missing")
            }
            UserDefaults.standard.set(serverURL, forKey: "serverURL")
        } catch {
            connectionState = .error("Unreachable")
        }
    }

    private func debounceCheck() {
        checkTask?.cancel()
        checkTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            await checkConnection()
        }
    }

    func getStarted() {
        UserDefaults.standard.set(serverURL, forKey: "serverURL")
        UserDefaults.standard.set(true, forKey: "onboardingComplete")
    }
}
