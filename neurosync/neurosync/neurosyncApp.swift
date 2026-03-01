import SwiftUI

@main
struct NeuroSyncApp: App {
    @AppStorage("onboardingComplete") var onboardingComplete = false

    var body: some Scene {
        WindowGroup {
            if onboardingComplete {
                HomeView()
            } else {
                OnboardingView()
            }
        }
    }
}
