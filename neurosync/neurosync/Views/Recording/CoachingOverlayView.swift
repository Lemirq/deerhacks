import SwiftUI

struct CoachingOverlayView: View {
    let event: CoachingEvent
    var compact: Bool = false

    private var eventColor: Color {
        switch event.event {
        case "GOOD": return Color(red: 0/255, green: 220/255, blue: 80/255)
        case "SPEED_UP": return Color(red: 255/255, green: 30/255, blue: 0/255)
        case "VIBE_CHECK": return Color(red: 255/255, green: 120/255, blue: 0/255)
        case "RAISE_ENERGY": return Color(red: 255/255, green: 30/255, blue: 0/255)
        case "VISUAL_RESET": return Color(red: 0/255, green: 150/255, blue: 255/255)
        case "HOOK_GOOD": return Color(red: 200/255, green: 200/255, blue: 0/255)
        case "HOOK_WEAK": return Color(red: 200/255, green: 80/255, blue: 0/255)
        default: return .gray
        }
    }

    /// Short, punchy label — no full sentences
    private var shortLabel: String {
        switch event.event {
        case "GOOD": return "LOCKED IN"
        case "SPEED_UP": return "SPEED UP"
        case "VIBE_CHECK": return "FLAT ENERGY"
        case "RAISE_ENERGY": return "MORE ENERGY"
        case "VISUAL_RESET": return "MOVE"
        case "HOOK_GOOD": return "STRONG HOOK"
        case "HOOK_WEAK": return "WEAK HOOK"
        default: return event.event
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Score circle
            ZStack {
                Circle()
                    .stroke(eventColor.opacity(0.3), lineWidth: 3)
                    .frame(width: 44, height: 44)
                Circle()
                    .trim(from: 0, to: event.score)
                    .stroke(eventColor, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                    .frame(width: 44, height: 44)
                    .rotationEffect(.degrees(-90))
                Text("\(Int(event.score * 100))")
                    .font(.custom("Satoshi-Bold", size: 14))
                    .foregroundColor(eventColor)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(shortLabel)
                    .font(.custom("Satoshi-Bold", size: compact ? 14 : 16))
                    .foregroundColor(.white)

                if !compact {
                    Text(event.message)
                        .font(.custom("Satoshi-Medium", size: 12))
                        .foregroundColor(.white.opacity(0.6))
                        .lineLimit(1)
                }
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, compact ? 10 : 12)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.black.opacity(0.7))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(eventColor.opacity(0.4), lineWidth: 1)
                )
        )
    }
}

/// Dedicated hook result banner — stays pinned
struct HookBannerView: View {
    let event: CoachingEvent
    let isWeak: Bool

    private var color: Color {
        isWeak
            ? Color(red: 200/255, green: 80/255, blue: 0/255)
            : Color(red: 200/255, green: 200/255, blue: 0/255)
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: isWeak ? "exclamationmark.triangle.fill" : "checkmark.seal.fill")
                .font(.system(size: 18))
                .foregroundColor(color)

            VStack(alignment: .leading, spacing: 1) {
                Text(isWeak ? "WEAK HOOK" : "STRONG HOOK")
                    .font(.custom("Satoshi-Bold", size: 14))
                    .foregroundColor(.white)
                Text("\(Int(event.score * 100))% — \(event.message)")
                    .font(.custom("Satoshi-Medium", size: 11))
                    .foregroundColor(.white.opacity(0.6))
                    .lineLimit(1)
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(color.opacity(0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(color.opacity(0.5), lineWidth: 1)
                )
        )
    }
}
