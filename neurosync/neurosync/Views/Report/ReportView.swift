import SwiftUI

struct ReportView: View {
    @StateObject private var viewModel = ReportViewModel()
    let sessionId: String
    @Binding var isPresented: Bool

    private func scoreColor(_ score: Double) -> Color {
        if score >= 0.80 { return Color(red: 0/255, green: 220/255, blue: 80/255) }
        if score >= 0.65 { return Color(red: 200/255, green: 200/255, blue: 0/255) }
        if score >= 0.50 { return Color(red: 255/255, green: 120/255, blue: 0/255) }
        return Color(red: 255/255, green: 30/255, blue: 0/255)
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if viewModel.isLoading {
                VStack(spacing: 16) {
                    ProgressView().tint(.white)
                    Text("LOADING REPORT...")
                        .font(DesignTokens.Fonts.satoshiBold(12))
                        .tracking(1.5)
                        .foregroundColor(DesignTokens.Colors.textTertiary)
                }
            } else if let report = viewModel.report {
                ScrollView(.vertical, showsIndicators: false) {
                    VStack(spacing: 32) {
                        // Header: SESSION REPORT + avg score
                        VStack(spacing: 16) {
                            Text("SESSION REPORT")
                                .font(DesignTokens.Fonts.satoshiBold(11))
                                .tracking(2)
                                .foregroundColor(DesignTokens.Colors.textTertiary)

                            Text("\(Int(report.stats.avgScore * 100))")
                                .font(DesignTokens.Fonts.tanker(72))
                                .foregroundColor(scoreColor(report.stats.avgScore))

                            Text("AVERAGE SCORE")
                                .font(DesignTokens.Fonts.satoshiMedium(11))
                                .foregroundColor(DesignTokens.Colors.textSecondary)

                            // Stats row
                            HStack(spacing: 32) {
                                StatItem(label: "EVENTS", value: "\(report.stats.totalEvents)")
                                StatItem(label: "HIGH", value: "\(Int(report.stats.maxScore * 100))%")
                                StatItem(label: "LOW", value: "\(Int(report.stats.minScore * 100))%")
                            }
                        }
                        .padding(.top, 20)

                        // Hook evaluation card
                        if let hook = report.hookEvaluation {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("HOOK EVALUATION")
                                    .font(DesignTokens.Fonts.satoshiBold(11))
                                    .tracking(2)
                                    .foregroundColor(DesignTokens.Colors.textTertiary)

                                HStack {
                                    Text(hook.verdict == "STRONG" ? "STRONG HOOK" : "WEAK HOOK")
                                        .font(DesignTokens.Fonts.satoshiBold(18))
                                        .foregroundColor(hook.verdict == "STRONG"
                                            ? Color(red: 200/255, green: 200/255, blue: 0/255)
                                            : Color(red: 200/255, green: 80/255, blue: 0/255))
                                    Spacer()
                                    Text("\(Int(hook.avgScore * 100))%")
                                        .font(DesignTokens.Fonts.satoshiBold(18))
                                        .foregroundColor(.white)
                                }
                            }
                            .padding(20)
                            .background(
                                RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                                    .fill(DesignTokens.Colors.divider.opacity(0.5))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                                            .stroke(Color(hex: "27272A"), lineWidth: 1)
                                    )
                            )
                        }

                        // Best & worst moments
                        if let best = report.bestMoment, let worst = report.worstMoment {
                            HStack(spacing: 12) {
                                MomentCard(title: "BEST", score: best.score, event: best.event, color: scoreColor(best.score))
                                MomentCard(title: "WORST", score: worst.score, event: worst.event, color: scoreColor(worst.score))
                            }
                        }

                        // Problem zones
                        if !report.problemZones.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("PROBLEM ZONES")
                                    .font(DesignTokens.Fonts.satoshiBold(11))
                                    .tracking(2)
                                    .foregroundColor(DesignTokens.Colors.textTertiary)

                                ForEach(Array(report.problemZones.enumerated()), id: \.offset) { _, zone in
                                    HStack {
                                        Text("Frames \(zone.startFrame)-\(zone.endFrame)")
                                            .font(DesignTokens.Fonts.satoshiMedium(13))
                                            .foregroundColor(.white)
                                        Spacer()
                                        Text("\(Int(zone.avgScore * 100))%")
                                            .font(DesignTokens.Fonts.satoshiBold(13))
                                            .foregroundColor(scoreColor(zone.avgScore))
                                    }
                                    .padding(.vertical, 8)
                                }
                            }
                            .padding(20)
                            .background(
                                RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                                    .fill(DesignTokens.Colors.divider.opacity(0.5))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                                            .stroke(Color(hex: "27272A"), lineWidth: 1)
                                    )
                            )
                        }

                        // Action buttons
                        VStack(spacing: 12) {
                            Button(action: { isPresented = false }) {
                                Text("New Take")
                                    .font(DesignTokens.Fonts.satoshiBold(16))
                                    .foregroundColor(.black)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                                    .background(Capsule().fill(Color.white))
                            }

                            Button(action: { isPresented = false }) {
                                Text("Done")
                                    .font(DesignTokens.Fonts.satoshiMedium(14))
                                    .foregroundColor(DesignTokens.Colors.textSecondary)
                            }
                        }
                        .padding(.top, 8)
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 40)
                }
            } else if let error = viewModel.error {
                VStack(spacing: 16) {
                    Text(error)
                        .font(DesignTokens.Fonts.satoshiMedium(14))
                        .foregroundColor(DesignTokens.Colors.textSecondary)
                    Button("Close") { isPresented = false }
                        .foregroundColor(.white)
                }
            }
        }
        .preferredColorScheme(.dark)
        .task {
            await viewModel.fetchReport(sessionId: sessionId)
        }
    }
}

struct StatItem: View {
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(DesignTokens.Fonts.satoshiBold(18))
                .foregroundColor(.white)
            Text(label)
                .font(DesignTokens.Fonts.satoshiMedium(10))
                .tracking(1)
                .foregroundColor(DesignTokens.Colors.textTertiary)
        }
    }
}

struct MomentCard: View {
    let title: String
    let score: Double
    let event: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(DesignTokens.Fonts.satoshiBold(10))
                .tracking(2)
                .foregroundColor(DesignTokens.Colors.textTertiary)
            Text("\(Int(score * 100))%")
                .font(DesignTokens.Fonts.satoshiBold(28))
                .foregroundColor(color)
            Text(event.replacingOccurrences(of: "_", with: " "))
                .font(DesignTokens.Fonts.satoshiMedium(11))
                .foregroundColor(DesignTokens.Colors.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.permissionCard)
                .fill(DesignTokens.Colors.divider.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: DesignTokens.Radius.permissionCard)
                        .stroke(Color(hex: "27272A"), lineWidth: 1)
                )
        )
    }
}
