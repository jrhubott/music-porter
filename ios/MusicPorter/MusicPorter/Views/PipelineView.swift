import SwiftUI

struct PipelineView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = OperationViewModel()
    @State private var playlists: [Playlist] = []
    @State private var selectedPlaylist: Playlist?
    @State private var customURL = ""
    @State private var useAuto = false
    @State private var preset = "lossless"
    @State private var syncAfter = false
    @State private var destinations: [SyncDestination] = []
    @State private var selectedDestination: String?
    @State private var showExportPicker = false
    @State private var tasks: [TaskInfo] = []
    @State private var eqConfig = EQConfig()

    let presets = ["lossless", "high", "medium", "low"]

    var body: some View {
        NavigationStack {
            Form {
                if appState.isOfflineMode {
                    offlineSection
                } else {
                    if !vm.isRunning {
                        sourceSection
                        advancedSection
                        processButton
                    }

                    if vm.isRunning || !vm.logMessages.isEmpty {
                        ProgressPanel(vm: vm)
                    }

                    postProcessSection
                }
                taskHistorySection
            }
            .navigationTitle("Process")
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
            .task {
                guard !appState.isOfflineMode else { return }
                await loadData()
            }
            .onChange(of: selectedPlaylist) { _, newPlaylist in
                if let key = newPlaylist?.key {
                    Task { await loadEQForPlaylist(key) }
                }
            }
            .onChange(of: appState.pendingPipelinePlaylist) { _, pending in
                if let pending {
                    selectedPlaylist = pending
                    useAuto = false
                    customURL = ""
                    appState.pendingPipelinePlaylist = nil
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

    // MARK: - Offline

    private var offlineSection: some View {
        Section {
            VStack(spacing: 12) {
                Image(systemName: "wifi.slash")
                    .font(.system(size: 36))
                    .foregroundStyle(.secondary)
                Text("Processing requires a server connection")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 20)
        }
    }

    // MARK: - Source

    private var sourceSection: some View {
        Section("Source") {
            Toggle("Process all playlists", isOn: $useAuto)

            if !useAuto {
                Picker("Playlist", selection: $selectedPlaylist) {
                    Text("None").tag(nil as Playlist?)
                    ForEach(playlists) { p in
                        Text(p.name).tag(p as Playlist?)
                    }
                }

                TextField("Or enter Apple Music URL", text: $customURL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
            }
        }
    }

    // MARK: - Advanced Options

    private var advancedSection: some View {
        Section {
            DisclosureGroup("Advanced Options") {
                Picker("Quality Preset", selection: $preset) {
                    ForEach(presets, id: \.self) { Text($0) }
                }
                Toggle("Sync after processing", isOn: $syncAfter)
                if syncAfter && !destinations.isEmpty {
                    Picker("Destination", selection: $selectedDestination) {
                        Text("Select...").tag(nil as String?)
                        ForEach(destinations) { dest in
                            Text(dest.name).tag(dest.name as String?)
                        }
                    }
                }
                eqSection
            }
        }
    }

    private var eqSection: some View {
        Group {
            Text("EQ Audio Effects")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
                .padding(.top, 4)
            Toggle("Loudness Normalization", isOn: $eqConfig.loudnorm)
            Toggle("Bass Boost", isOn: $eqConfig.bassBoost)
            Toggle("Treble Boost", isOn: $eqConfig.trebleBoost)
            Toggle("Dynamic Compression", isOn: $eqConfig.compressor)
        }
    }

    // MARK: - Process Button

    private var processButton: some View {
        Section {
            Button {
                Task { await runPipeline() }
            } label: {
                HStack {
                    Spacer()
                    Label("Process", systemImage: "play.fill")
                        .fontWeight(.semibold)
                    Spacer()
                }
            }
            .disabled(!canRun)
        }
    }

    // MARK: - Post-Process Actions

    @ViewBuilder
    private var postProcessSection: some View {
        if !vm.isRunning && vm.isCompleted {
            Section("Next Steps") {
                Button {
                    showExportPicker = true
                } label: {
                    Label("Export to USB", systemImage: "externaldrive")
                }
            }
        }
    }

    // MARK: - Task History

    private var taskHistorySection: some View {
        Section("Recent Operations") {
            if tasks.isEmpty {
                Text("No recent operations")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(tasks.prefix(10)) { task in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(task.operation)
                                .font(.subheadline.weight(.medium))
                            Spacer()
                            StatusBadge(
                                text: task.status,
                                color: statusColor(task.status))
                        }
                        Text(task.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if let elapsed = task.elapsed {
                            Text(String(format: "%.1fs", elapsed))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                if tasks.count > 10 {
                    NavigationLink("View All") {
                        OperationsView()
                    }
                    .font(.subheadline)
                }
            }
        }
    }

    // MARK: - Helpers

    private var canRun: Bool {
        let hasSource = useAuto || selectedPlaylist != nil || !customURL.isEmpty
        if syncAfter && !destinations.isEmpty {
            return hasSource && selectedDestination != nil
        }
        return hasSource
    }

    private func loadData() async {
        async let p = appState.apiClient.getPlaylists()
        async let d = appState.apiClient.getSyncDestinations()
        async let t = appState.apiClient.getTasks()
        playlists = (try? await p) ?? []
        let destResponse = try? await d
        destinations = destResponse?.destinations ?? []
        tasks = (try? await t) ?? []
        // Auto-load EQ for first playlist
        if let first = playlists.first {
            await loadEQForPlaylist(first.key)
        }
    }

    private func loadEQForPlaylist(_ playlist: String) async {
        if let resolved = try? await appState.apiClient.resolveEQ(profile: appState.activeProfile, playlist: playlist) {
            eqConfig = resolved.eq
        }
    }

    private func runPipeline() async {
        let syncDest = syncAfter ? selectedDestination : nil
        let eqParam = eqConfig.anyEnabled ? eqConfig : nil
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.runPipeline(
                playlist: selectedPlaylist?.key,
                url: customURL.isEmpty ? nil : customURL,
                auto: useAuto,
                preset: preset,
                syncDestination: syncDest,
                eq: eqParam
            )
        }
        // Refresh task history after completion
        tasks = (try? await appState.apiClient.getTasks()) ?? []
    }

    private func exportToFolder(_ destDir: URL) async {
        guard let playlist = selectedPlaylist,
              let cacheManager = appState.audioCacheManager else { return }

        // Append profile's USB directory if configured
        let usbDir = appState.usbDir
        let targetDir = usbDir.isEmpty ? destDir : destDir.appendingPathComponent(usbDir)

        var fileURLs: [URL] = []
        let cachedEntries = await cacheManager.getCachedFileInfos(playlist.key)
        for entry in cachedEntries {
            if let cachedURL = await cacheManager.isCached(entry.uuid) {
                fileURLs.append(cachedURL)
            }
        }

        guard !fileURLs.isEmpty else { return }

        _ = await appState.usbExport.exportFiles(
            urls: fileURLs, to: targetDir, subdirectory: playlist.name)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        case "cancelled": return .orange
        default: return .gray
        }
    }
}
