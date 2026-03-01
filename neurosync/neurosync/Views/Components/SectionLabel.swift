import SwiftUI

struct SectionLabel: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.custom("Satoshi-Bold", size: 11))
            .tracking(2)
            .foregroundColor(Color(hex: "71717A"))
            .textCase(.uppercase)
    }
}
