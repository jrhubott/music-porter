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
    @State private var backgroundedAt: Date?
    @State private var downloadGeneration = 0

    /// Minimum seconds in background before considering a download stalled.
    /// iOS reclaims sockets after suspension; connections are dead after this threshold.
    private let backgroundStallThreshold: TimeInterval = 3

    // Cache state
    @State private var playlistCacheStatus: [String: PlaylistCacheStatus] = [:]
    @State private var cacheSize: Int64 = 0

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
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if !appState.activeProfile.isEmpty {
                        Text(appState.activeProfile)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.ultraThinMaterial)
                            .clipShape(Capsule())
                    }
                }
            }
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
                    backgroundedAt = nil
                } else if newPhase == .background {
                    backgroundedAt = Date()
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
        let isPinned = appState.cachePreferences.isPinned(playlist.key)
        let status = playlistCacheStatus[playlist.key]

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
                        if let status, status.cached > 0 {
                            Text("·")
                            if status.cached >= status.total && status.total > 0 {
                                Image(systemName: "checkmark")
                                    .imageScale(.small)
                                    .foregroundStyle(.blue)
                            } else {
                                Text("\(status.cached)/\(status.total)")
                                    .foregroundStyle(.blue)
                            }
                            Image(systemName: "internaldrive")
                                .imageScale(.small)
                                .foregroundStyle(.blue)
                        }
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                Spacer()

                Button {
                    if isPinned {
                        appState.cachePreferences.unpinPlaylist(playlist.key)
                    } else {
                        appState.cachePreferences.pinPlaylist(playlist.key)
                    }
                } label: {
                    Image(systemName: isPinned ? "pin.fill" : "pin")
                        .foregroundStyle(isPinned ? .blue : .secondary)
                }
                .buttonStyle(.borderless)

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
            if status != nil && (status?.cached ?? 0) > 0 {
                Button {
                    Task {
                        await appState.audioCacheManager?.clearPlaylist(playlist.key)
                        await loadCacheStatus()
                    }
                } label: {
                    Label("Clear Cache", systemImage: "internaldrive")
                }
                .tint(.purple)
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
            LabeledContent("Downloads", value: ByteCountFormatter.string(
                fromByteCount: Int64(storageUsed), countStyle: .file))
            if cacheSize > 0 {
                LabeledContent("Cache", value: CacheUtils.formatBytes(cacheSize))
            }
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
        await loadCacheStatus()
    }

    private func loadCacheStatus() async {
        guard let cacheManager = appState.audioCacheManager else { return }
        cacheSize = await cacheManager.getTotalSize()
        var statuses: [String: PlaylistCacheStatus] = [:]
        for playlist in vm.playlists {
            let serverCount = vm.fileCount(for: playlist.key)
            let pinned = appState.cachePreferences.isPinned(playlist.key)
            let status = await cacheManager.getPlaylistCacheStatus(
                key: playlist.key, totalFiles: serverCount, pinned: pinned)
            statuses[playlist.key] = status
        }
        playlistCacheStatus = statuses
    }

    private func startDownloadPlaylist(_ name: String) {
        downloadTask?.cancel()
        downloadGeneration += 1
        let generation = downloadGeneration
        downloadTask = Task {
            downloadingPlaylist = name
            downloadError = nil
            do {
                try await appState.downloadManager.downloadAll(playlist: name)
            } catch is CancellationError {
                // User cancelled or replaced by resumeIfStalled
            } catch {
                downloadError = error.localizedDescription
            }
            // Only clean up if we're still the active download generation.
            // A newer task (from resumeIfStalled) may have replaced us.
            guard downloadGeneration == generation else { return }
            storageUsed = appState.downloadManager.localStorageUsed()
            appState.downloadManager.clearProgress()
            downloadingPlaylist = nil
            downloadTask = nil
        }
    }

    private func startDownloadAll() {
        downloadTask?.cancel()
        downloadGeneration += 1
        let generation = downloadGeneration
        downloadTask = Task {
            isDownloadingAll = true
            downloadError = nil
            appState.usbExport.reset()
            do {
                try await appState.downloadManager.downloadAllPlaylists(dirs: vm.exportDirs)
            } catch is CancellationError {
                // User cancelled or replaced by resumeIfStalled
            } catch {
                downloadError = error.localizedDescription
            }
            guard downloadGeneration == generation else { return }
            storageUsed = appState.downloadManager.localStorageUsed()
            appState.downloadManager.clearProgress()
            isDownloadingAll = false
            downloadTask = nil
        }
    }

    /// Resume a stalled download after returning from background.
    /// iOS reclaims sockets after suspension; this uses background duration
    /// to distinguish brief app switches from real stalls.
    private func resumeIfStalled() {
        guard appState.downloadManager.stalledDownloadPlaylist() != nil else { return }

        if downloadTask == nil {
            // App was relaunched or previous download completed/failed — restart
            if isDownloadingAll {
                startDownloadAll()
            } else if let playlist = appState.downloadManager.stalledDownloadPlaylist() {
                startDownloadPlaylist(playlist)
            }
            return
        }

        // Download task exists. Only intervene if backgrounded long enough for
        // the OS to reclaim sockets. Brief app switches don't interrupt.
        guard let bgTime = backgroundedAt,
              Date().timeIntervalSince(bgTime) > backgroundStallThreshold else { return }

        // Connections are dead after suspension — cancel stale task, start fresh
        downloadTask?.cancel()
        downloadTask = nil

        if isDownloadingAll {
            startDownloadAll()
        } else if let playlist = appState.downloadManager.stalledDownloadPlaylist() {
            startDownloadPlaylist(playlist)
        }
    }

    private func cancelDownload() {
        downloadTask?.cancel()
        appState.downloadManager.cancelDownloads()
    }

    private func exportToFolder(_ destDir: URL) async {
        appState.usbExport.reset()

        // Append profile's USB directory if configured
        let usbDir = appState.usbDir
        let targetDir = usbDir.isEmpty ? destDir : destDir.appendingPathComponent(usbDir)

        let playlistKeys: [String]
        switch exportScope {
        case .all:
            playlistKeys = vm.exportDirs.filter { $0.files > 0 }.map(\.name)
        case .playlist(let name):
            playlistKeys = [name]
        }

        for key in playlistKeys {
            var fileURLs = appState.downloadManager.localFiles(playlist: key)

            // Supplement with cached files not already in local downloads
            if let cacheManager = appState.audioCacheManager {
                let localNames = Set(fileURLs.map(\.lastPathComponent))
                let cachedEntries = await cacheManager.getCachedFileInfos(key)
                for entry in cachedEntries {
                    // Skip files already in local downloads
                    if localNames.contains(entry.displayFilename) { continue }
                    if let cachedURL = await cacheManager.isCached(entry.uuid) {
                        fileURLs.append(cachedURL)
                    }
                }
            }

            guard !fileURLs.isEmpty else { continue }
            _ = await appState.usbExport.exportFiles(
                urls: fileURLs, to: targetDir, subdirectory: key)
        }
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
