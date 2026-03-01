import SwiftUI

struct OnboardingView: View {
    @StateObject private var viewModel = OnboardingViewModel()
    @AppStorage("onboardingComplete") private var onboardingComplete = false

    var body: some View {
        ZStack(alignment: .bottom) {
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 0) {
                    OnboardingHeaderView()

                    VStack(spacing: 48) {
                        ServerConnectionSection(
                            serverURL: $viewModel.serverURL,
                            connectionState: viewModel.connectionState,
                            onSubmit: { Task { await viewModel.checkConnection() } }
                        )

                        PermissionsSection(
                            micEnabled: viewModel.micEnabled,
                            cameraEnabled: viewModel.cameraEnabled,
                            micSubtitle: viewModel.micSubtitle,
                            cameraSubtitle: viewModel.cameraSubtitle,
                            onToggleMic: { viewModel.toggleMic() },
                            onToggleCamera: { viewModel.toggleCamera() }
                        )

                        InfoCard()
                    }
                    .padding(.horizontal, 32)
                    .padding(.bottom, 120)
                }
            }

            OnboardingFooterView(
                isEnabled: viewModel.isReady,
                onGetStarted: {
                    viewModel.getStarted()
                    withAnimation { onboardingComplete = true }
                }
            )
        }
        .background(Color.black)
        .preferredColorScheme(.dark)
    }
}
