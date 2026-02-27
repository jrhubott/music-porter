import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    if let server = appState.currentServer {
                        HStack(spacing: 12) {
                            connectionIcon
                                .font(.title2)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(server.name)
                                    .font(.headline)
                                connectionLabel
                            }
                        }

                        if let baseURL = appState.apiClient.activeBaseURL {
                            LabeledContent("Active URL", value: baseURL.absoluteString)
                        }
                        if server.hasExternalURL {
                            LabeledContent("External URL", value: server.externalURL!)
                        }
                        LabeledContent("Local URL", value: server.localURL?.absoluteString ?? "\(server.host):\(server.port)")
                    }
                    Button("Disconnect", role: .destructive) {
                        appState.disconnect()
                    }
                }

                Section("Sync & Status") {
                    NavigationLink {
                        SyncStatusView()
                    } label: {
                        Label("Sync Status", systemImage: "arrow.left.arrow.right")
                    }
                    NavigationLink {
                        DashboardView()
                    } label: {
                        Label("Server Dashboard", systemImage: "gauge.medium")
                    }
                }

                if !appState.profiles.isEmpty {
                    Section("Output Profile") {
                        Picker("Profile", selection: Binding(
                            get: { appState.activeProfile },
                            set: { appState.activeProfile = $0 }
                        )) {
                            ForEach(Array(appState.profiles.keys.sorted()), id: \.self) { name in
                                Text(name).tag(name)
                            }
                        }
                        if let profile = appState.profiles[appState.activeProfile] {
                            LabeledContent("Description", value: profile.description)
                            if !profile.usbDir.isEmpty {
                                LabeledContent("USB Directory", value: profile.usbDir)
                            }
                        }
                    }
                }

                Section("About") {
                    LabeledContent("App Version", value: MusicPorterApp.appVersion)
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Settings")
            .task { await loadSettings() }
        }
    }

    @ViewBuilder
    private var connectionIcon: some View {
        if appState.apiClient.connectionType == .external {
            Image(systemName: "globe")
                .foregroundStyle(.blue)
        } else {
            Image(systemName: "house")
                .foregroundStyle(.green)
        }
    }

    @ViewBuilder
    private var connectionLabel: some View {
        if let type = appState.apiClient.connectionType {
            Text(type == .local ? "Connected via Local Network" : "Connected via External URL")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func loadSettings() async {
        // Profiles are fetched by AppState on connect; refresh if empty
        if appState.profiles.isEmpty {
            if let settings = try? await appState.apiClient.getSettings() {
                appState.profiles = settings.profiles
            }
        }
    }
}
