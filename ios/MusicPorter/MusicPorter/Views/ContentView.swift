import SwiftUI

/// Root view: shows connection flow, reconnecting state, or main app tabs.
struct ContentView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if appState.isConnected {
                MainTabView()
            } else if appState.isReconnecting, let server = appState.savedServer {
                ReconnectingView(server: server)
            } else {
                ServerDiscoveryView()
            }
        }
        .task {
            _ = await appState.attemptAutoReconnect()
        }
    }
}

/// Shown while the app retries connecting to a previously saved server.
struct ReconnectingView: View {
    @Environment(AppState.self) private var appState
    let server: ServerConnection

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "antenna.radiowaves.left.and.right")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
                .symbolEffect(.pulse, isActive: true)

            Text("Connecting to Server")
                .font(.title2.weight(.semibold))

            VStack(spacing: 8) {
                Text("\(server.host):\(server.port)")
                    .font(.body.monospaced())
                    .foregroundStyle(.secondary)

                if let ext = server.externalURL {
                    Text(ext)
                        .font(.caption.monospaced())
                        .foregroundStyle(.tertiary)
                }

                if !server.name.isEmpty {
                    Text(server.name)
                        .font(.subheadline)
                        .foregroundStyle(.tertiary)
                }
            }

            ProgressView()
                .scaleEffect(1.2)

            if appState.reconnectAttempt > 1 {
                Text("Attempt \(appState.reconnectAttempt)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button(role: .destructive) {
                appState.cancelAutoReconnect()
            } label: {
                Text("Cancel")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .padding(.horizontal, 40)
            .padding(.bottom, 32)
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
