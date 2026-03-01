import SwiftUI

struct ServerConnectionSection: View {
    @Binding var serverURL: String
    let connectionState: ConnectionState
    var onSubmit: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            SectionLabel(text: "1. SERVER CONNECTION")

            VStack(alignment: .leading, spacing: 8) {
                Text("HOST ADDRESS")
                    .font(.custom("Satoshi-Bold", size: 10))
                    .tracking(1.5)
                    .foregroundColor(Color(hex: "A1A1AA"))
                    .textCase(.uppercase)

                TextField("192.168.1.50:8000", text: $serverURL)
                    .font(.custom("Tanker", size: 20))
                    .tracking(-0.3)
                    .foregroundColor(.white)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .keyboardType(.URL)
                    .padding(.vertical, 8)
                    .overlay(
                        Rectangle()
                            .frame(height: 1)
                            .foregroundColor(Color.white.opacity(0.2)),
                        alignment: .bottom
                    )
                    .tint(.white)
                    .onSubmit { onSubmit() }
            }

            HStack(spacing: 8) {
                Circle()
                    .fill(connectionState.dotColor)
                    .frame(width: 6, height: 6)
                    .animation(.easeInOut(duration: 0.3), value: connectionState)
                Text("STATE: \(connectionState.label)")
                    .font(.custom("Satoshi-Bold", size: 10))
                    .tracking(1.5)
                    .foregroundColor(Color(hex: "A1A1AA"))
                    .animation(.easeInOut(duration: 0.3), value: connectionState)
            }
        }
    }
}
