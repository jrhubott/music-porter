import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var settings: SettingsResponse?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    if let server = appState.currentServer {
                        LabeledContent("Host", value: "\(server.host):\(server.port)")
                        LabeledContent("Name", value: server.name)
                    }
                    Button("Disconnect", role: .destructive) {
                        appState.disconnect()
                    }
                }

                if let settings {
                    Section("Profiles") {
                        ForEach(Array(settings.profiles.keys.sorted()), id: \.self) { name in
                            if let profile = settings.profiles[name] {
                                VStack(alignment: .leading) {
                                    Text(name).font(.headline)
                                    Text(profile.description)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                Section("Operations") {
                    NavigationLink("Task History") {
                        OperationsView()
                    }
                    NavigationLink("Apple Music") {
                        AppleMusicBrowserView()
                    }
                }

                Section("About") {
                    LabeledContent("App Version", value: "1.0.0")
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

    private func loadSettings() async {
        do {
            settings = try await appState.apiClient.getSettings()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
