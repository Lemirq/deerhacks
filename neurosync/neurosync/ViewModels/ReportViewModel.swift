import SwiftUI
import Combine

class ReportViewModel: ObservableObject {
    @Published var report: SessionReport?
    @Published var isLoading = true
    @Published var error: String?

    private let networkService = NetworkService()

    private var serverURL: String {
        let stored = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        return stored.hasPrefix("http") ? stored : "http://\(stored)"
    }

    func fetchReport(sessionId: String) async {
        await MainActor.run { isLoading = true }
        do {
            let report = try await networkService.fetchReport(baseURL: serverURL, sessionId: sessionId)
            await MainActor.run {
                self.report = report
                self.isLoading = false
            }
        } catch {
            await MainActor.run {
                self.error = "Could not load report"
                self.isLoading = false
            }
        }
    }
}
