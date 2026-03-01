import SwiftUI

struct HomeView: View {
    @AppStorage("onboardingComplete") private var onboardingComplete = false
    @AppStorage("serverURL") private var serverURL = ""
    @State private var isRecording = false
    @State private var showHistory = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 40) {
                Spacer()

                // Title
                VStack(spacing: 12) {
                    Text("NEURO-SYNC")
                        .font(.custom("Tanker", size: 44))
                        .foregroundColor(.white)
                    Text("Tap to start recording")
                        .font(.custom("Satoshi-Medium", size: 15))
                        .foregroundColor(Color(hex: "A1A1AA"))
                }

                // Record button
                Button(action: { isRecording = true }) {
                    ZStack {
                        Circle()
                            .stroke(Color.white.opacity(0.3), lineWidth: 4)
                            .frame(width: 88, height: 88)
                        Circle()
                            .fill(Color.red)
                            .frame(width: 72, height: 72)
                    }
                }

                Spacer()

                // Server status
                HStack(spacing: 8) {
                    Circle()
                        .fill(serverURL.isEmpty ? Color(hex: "71717A") : Color.green)
                        .frame(width: 6, height: 6)
                    Text(serverURL.isEmpty ? "No server configured" : serverURL)
                        .font(.custom("Satoshi-Medium", size: 12))
                        .foregroundColor(Color(hex: "71717A"))
                }
                .padding(.bottom, 16)

                // History & Settings links
                HStack(spacing: 24) {
                    Button(action: { showHistory = true }) {
                        Text("History")
                            .font(.custom("Satoshi-Medium", size: 13))
                            .foregroundColor(Color(hex: "A1A1AA"))
                            .underline()
                    }

                    Button(action: { onboardingComplete = false }) {
                        Text("Settings")
                            .font(.custom("Satoshi-Medium", size: 13))
                            .foregroundColor(Color(hex: "A1A1AA"))
                            .underline()
                    }
                }
                .padding(.bottom, 40)
            }
        }
        .preferredColorScheme(.dark)
        .fullScreenCover(isPresented: $isRecording) {
            RecordingView(isPresented: $isRecording)
        }
        .sheet(isPresented: $showHistory) {
            HistoryView()
        }
    }
}
