import UIKit

class HapticService {
    private let lightGenerator = UIImpactFeedbackGenerator(style: .light)
    private let mediumGenerator = UIImpactFeedbackGenerator(style: .medium)
    private let heavyGenerator = UIImpactFeedbackGenerator(style: .heavy)
    private let notificationGenerator = UINotificationFeedbackGenerator()

    init() {
        lightGenerator.prepare()
        mediumGenerator.prepare()
        heavyGenerator.prepare()
        notificationGenerator.prepare()
    }

    func play(pattern: String) {
        switch pattern {
        case "triple":
            // SPEED_UP — 3 rapid light taps
            lightGenerator.impactOccurred()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) { [self] in
                lightGenerator.impactOccurred()
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) { [self] in
                lightGenerator.impactOccurred()
            }
        case "double":
            // VIBE_CHECK — 2 medium taps
            mediumGenerator.impactOccurred()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [self] in
                mediumGenerator.impactOccurred()
            }
        case "long":
            // RAISE_ENERGY — warning notification
            notificationGenerator.notificationOccurred(.warning)
        case "single":
            lightGenerator.impactOccurred()
        default:
            break
        }
    }

    func countdown(_ number: String) {
        switch number {
        case "3", "2":
            mediumGenerator.impactOccurred()
        case "1":
            heavyGenerator.impactOccurred()
        case "GO!":
            notificationGenerator.notificationOccurred(.success)
        default:
            break
        }
    }
}
