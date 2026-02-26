import SwiftUI

/// Root view: shows connection flow or main app tabs.
struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if appState.isConnected {
                MainTabView()
            } else {
                ServerDiscoveryView()
            }
        }
        .task {
            // Non-blocking: if reconnect succeeds, isConnected flips and
            // the view auto-switches to MainTabView
            await appState.attemptAutoReconnect()
        }
    }
}

/// Main app tab navigation — 3 tabs: Library, Process, Settings.
struct MainTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        TabView(selection: $state.selectedTab) {
            LibraryView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Library", systemImage: "music.note.list") }
                .tag(0)

            PipelineView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Process", systemImage: "arrow.triangle.2.circlepath") }
                .tag(1)

            SettingsView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Settings", systemImage: "gear") }
                .tag(2)
        }
        .overlay(alignment: .bottom) {
            if appState.audioPlayer.hasCurrentTrack {
                MiniPlayerView()
                    .padding(.bottom, 49) // standard tab bar height
            }
        }
        .animation(.easeInOut(duration: 0.25), value: appState.audioPlayer.hasCurrentTrack)
    }

    /// Invisible spacer that reserves scroll space so list content
    /// isn't hidden behind the mini player overlay.
    @ViewBuilder
    private var miniPlayerSpacer: some View {
        if appState.audioPlayer.hasCurrentTrack {
            Color.clear.frame(height: 64)
        }
    }
}
