import SwiftUI

struct InfoCard: View {
    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: "info.circle")
                .font(.system(size: 18))
                .foregroundColor(Color(hex: "71717A"))

            Text("Start your first session by connecting to your server and granting permissions above.")
                .font(.custom("Satoshi-Medium", size: 12))
                .lineSpacing(4)
                .foregroundColor(Color(hex: "A1A1AA"))
        }
        .padding(24)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color(hex: "18181B").opacity(0.1))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color(hex: "18181B"), lineWidth: 1)
        )
    }
}
