import SwiftUI

struct NeuroSyncToggle: View {
    @Binding var isOn: Bool
    var onTap: (() -> Void)?

    var body: some View {
        Button(action: {
            if let onTap {
                onTap()
            } else {
                withAnimation(.easeInOut(duration: 0.2)) { isOn.toggle() }
            }
        }) {
            ZStack(alignment: isOn ? .trailing : .leading) {
                Capsule()
                    .fill(isOn ? Color.white : Color(hex: "1A1A1A"))
                    .overlay(
                        Capsule().stroke(Color(hex: "333333"), lineWidth: 1)
                    )
                    .frame(width: 40, height: 20)

                Circle()
                    .fill(isOn ? Color.black : Color.white)
                    .frame(width: 14, height: 14)
                    .padding(3)
            }
            .animation(.easeInOut(duration: 0.2), value: isOn)
        }
        .buttonStyle(.plain)
    }
}
