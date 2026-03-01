import SwiftUI

struct OnboardingHeaderView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel(text: "CONFIGURATION")
                .padding(.bottom, 8)

            Text("WELCOME TO\nNEURO-SYNC")
                .font(.custom("Tanker", size: 48))
                .tracking(-0.5)
                .foregroundColor(.white)
                .textCase(.uppercase)
                .padding(.bottom, 16)

            Text("Professional real-time coaching for high-stakes content creation. Experience Gemini AI vision analysis as you record.")
                .font(.custom("Satoshi-Medium", size: 14))
                .foregroundColor(Color(hex: "A1A1AA"))
                .lineSpacing(4)
                .frame(maxWidth: 280, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 56)
        .padding(.horizontal, 32)
        .padding(.bottom, 48)
    }
}
