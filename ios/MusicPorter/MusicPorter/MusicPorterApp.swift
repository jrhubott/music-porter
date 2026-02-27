import SwiftUI

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        BackgroundDownloadManager.shared.backgroundCompletionHandler = completionHandler
    }
}

@main
struct MusicPorterApp: App {
    /// Independent iOS app version — only bump when iOS code changes.
    static let appVersion = "1.2.0"

    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(appState)
                .preferredColorScheme(.dark)
                .onChange(of: scenePhase) { _, newPhase in
                    if newPhase == .active {
                        appState.downloadManager.reconcileBackgroundDownloads()
                    }
                }
        }
    }
}
