import SwiftUI

struct CountdownView: View {
    let number: String

    var body: some View {
        ZStack {
            Color.black.opacity(0.6)
                .ignoresSafeArea()

            Text(number)
                .font(.system(size: 120, weight: .bold, design: .rounded))
                .foregroundColor(number == "GO!" ? .green : .white)
                .shadow(color: (number == "GO!" ? Color.green : Color.white).opacity(0.5), radius: 20)
                .transition(.scale.combined(with: .opacity))
        }
    }
}
