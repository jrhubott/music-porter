import SwiftUI

struct DownloadView: View {
    @Environment(AppState.self) private var appState
    @State private var exportDirs: [ExportDirectory] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var downloadingPlaylist: String?
    @State private var storageUsed = 0
    @State private var playlistToDelete: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Server Playlists") {
                    if isLoading {
                        ProgressView()
                    }
                    ForEach(exportDirs) { dir in
                        VStack(alignment: .leading, spacing: 8) {
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
                                    Image(systemName: "arrow.down.circle")
                                }
                                .disabled(downloadingPlaylist != nil)
                            }

                            if downloadingPlaylist == dir.name,
                               let progress = appState.downloadManager.downloadProgress {
                                VStack(alignment: .leading, spacing: 4) {
                                    ProgressView(value: progress.fraction)
                                        .tint(.blue)
                                    HStack {
                                        Text("Downloading \(progress.completed + 1) of \(progress.total)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Spacer()
                                        Text(progress.currentFile)
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                    }
                                }
                                .transition(.opacity)
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            if !appState.downloadManager.localFiles(playlist: dir.name).isEmpty {
                                Button(role: .destructive) {
                                    playlistToDelete = dir.name
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
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
            .alert("Delete Local Files?", isPresented: Binding(
                get: { playlistToDelete != nil },
                set: { if !$0 { playlistToDelete = nil } }
            )) {
                Button("Delete", role: .destructive) {
                    if let name = playlistToDelete {
                        deleteLocal(name)
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                if let name = playlistToDelete {
                    Text("All downloaded files for \"\(name)\" will be removed from this device.")
                }
            }
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
            try await appState.downloadManager.downloadAll(playlist: name)
            storageUsed = appState.downloadManager.localStorageUsed()
        } catch {
            self.error = error.localizedDescription
        }
        appState.downloadManager.clearProgress()
        downloadingPlaylist = nil
    }

    private func deleteLocal(_ name: String) {
        do {
            try appState.downloadManager.deletePlaylist(playlist: name)
            storageUsed = appState.downloadManager.localStorageUsed()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
