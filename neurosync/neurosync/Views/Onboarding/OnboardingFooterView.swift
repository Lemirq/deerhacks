import SwiftUI

struct OnboardingFooterView: View {
    let isEnabled: Bool
    let onGetStarted: () -> Void

    var body: some View {
        Button(action: onGetStarted) {
            Text("Get Started")
                .font(.custom("Satoshi-Bold", size: 16))
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Capsule().fill(Color.white))
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .opacity(isEnabled ? 1.0 : 0.35)
        .padding(.horizontal, 32)
        .padding(.bottom, 40)
    }
}
