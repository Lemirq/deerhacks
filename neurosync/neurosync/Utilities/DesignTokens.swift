import SwiftUI

enum DesignTokens {
    enum Colors {
        static let background = Color.black
        static let textPrimary = Color.white
        static let textSecondary = Color(hex: "A1A1AA")
        static let textTertiary = Color(hex: "71717A")
        static let labelColor = Color(hex: "52525B")
        static let divider = Color(hex: "18181B")
        static let toggleOff = Color(hex: "1A1A1A")
        static let toggleBorder = Color(hex: "333333")
        static let statusDot = Color(hex: "27272A")
        static let infoIcon = Color(hex: "404040")
    }

    enum Fonts {
        static func tanker(_ size: CGFloat) -> Font { .custom("Tanker", size: size) }
        static func satoshiMedium(_ size: CGFloat) -> Font { .custom("Satoshi-Medium", size: size) }
        static func satoshiBold(_ size: CGFloat) -> Font { .custom("Satoshi-Bold", size: size) }
        static func satoshiBlack(_ size: CGFloat) -> Font { .custom("Satoshi-Black", size: size) }
    }

    enum Spacing {
        static let screenHorizontal: CGFloat = 32
        static let sectionGap: CGFloat = 48
        static let headerTopPadding: CGFloat = 56
        static let footerBottomPadding: CGFloat = 34
    }

    enum Radius {
        static let card: CGFloat = 16
        static let permissionCard: CGFloat = 12
        static let toggle: CGFloat = 10
    }
}
