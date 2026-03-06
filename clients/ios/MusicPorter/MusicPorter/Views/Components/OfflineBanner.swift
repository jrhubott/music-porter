import SwiftUI

/// Compact banner shown at the top of MainTabView when in offline mode.
struct OfflineBanner: View {
    @Environment(AppState.self) private var appState
    @State private var isReconnecting = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "wifi.slash")
                .font(.subheadline)
            Text("Offline Mode")
                .font(.subheadline.weight(.medium))
            Spacer()
            if isReconnecting {
                ProgressView()
                    .controlSize(.small)
            } else {
                Button("Reconnect") {
                    Task { await reconnect() }
                }
                .font(.subheadline.weight(.semibold))
                .buttonStyle(.borderless)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial)
    }

    private func reconnect() async {
        isReconnecting = true
        let success = await appState.attemptAutoReconnect()
        isReconnecting = false
        if success {
            appState.isOfflineMode = false
        }
    }
}
