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

/// Main app tab navigation.
struct MainTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            DashboardView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Dashboard", systemImage: "gauge.medium") }

            PlaylistsView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Playlists", systemImage: "music.note.list") }

            AppleMusicView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Apple Music", systemImage: "music.quarternote.3") }

            PipelineView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Process", systemImage: "arrow.triangle.2.circlepath") }

            SettingsView()
                .safeAreaInset(edge: .bottom) { miniPlayerSpacer }
                .tabItem { Label("Settings", systemImage: "gear") }
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
