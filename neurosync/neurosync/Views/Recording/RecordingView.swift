import SwiftUI

struct RecordingView: View {
    @StateObject private var viewModel = RecordingViewModel()
    @Binding var isPresented: Bool
    @State private var showReport = false

    var body: some View {
        ZStack {
            // Camera preview
            CameraPreviewView(session: viewModel.cameraService.session)
                .ignoresSafeArea()

            // Main UI
            VStack(spacing: 0) {
                // Top: hook banner (pinned) + coaching event
                VStack(spacing: 8) {
                    // Hook result — stays on screen once received
                    if let hook = viewModel.hookResult {
                        HookBannerView(event: hook, isWeak: viewModel.hookIsWeak)
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }

                    // Live coaching — shown below the hook
                    if let event = viewModel.currentEvent {
                        CoachingOverlayView(event: event, compact: viewModel.hookResult != nil)
                            .transition(.opacity)
                            .animation(.easeInOut(duration: 0.2), value: event.event)
                    } else if viewModel.phase == .hookCollecting {
                        HStack(spacing: 8) {
                            ProgressView()
                                .tint(.yellow)
                                .scaleEffect(0.8)
                            Text("EVALUATING HOOK...")
                                .font(.custom("Satoshi-Bold", size: 11))
                                .tracking(1.5)
                                .foregroundColor(.yellow)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Capsule().fill(Color.black.opacity(0.6)))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 60)
                .animation(.easeInOut(duration: 0.3), value: viewModel.hookResult?.event)

                Spacer()

                // Bottom controls
                VStack(spacing: 12) {
                    // Error
                    if let error = viewModel.error {
                        Text(error)
                            .font(.custom("Satoshi-Bold", size: 12))
                            .foregroundColor(.red)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 6)
                            .background(Capsule().fill(Color.red.opacity(0.2)))
                    }

                    // Redo button — prominent when hook is weak
                    if viewModel.hookIsWeak {
                        Button(action: { viewModel.redo() }) {
                            HStack(spacing: 8) {
                                Image(systemName: "arrow.counterclockwise")
                                    .font(.system(size: 15, weight: .bold))
                                Text("REDO TAKE")
                                    .font(.custom("Satoshi-Bold", size: 14))
                            }
                            .foregroundColor(.black)
                            .padding(.horizontal, 28)
                            .padding(.vertical, 12)
                            .background(Capsule().fill(Color.white))
                        }
                        .transition(.scale.combined(with: .opacity))
                        .animation(.spring(response: 0.4), value: viewModel.hookIsWeak)
                    }

                    HStack {
                        // REC indicator
                        HStack(spacing: 8) {
                            Circle()
                                .fill(Color.red)
                                .frame(width: 10, height: 10)
                            Text("REC")
                                .font(.custom("Satoshi-Bold", size: 13))
                                .foregroundColor(.white)

                            if viewModel.latencyMs > 0 {
                                Text("·")
                                    .foregroundColor(.white.opacity(0.3))
                                Text("\(viewModel.latencyMs)ms")
                                    .font(.custom("Satoshi-Medium", size: 11))
                                    .foregroundColor(.white.opacity(0.4))
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Capsule().fill(Color.black.opacity(0.5)))

                        Spacer()

                        // Stop button
                        Button(action: {
                            viewModel.stopRecording()
                            showReport = true
                        }) {
                            ZStack {
                                Circle()
                                    .fill(Color.white.opacity(0.2))
                                    .frame(width: 64, height: 64)
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.red)
                                    .frame(width: 24, height: 24)
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                }
                .padding(.bottom, 40)
            }

            // Countdown overlay
            if viewModel.phase == .countdown {
                CountdownView(number: viewModel.countdownText)
                    .transition(.opacity)
                    .animation(.easeInOut(duration: 0.2), value: viewModel.countdownText)
            }
        }
        .onAppear {
            viewModel.setup()
            UIApplication.shared.isIdleTimerDisabled = true
        }
        .onDisappear {
            viewModel.teardown()
            UIApplication.shared.isIdleTimerDisabled = false
        }
        .statusBarHidden(true)
        .fullScreenCover(isPresented: $showReport) {
            ReportView(sessionId: viewModel.sessionId, isPresented: $isPresented)
        }
    }
}
