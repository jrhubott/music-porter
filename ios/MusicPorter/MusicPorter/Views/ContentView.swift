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
                .tabItem { Label("Dashboard", systemImage: "gauge.medium") }

            PlaylistsView()
                .tabItem { Label("Playlists", systemImage: "music.note.list") }

            PipelineView()
                .tabItem { Label("Pipeline", systemImage: "arrow.triangle.2.circlepath") }

            DownloadView()
                .tabItem { Label("Downloads", systemImage: "arrow.down.circle") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
    }
}
