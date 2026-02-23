import SwiftUI

struct DownloadView: View {
    @Environment(AppState.self) private var appState
    @State private var exportDirs: [ExportDirectory] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var downloadingPlaylist: String?
    @State private var storageUsed = 0

    var body: some View {
        NavigationStack {
            List {
                Section("Server Playlists") {
                    if isLoading {
                        ProgressView()
                    }
                    ForEach(exportDirs) { dir in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(dir.name)
                                    .font(.headline)
                                Text("\(dir.files) files on server")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()

                            let localCount = appState.downloadManager.localFiles(playlist: dir.name).count
                            if localCount > 0 {
                                Text("\(localCount) local")
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }

                            Button {
                                Task { await downloadPlaylist(dir.name) }
                            } label: {
                                if downloadingPlaylist == dir.name {
                                    ProgressView()
                                } else {
                                    Image(systemName: "arrow.down.circle")
                                }
                            }
                            .disabled(downloadingPlaylist != nil)
                        }
                    }
                }

                Section("Local Storage") {
                    LabeledContent("Used", value: ByteCountFormatter.string(
                        fromByteCount: Int64(storageUsed), countStyle: .file))
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Downloads")
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private func load() async {
        isLoading = true
        exportDirs = (try? await appState.apiClient.getExportDirectories()) ?? []
        storageUsed = appState.downloadManager.localStorageUsed()
        isLoading = false
    }

    private func downloadPlaylist(_ name: String) async {
        downloadingPlaylist = name
        error = nil
        do {
            let _ = try await appState.downloadManager.downloadAll(playlist: name)
            storageUsed = appState.downloadManager.localStorageUsed()
        } catch {
            self.error = error.localizedDescription
        }
        downloadingPlaylist = nil
    }
}
