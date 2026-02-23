import SwiftUI

/// Scope for USB export: all local playlists or a single one.
enum ExportScope {
    case all
    case playlist(String)
}

struct PlaylistsView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = PlaylistsViewModel()

    // Download state
    @State private var downloadingPlaylist: String?
    @State private var isDownloadingAll = false
    @State private var storageUsed = 0
    @State private var playlistToDelete: String?
    @State private var showExportPicker = false
    @State private var exportScope: ExportScope = .all
    @State private var downloadTask: Task<Void, Never>?
    @State private var downloadError: String?

    var body: some View {
        @Bindable var vmBindable = vm
        NavigationStack {
            List {
                actionBar
                bulkProgressSection
                exportProgressSection
                exportResultSection
                playlistsSection
                localStorageSection
                errorSection
            }
            .navigationTitle("Playlists")
            .navigationDestination(for: Playlist.self) { playlist in
                PlaylistDetailView(playlist: playlist)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        vm.showAddSheet = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $vmBindable.showAddSheet) {
                AddPlaylistSheet(vm: vm)
            }
            .sheet(isPresented: $showExportPicker) {
                DocumentExportPicker { url in
                    showExportPicker = false
                    if let url {
                        Task { await exportToFolder(url) }
                    }
                }
            }
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
            .refreshable {
                await load()
            }
            .task {
                await load()
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
                    .disabled(vm.exportDirs.isEmpty)
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

    // MARK: - Playlists

    private var playlistsSection: some View {
        Section("Server Playlists") {
            if vm.isLoading {
                ProgressView()
            }
            ForEach(vm.playlists) { playlist in
                NavigationLink(value: playlist) {
                    playlistRow(playlist)
                }
            }
            .onDelete { indexSet in
                for index in indexSet {
                    let key = vm.playlists[index].key
                    Task { await vm.deletePlaylist(api: appState.apiClient, key: key) }
                }
            }
        }
    }

    private func playlistRow(_ playlist: Playlist) -> some View {
        let serverCount = vm.fileCount(for: playlist.key)
        let localCount = appState.downloadManager.localFiles(playlist: playlist.key).count
        let hasLocal = localCount > 0
        let isDownloadingThis = downloadingPlaylist == playlist.key && !isDownloadingAll

        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(playlist.name)
                        .font(.headline)
                    HStack(spacing: 4) {
                        if serverCount > 0 {
                            Text("\(serverCount)")
                                .foregroundStyle(localCount >= serverCount && serverCount > 0 ? .green : .secondary)
                            Image(systemName: "cloud")
                                .imageScale(.small)
                                .foregroundStyle(localCount >= serverCount && serverCount > 0 ? .green : .secondary)
                        }
                        if localCount > 0 {
                            if serverCount > 0 { Text("·") }
                            Text("\(localCount)")
                                .foregroundStyle(.green)
                            Image(systemName: "iphone")
                                .imageScale(.small)
                                .foregroundStyle(.green)
                        }
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                Spacer()

                Button {
                    startDownloadPlaylist(playlist.key)
                } label: {
                    Image(systemName: "arrow.down.circle")
                }
                .buttonStyle(.borderless)
                .disabled(downloadingPlaylist != nil || isDownloadingAll)
            }

            if isDownloadingThis, let progress = appState.downloadManager.downloadProgress {
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
                    playlistToDelete = playlist.key
                } label: {
                    Label("Delete Local", systemImage: "trash")
                }
            }
        }
        .swipeActions(edge: .leading) {
            if hasLocal {
                Button {
                    exportScope = .playlist(playlist.key)
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
        if let error = vm.error ?? downloadError {
            Section {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        }
    }

    // MARK: - Helpers

    private var hasLocalFiles: Bool {
        vm.exportDirs.contains { !appState.downloadManager.localFiles(playlist: $0.name).isEmpty }
    }

    // MARK: - Actions

    private func load() async {
        await vm.load(api: appState.apiClient)
        storageUsed = appState.downloadManager.localStorageUsed()
    }

    private func startDownloadPlaylist(_ name: String) {
        downloadTask = Task {
            downloadingPlaylist = name
            downloadError = nil
            do {
                try await appState.downloadManager.downloadAll(playlist: name)
            } catch is CancellationError {
                // User cancelled
            } catch {
                downloadError = error.localizedDescription
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
            downloadError = nil
            appState.usbExport.reset()
            do {
                try await appState.downloadManager.downloadAllPlaylists(dirs: vm.exportDirs)
            } catch is CancellationError {
                // User cancelled
            } catch {
                downloadError = error.localizedDescription
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
            urls = vm.exportDirs.flatMap { appState.downloadManager.localFiles(playlist: $0.name) }
        case .playlist(let name):
            urls = appState.downloadManager.localFiles(playlist: name)
        }

        guard !urls.isEmpty else {
            downloadError = "No local files to export"
            return
        }

        _ = await appState.usbExport.exportFiles(urls: urls, to: destDir)
    }

    private func deleteLocal(_ name: String) {
        do {
            try appState.downloadManager.deletePlaylist(playlist: name)
            storageUsed = appState.downloadManager.localStorageUsed()
        } catch {
            downloadError = error.localizedDescription
        }
    }
}

struct AddPlaylistSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @Bindable var vm: PlaylistsViewModel

    var body: some View {
        NavigationStack {
            Form {
                TextField("Key (e.g. Pop_Workout)", text: $vm.newKey)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                TextField("Apple Music URL", text: $vm.newURL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                TextField("Display Name", text: $vm.newName)
            }
            .navigationTitle("Add Playlist")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        Task {
                            await vm.addPlaylist(api: appState.apiClient)
                        }
                    }
                    .disabled(vm.newKey.isEmpty || vm.newURL.isEmpty || vm.newName.isEmpty)
                }
            }
        }
    }
}
