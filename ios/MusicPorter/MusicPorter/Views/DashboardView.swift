import SwiftUI

struct DashboardView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = DashboardViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Server info card
                    if let status = vm.status {
                        GroupBox("Server") {
                            VStack(alignment: .leading, spacing: 8) {
                                LabeledContent("Version", value: status.version)
                                LabeledContent("Profile", value: status.profile)
                                HStack {
                                    Text("Cookies")
                                    Spacer()
                                    StatusBadge(
                                        text: status.cookies.valid ? "Valid" : "Invalid",
                                        color: status.cookies.valid ? .green : .red)
                                }
                                if let days = status.cookies.daysRemaining {
                                    LabeledContent("Expires", value: "\(days) days")
                                }
                                HStack {
                                    Text("Server")
                                    Spacer()
                                    StatusBadge(
                                        text: status.busy ? "Busy" : "Idle",
                                        color: status.busy ? .orange : .green)
                                }
                            }
                        }
                    }

                    // Library stats
                    if let status = vm.status {
                        GroupBox("Library") {
                            HStack(spacing: 20) {
                                StatCard(value: "\(status.library.playlists)", label: "Playlists")
                                StatCard(value: "\(status.library.files)", label: "Files")
                                StatCard(value: String(format: "%.0f MB", status.library.sizeMb), label: "Size")
                            }
                        }
                    }

                    // Summary
                    if let summary = vm.summary, !summary.playlists.isEmpty {
                        GroupBox("Playlists") {
                            ForEach(summary.playlists) { playlist in
                                HStack {
                                    Text(playlist.name)
                                    Spacer()
                                    Text("\(playlist.fileCount) files")
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if let error = vm.error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
                .padding()
            }
            .navigationTitle("Dashboard")
            .refreshable { await vm.load(api: appState.apiClient) }
            .task { await vm.load(api: appState.apiClient) }
        }
    }
}

struct StatCard: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2.bold())
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
