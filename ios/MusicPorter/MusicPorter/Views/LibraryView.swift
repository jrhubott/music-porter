import SwiftUI
import MusicKit

enum ExportScope {
    case all
    case playlist(String)
}

/// Combined Library tab with segmented control for "My Playlists" and "Apple Music".
struct LibraryView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = PlaylistsViewModel()
    @State private var selectedSegment = 0

    @State private var showExportPicker = false
    @State private var exportScope: ExportScope = .all

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
        }
    }

    // MARK: - Playlists Content

    private var playlistsContent: some View {
        List {
            actionBar
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
        let serverTotal = vm.exportDirs.reduce(0) { $0 + $1.files }
        let cachedTotal = playlistCacheStatus.values.reduce(0) { $0 + $1.cached }
        let serverOnly = max(0, serverTotal - cachedTotal)
        if serverTotal > 0 {
            HStack(spacing: 4) {
                Image(systemName: "internaldrive")
                    .imageScale(.small)
                Text("\(cachedTotal) cached")
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
                                .foregroundStyle(.secondary)
                            Image(systemName: "cloud")
                                .imageScale(.small)
                                .foregroundStyle(.secondary)
                        }
                        if let status, status.cached > 0 {
                            if serverCount > 0 { Text("·") }
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
        }
        .swipeActions(edge: .leading) {
            if serverCount > 0 {
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
            if cacheSize > 0 {
                LabeledContent("Cache", value: CacheUtils.formatBytes(cacheSize))
            } else {
                Text("No cached files")
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Error

    @ViewBuilder
    private var errorSection: some View {
        if let error = vm.error {
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

        guard let cacheManager = appState.audioCacheManager else { return }
        for key in playlistKeys {
            var fileURLs: [URL] = []
            let cachedEntries = await cacheManager.getCachedFileInfos(key)
            for entry in cachedEntries {
                if let cachedURL = await cacheManager.isCached(entry.uuid) {
                    fileURLs.append(cachedURL)
                }
            }
            guard !fileURLs.isEmpty else { continue }
            _ = await appState.usbExport.exportFiles(
                urls: fileURLs, to: targetDir, subdirectory: key)
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
