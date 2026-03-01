import SwiftUI

@main
struct MusicPorterApp: App {
    /// Independent iOS app version — only bump when iOS code changes.
    static let appVersion = "1.5.0"

    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(appState)
                .preferredColorScheme(.dark)
        }
    }
}
