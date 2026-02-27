import SwiftUI
import MusicKit

/// Combined Library tab with segmented control for "My Playlists" and "Apple Music".
struct LibraryView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.scenePhase) private var scenePhase
    @State private var vm = PlaylistsViewModel()
    @State private var selectedSegment = 0

    // Download state
    @State private var downloadingPlaylist: String?
    @State private var isDownloadingAll = false
    @State private var storageUsed = 0
    @State private var playlistToDelete: String?
    @State private var showExportPicker = false
    @State private var exportScope: ExportScope = .all
    @State private var downloadTask: Task<Void, Never>?
    @State private var downloadError: String?

    // Delete server data state
    @State private var serverDeleteKey: String?
    @State private var serverDeleteSource = true
    @State private var serverDeleteExport = true
    @State private var serverDeleteConfig = false

    var body: some View {
        @Bindable var vmBindable = vm
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $selectedSegment) {
                    Text("My Playlists").tag(0)
                    Text("Apple Music").tag(1)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)

                Group {
                    if selectedSegment == 0 {
                        playlistsContent
                    } else {
                        appleMusicContent
                    }
                }
            }
            .navigationTitle("Library")
            .navigationDestination(for: Playlist.self) { playlist in
                PlaylistDetailView(playlist: playlist)
            }
            .navigationDestination(for: MusicKit.Playlist.self) { playlist in
                AppleMusicPlaylistDetailView(playlist: playlist)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if selectedSegment == 0 {
                        Button {
                            vm.showAddSheet = true
                        } label: {
                            Image(systemName: "plus")
                        }
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
            .sheet(isPresented: Binding(
                get: { serverDeleteKey != nil },
                set: { if !$0 { serverDeleteKey = nil } }
            )) {
                DeleteServerDataSheet(
                    key: serverDeleteKey ?? "",
                    deleteSource: $serverDeleteSource,
                    deleteExport: $serverDeleteExport,
                    removeConfig: $serverDeleteConfig
                ) {
                    if let key = serverDeleteKey {
                        Task {
                            await vm.deletePlaylistData(
                                api: appState.apiClient, key: key,
                                deleteSource: serverDeleteSource,
                                deleteExport: serverDeleteExport,
                                removeConfig: serverDeleteConfig)
                            await load()
                        }
                    }
                    serverDeleteKey = nil
                }
                .presentationDetents([.medium])
            }
            .refreshable {
                await load()
                if selectedSegment == 1 {
                    await vm.loadAppleMusic(musicKit: appState.musicKit)
                }
            }
            .task {
                await load()
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .active {
                    resumeIfStalled()
                }
            }
        }
    }

    // MARK: - Playlists Content

    private var playlistsContent: some View {
        List {
            actionBar
            bulkProgressSection
            exportProgressSection
            exportResultSection
            playlistsSection
            localStorageSection
            errorSection
        }
    }

    // MARK: - Apple Music Content

    private var appleMusicContent: some View {
        List {
            guidedFlowBanner
            appleMusicSection
            errorSection
        }
        .searchable(text: Binding(
            get: { vm.searchQuery },
            set: { newValue in
                vm.searchQuery = newValue
                Task { await vm.searchAppleMusic(query: newValue, musicKit: appState.musicKit) }
            }
        ), prompt: "Search Apple Music")
        .task {
            await vm.loadAppleMusic(musicKit: appState.musicKit)
        }
    }

    // MARK: - Guided Flow Banner

    @ViewBuilder
    private var guidedFlowBanner: some View {
        if vm.showProcessPrompt, let playlist = vm.lastAddedPlaylist {
            Section {
                VStack(spacing: 12) {
                    Label("\"\(playlist.name)\" added!", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                        .font(.subheadline.weight(.medium))
                    Button {
                        appState.pendingPipelinePlaylist = playlist
                        appState.selectedTab = 1 // Process tab
                        vm.dismissProcessPrompt()
                    } label: {
                        HStack {
                            Spacer()
                            Label("Process Now", systemImage: "play.fill")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Later") {
                        vm.dismissProcessPrompt()
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
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
                .disabled(appState.usbExport.isExporting || !hasExportableFiles)
            }
            .buttonStyle(.borderless)

            Toggle("Also save to device", isOn: Binding(
                get: { appState.usbExport.cacheToDevice },
                set: { appState.usbExport.cacheToDevice = $0 }
            ))
            .font(.subheadline)

            Text("Files are organized into playlist folders on USB.")
                .font(.caption2)
                .foregroundStyle(.tertiary)

            exportSourceSummary
        }
    }

    @ViewBuilder
    private var exportSourceSummary: some View {
        let localCount = vm.exportDirs.reduce(0) { $0 + appState.downloadManager.localFiles(playlist: $1.name).count }
        let serverTotal = vm.exportDirs.reduce(0) { $0 + $1.files }
        let serverOnly = max(0, serverTotal - localCount)
        if serverTotal > 0 {
            HStack(spacing: 4) {
                Image(systemName: "iphone")
                    .imageScale(.small)
                Text("\(localCount) local")
                if serverOnly > 0 {
                    Text("·")
                    Image(systemName: "cloud")
                        .imageScale(.small)
                    Text("\(serverOnly) from server")
                }
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
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
                        if let source = appState.usbExport.currentFileSource {
                            switch source {
                            case .local:
                                Image(systemName: "iphone")
                                    .imageScale(.small)
                                    .foregroundStyle(.secondary)
                            case .server:
                                Image(systemName: "cloud")
                                    .imageScale(.small)
                                    .foregroundStyle(.secondary)
                            }
                        }
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

    // MARK: - Playlists Section

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
            Button(role: .destructive) {
                serverDeleteSource = true
                serverDeleteExport = true
                serverDeleteConfig = false
                serverDeleteKey = playlist.key
            } label: {
                Label("Delete Server Data", systemImage: "server.rack")
            }
            if hasLocal {
                Button(role: .destructive) {
                    playlistToDelete = playlist.key
                } label: {
                    Label("Delete Local", systemImage: "trash")
                }
            }
        }
        .swipeActions(edge: .leading) {
            if hasLocal || serverCount > 0 {
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

    // MARK: - Apple Music Section

    private var appleMusicSection: some View {
        Section("Apple Music Library") {
            if !appState.musicKit.isAuthorized {
                Button("Authorize Apple Music") {
                    Task { await appState.musicKit.requestAuthorization() }
                }
            } else {
                if vm.isLoadingAppleMusic {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                }
                ForEach(vm.appleMusicPlaylists) { playlist in
                    NavigationLink(value: playlist) {
                        appleMusicRow(playlist)
                    }
                }
                if let appleMusicError = vm.appleMusicError {
                    Label(appleMusicError, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }
        }
    }

    private func appleMusicRow(_ playlist: MusicKit.Playlist) -> some View {
        HStack {
            VStack(alignment: .leading) {
                Text(playlist.name)
                    .font(.headline)
                if let desc = playlist.shortDescription {
                    Text(desc)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if let url = playlist.url {
                if vm.isAlreadyAdded(url: url) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else if vm.addingPlaylistURL == url.absoluteString {
                    ProgressView()
                } else {
                    Button {
                        Task {
                            await vm.addAppleMusicPlaylist(
                                api: appState.apiClient,
                                url: url.absoluteString,
                                name: playlist.name
                            )
                        }
                    } label: {
                        Image(systemName: "plus.circle")
                            .foregroundStyle(.blue)
                    }
                    .buttonStyle(.borderless)
                }
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

    private var hasExportableFiles: Bool {
        !vm.exportDirs.isEmpty && vm.exportDirs.contains { $0.files > 0 }
    }

    // MARK: - Actions

    private func load() async {
        await vm.load(api: appState.apiClient)
        storageUsed = appState.downloadManager.localStorageUsed()
    }

    private func startDownloadPlaylist(_ name: String) {
        // Cancel any stale suspended task to avoid duplicates
        downloadTask?.cancel()
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
        // Cancel any stale suspended task to avoid duplicates
        downloadTask?.cancel()
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

    /// Resume a stalled download after returning from background.
    /// The foreground Task may have been suspended by the OS; this detects
    /// remaining files and starts a new download task that skips completed files.
    private func resumeIfStalled() {
        // Only resume if our foreground task isn't actively running
        guard downloadTask == nil || downloadTask?.isCancelled == true else { return }

        if isDownloadingAll {
            // Bulk download was interrupted — restart with remaining dirs
            startDownloadAll()
        } else if let playlist = appState.downloadManager.stalledDownloadPlaylist() {
            // Single playlist download was interrupted — restart it
            startDownloadPlaylist(playlist)
        }
    }

    private func cancelDownload() {
        downloadTask?.cancel()
        appState.downloadManager.cancelDownloads()
    }

    private func exportToFolder(_ destDir: URL) async {
        appState.usbExport.reset()

        let playlistKeys: [String]
        switch exportScope {
        case .all:
            playlistKeys = vm.exportDirs.filter { $0.files > 0 }.map(\.name)
        case .playlist(let name):
            playlistKeys = [name]
        }

        var groups: [PlaylistExportGroup] = []

        for key in playlistKeys {
            let localFiles = appState.downloadManager.localFiles(playlist: key)
            let localNames = Set(localFiles.map(\.lastPathComponent))

            // Build local entries
            var entries = localFiles.map { url in
                ExportManifestEntry(playlist: key, filename: url.lastPathComponent, source: .local(url))
            }

            // Fetch server file list for files not available locally
            if let serverFiles = try? await appState.apiClient.getFiles(playlist: key) {
                for track in serverFiles.files where !localNames.contains(track.filename) {
                    entries.append(ExportManifestEntry(
                        playlist: key, filename: track.filename,
                        source: .server(playlist: key, filename: track.filename)))
                }
            }

            if !entries.isEmpty {
                groups.append(PlaylistExportGroup(playlist: key, entries: entries))
            }
        }

        guard !groups.isEmpty else {
            downloadError = "No files to export"
            return
        }

        _ = await appState.usbExport.exportFiles(
            groups: groups, to: destDir,
            cacheToDevice: appState.usbExport.cacheToDevice)
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
