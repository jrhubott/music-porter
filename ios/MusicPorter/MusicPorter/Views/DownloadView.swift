import SwiftUI

/// Scope for USB export: all local playlists or a single one.
enum ExportScope {
    case all
    case playlist(String)
}

struct DownloadView: View {
    @Environment(AppState.self) private var appState
    @State private var exportDirs: [ExportDirectory] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var downloadingPlaylist: String?
    @State private var isDownloadingAll = false
    @State private var storageUsed = 0
    @State private var playlistToDelete: String?
    @State private var showExportPicker = false
    @State private var exportScope: ExportScope = .all
    @State private var downloadTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            List {
                actionBar
                bulkProgressSection
                exportProgressSection
                exportResultSection
                serverPlaylistsSection
                localStorageSection
                errorSection
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
            .sheet(isPresented: $showExportPicker) {
                DocumentExportPicker { url in
                    showExportPicker = false
                    if let url {
                        Task { await exportToFolder(url) }
                    }
                }
            }
        }
    }

    // MARK: - Action Bar

    private var actionBar: some View {
        Section {
            HStack(spacing: 12) {
                if isDownloadingAll || downloadingPlaylist != nil {
                    Button(role: .destructive) {
                        cancelDownload()
                    } label: {
                        Label("Cancel", systemImage: "xmark.circle")
                    }
                } else {
                    Button {
                        startDownloadAll()
                    } label: {
                        Label("Download All", systemImage: "arrow.down.circle")
                    }
                    .disabled(exportDirs.isEmpty)
                }

                Spacer()

                Button {
                    exportScope = .all
                    showExportPicker = true
                } label: {
                    Label("Export to USB", systemImage: "externaldrive")
                }
                .disabled(appState.usbExport.isExporting || !hasLocalFiles)
            }
            .buttonStyle(.borderless)
        }
    }

    // MARK: - Bulk Download Progress

    @ViewBuilder
    private var bulkProgressSection: some View {
        if isDownloadingAll, let bulk = appState.downloadManager.bulkProgress {
            Section("Download All") {
                VStack(alignment: .leading, spacing: 6) {
                    if bulk.completedPlaylists < bulk.totalPlaylists {
                        Text("Playlist \(bulk.completedPlaylists + 1) of \(bulk.totalPlaylists): \(bulk.currentPlaylistName)")
                            .font(.subheadline)

                        ProgressView(
                            value: Double(bulk.completedPlaylists),
                            total: Double(bulk.totalPlaylists)
                        )
                        .tint(.blue)

                        if let fileProgress = appState.downloadManager.downloadProgress {
                            HStack {
                                Text("File \(fileProgress.completed + 1) of \(fileProgress.total)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(fileProgress.currentFile)
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }
                            ProgressView(value: fileProgress.fraction)
                                .tint(.cyan)
                        }
                    } else {
                        Label("All playlists downloaded", systemImage: "checkmark.circle")
                            .foregroundStyle(.green)
                    }
                }
            }
        }
    }

    // MARK: - USB Export Progress

    @ViewBuilder
    private var exportProgressSection: some View {
        if appState.usbExport.isExporting {
            Section("USB Export") {
                VStack(alignment: .leading, spacing: 6) {
                    ProgressView(value: appState.usbExport.exportProgress)
                        .tint(.orange)
                    HStack {
                        Text("Exporting...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if let name = appState.usbExport.currentFileName {
                            Text(name)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var exportResultSection: some View {
        if !appState.usbExport.isExporting, let result = appState.usbExport.lastExportResult {
            Section {
                Label(result.message, systemImage: result.success ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(result.success ? .green : .red)
            }
        }
    }

    // MARK: - Server Playlists

    private var serverPlaylistsSection: some View {
        Section("Server Playlists") {
            if isLoading {
                ProgressView()
            }
            ForEach(exportDirs) { dir in
                playlistRow(dir)
            }
        }
    }

    private func playlistRow(_ dir: ExportDirectory) -> some View {
        let hasLocal = !appState.downloadManager.localFiles(playlist: dir.name).isEmpty

        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading) {
                    Text(dir.displayName)
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
                    startDownloadPlaylist(dir.name)
                } label: {
                    Image(systemName: "arrow.down.circle")
                }
                .disabled(downloadingPlaylist != nil || isDownloadingAll)
            }

            if downloadingPlaylist == dir.name, !isDownloadingAll,
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
            if hasLocal {
                Button(role: .destructive) {
                    playlistToDelete = dir.name
                } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
        .swipeActions(edge: .leading) {
            if hasLocal {
                Button {
                    exportScope = .playlist(dir.name)
                    showExportPicker = true
                } label: {
                    Label("Export", systemImage: "externaldrive")
                }
                .tint(.orange)
            }
        }
    }

    // MARK: - Local Storage

    private var localStorageSection: some View {
        Section("Local Storage") {
            LabeledContent("Used", value: ByteCountFormatter.string(
                fromByteCount: Int64(storageUsed), countStyle: .file))
        }
    }

    // MARK: - Error

    @ViewBuilder
    private var errorSection: some View {
        if let error {
            Section {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        }
    }

    // MARK: - Helpers

    private var hasLocalFiles: Bool {
        exportDirs.contains { !appState.downloadManager.localFiles(playlist: $0.name).isEmpty }
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        exportDirs = (try? await appState.apiClient.getExportDirectories()) ?? []
        storageUsed = appState.downloadManager.localStorageUsed()
        isLoading = false
    }

    private func startDownloadPlaylist(_ name: String) {
        downloadTask = Task {
            downloadingPlaylist = name
            error = nil
            do {
                try await appState.downloadManager.downloadAll(playlist: name)
            } catch is CancellationError {
                // User cancelled
            } catch {
                self.error = error.localizedDescription
            }
            storageUsed = appState.downloadManager.localStorageUsed()
            appState.downloadManager.clearProgress()
            downloadingPlaylist = nil
            downloadTask = nil
        }
    }

    private func startDownloadAll() {
        downloadTask = Task {
            isDownloadingAll = true
            error = nil
            appState.usbExport.reset()
            do {
                try await appState.downloadManager.downloadAllPlaylists(dirs: exportDirs)
            } catch is CancellationError {
                // User cancelled
            } catch {
                self.error = error.localizedDescription
            }
            storageUsed = appState.downloadManager.localStorageUsed()
            appState.downloadManager.clearProgress()
            isDownloadingAll = false
            downloadTask = nil
        }
    }

    private func cancelDownload() {
        downloadTask?.cancel()
    }

    private func exportToFolder(_ destDir: URL) async {
        appState.usbExport.reset()

        let urls: [URL]
        switch exportScope {
        case .all:
            urls = exportDirs.flatMap { appState.downloadManager.localFiles(playlist: $0.name) }
        case .playlist(let name):
            urls = appState.downloadManager.localFiles(playlist: name)
        }

        guard !urls.isEmpty else {
            error = "No local files to export"
            return
        }

        _ = await appState.usbExport.exportFiles(urls: urls, to: destDir)
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
