import SwiftUI

struct PermissionsSection: View {
    var micEnabled: Bool
    var cameraEnabled: Bool
    var micSubtitle: String = "LIVE AUDIO COACHING"
    var cameraSubtitle: String = "VISUAL ENERGY ANALYSIS"
    var onToggleMic: () -> Void = {}
    var onToggleCamera: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel(text: "2. PERMISSIONS")
                .padding(.bottom, 24)

            VStack(spacing: 0) {
                PermissionToggleRow(
                    title: "Microphone",
                    subtitle: micSubtitle,
                    isOn: micEnabled,
                    onTap: onToggleMic
                )

                Rectangle()
                    .fill(Color(hex: "18181B"))
                    .frame(height: 1)

                PermissionToggleRow(
                    title: "Camera Feed",
                    subtitle: cameraSubtitle,
                    isOn: cameraEnabled,
                    onTap: onToggleCamera
                )
            }
        }
    }
}

struct PermissionToggleRow: View {
    let title: String
    let subtitle: String
    var isOn: Bool
    var onTap: () -> Void = {}

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.custom("Satoshi-Bold", size: 15))
                    .tracking(-0.3)
                    .foregroundColor(.white)
                Text(subtitle)
                    .font(.custom("Satoshi-Medium", size: 11))
                    .foregroundColor(Color(hex: "A1A1AA"))
                    .textCase(.uppercase)
            }
            Spacer()
            NeuroSyncToggle(isOn: .constant(isOn), onTap: onTap)
        }
        .padding(.vertical, 20)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title) permission, currently \(isOn ? "enabled" : "disabled")")
    }
}
