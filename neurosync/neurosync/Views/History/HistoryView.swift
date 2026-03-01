import SwiftUI

class HistoryViewModel: ObservableObject {
    @Published var summaries: [ReportSummary] = []
    @Published var isLoading = true
    @Published var error: String?

    private let networkService = NetworkService()

    private var serverURL: String {
        let stored = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        return stored.hasPrefix("http") ? stored : "http://\(stored)"
    }

    func loadHistory() async {
        await MainActor.run { isLoading = true }
        do {
            let results = try await networkService.fetchReportHistory(baseURL: serverURL)
            await MainActor.run {
                self.summaries = results
                self.isLoading = false
            }
        } catch {
            await MainActor.run {
                self.error = "Could not load history"
                self.isLoading = false
            }
        }
    }
}

struct HistoryView: View {
    @StateObject private var viewModel = HistoryViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var selectedSessionId: String?

    private func scoreColor(_ score: Double) -> Color {
        if score >= 0.80 { return Color(red: 0/255, green: 220/255, blue: 80/255) }
        if score >= 0.65 { return Color(red: 200/255, green: 200/255, blue: 0/255) }
        if score >= 0.50 { return Color(red: 255/255, green: 120/255, blue: 0/255) }
        return Color(red: 255/255, green: 30/255, blue: 0/255)
    }

    private func formattedDate(_ timestamp: Double) -> String {
        let date = Date(timeIntervalSince1970: timestamp)
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    var body: some View {
        ZStack {
            DesignTokens.Colors.background.ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                HStack {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(DesignTokens.Colors.textSecondary)
                    }
                    Spacer()
                    Text("HISTORY")
                        .font(DesignTokens.Fonts.satoshiBold(11))
                        .tracking(2)
                        .foregroundColor(DesignTokens.Colors.textTertiary)
                    Spacer()
                    // Balance the close button
                    Image(systemName: "xmark")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.clear)
                }
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 24)

                if viewModel.isLoading {
                    Spacer()
                    VStack(spacing: 16) {
                        ProgressView().tint(.white)
                        Text("LOADING...")
                            .font(DesignTokens.Fonts.satoshiBold(12))
                            .tracking(1.5)
                            .foregroundColor(DesignTokens.Colors.textTertiary)
                    }
                    Spacer()
                } else if viewModel.summaries.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "clock")
                            .font(.system(size: 32))
                            .foregroundColor(DesignTokens.Colors.textTertiary)
                        Text("No past sessions")
                            .font(DesignTokens.Fonts.satoshiMedium(15))
                            .foregroundColor(DesignTokens.Colors.textSecondary)
                        Text("Complete a recording to see reports here")
                            .font(DesignTokens.Fonts.satoshiMedium(13))
                            .foregroundColor(DesignTokens.Colors.textTertiary)
                    }
                    Spacer()
                } else if let error = viewModel.error {
                    Spacer()
                    Text(error)
                        .font(DesignTokens.Fonts.satoshiMedium(14))
                        .foregroundColor(DesignTokens.Colors.textSecondary)
                    Spacer()
                } else {
                    ScrollView(.vertical, showsIndicators: false) {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.summaries) { summary in
                                Button(action: { selectedSessionId = summary.sessionId }) {
                                    HistoryRow(summary: summary, scoreColor: scoreColor, formattedDate: formattedDate)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.bottom, 40)
                    }
                }
            }
        }
        .preferredColorScheme(.dark)
        .task {
            await viewModel.loadHistory()
        }
        .sheet(item: Binding(
            get: {
                if let id = selectedSessionId {
                    return HistorySelection(id: id)
                }
                return nil
            },
            set: { selectedSessionId = $0?.id }
        )) { selection in
            HistoryReportWrapper(sessionId: selection.id)
        }
    }
}

private struct HistorySelection: Identifiable {
    let id: String
}

private struct HistoryReportWrapper: View {
    let sessionId: String
    @State private var isPresented = true

    var body: some View {
        ReportView(sessionId: sessionId, isPresented: $isPresented)
            .onChange(of: isPresented) { newValue in
                // Dismiss handled by ReportView internally
            }
    }
}

struct HistoryRow: View {
    let summary: ReportSummary
    let scoreColor: (Double) -> Color
    let formattedDate: (Double) -> String

    var body: some View {
        HStack(spacing: 16) {
            // Score circle
            ZStack {
                Circle()
                    .fill(scoreColor(summary.avgScore).opacity(0.15))
                    .frame(width: 48, height: 48)
                Text("\(Int(summary.avgScore * 100))")
                    .font(DesignTokens.Fonts.satoshiBold(16))
                    .foregroundColor(scoreColor(summary.avgScore))
            }

            // Details
            VStack(alignment: .leading, spacing: 4) {
                Text(formattedDate(summary.timestamp))
                    .font(DesignTokens.Fonts.satoshiMedium(14))
                    .foregroundColor(DesignTokens.Colors.textPrimary)

                HStack(spacing: 12) {
                    if let verdict = summary.hookVerdict {
                        Text(verdict)
                            .font(DesignTokens.Fonts.satoshiBold(11))
                            .foregroundColor(verdict == "STRONG"
                                ? Color(red: 0/255, green: 220/255, blue: 80/255)
                                : Color(red: 255/255, green: 120/255, blue: 0/255))
                    }
                    Text("\(summary.totalEvents) events")
                        .font(DesignTokens.Fonts.satoshiMedium(12))
                        .foregroundColor(DesignTokens.Colors.textTertiary)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(DesignTokens.Colors.textTertiary)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .fill(DesignTokens.Colors.divider.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                        .stroke(Color(hex: "27272A"), lineWidth: 1)
                )
        )
    }
}
