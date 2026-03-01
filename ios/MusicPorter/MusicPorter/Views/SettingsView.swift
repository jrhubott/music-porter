import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var error: String?
    @State private var cacheSize: Int64 = 0
    @State private var showClearCacheConfirmation = false

    /// Max cache size options in bytes. 0 = unlimited.
    private static let cacheSizeOptions: [(label: String, bytes: Int64)] = [
        ("5 GB", 5 * 1024 * 1024 * 1024),
        ("10 GB", 10 * 1024 * 1024 * 1024),
        ("20 GB", 20 * 1024 * 1024 * 1024),
        ("50 GB", 50 * 1024 * 1024 * 1024),
        ("Unlimited", 0),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    if let server = appState.currentServer {
                        HStack(spacing: 12) {
                            connectionIcon
                                .font(.title2)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(server.name)
                                    .font(.headline)
                                connectionLabel
                            }
                        }

                        if let baseURL = appState.apiClient.activeBaseURL {
                            LabeledContent("Active URL", value: baseURL.absoluteString)
                        }
                        if server.hasExternalURL {
                            LabeledContent("External URL", value: server.externalURL!)
                        }
                        LabeledContent("Local URL", value: server.localURL?.absoluteString ?? "\(server.host):\(server.port)")
                    }
                    Button("Disconnect", role: .destructive) {
                        appState.disconnect()
                    }
                }

                Section("Sync & Status") {
                    NavigationLink {
                        SyncStatusView()
                    } label: {
                        Label("Sync Status", systemImage: "arrow.left.arrow.right")
                    }
                    NavigationLink {
                        DashboardView()
                    } label: {
                        Label("Server Dashboard", systemImage: "gauge.medium")
                    }
                }

                if !appState.profiles.isEmpty {
                    Section("Output Profile") {
                        Picker("Profile", selection: Binding(
                            get: { appState.activeProfile },
                            set: { appState.switchProfile($0) }
                        )) {
                            ForEach(Array(appState.profiles.keys.sorted()), id: \.self) { name in
                                Text(name).tag(name)
                            }
                        }
                        if let profile = appState.profiles[appState.activeProfile] {
                            LabeledContent("Description", value: profile.description)
                            if !profile.usbDir.isEmpty {
                                LabeledContent("USB Directory", value: profile.usbDir)
                            }
                        }
                    }
                }

                offlineCacheSection

                Section("About") {
                    LabeledContent("App Version", value: MusicPorterApp.appVersion)
                    NavigationLink {
                        AboutView()
                    } label: {
                        Label("Release Notes", systemImage: "doc.text")
                    }
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Settings")
            .task {
                await loadSettings()
                await loadCacheSize()
            }
            .confirmationDialog("Clear All Cache?", isPresented: $showClearCacheConfirmation) {
                Button("Clear Cache", role: .destructive) {
                    Task { await clearAllCache() }
                }
            } message: {
                Text("This will delete all cached audio files and metadata. Downloaded files in your library are not affected.")
            }
        }
    }

    // MARK: - Offline Cache Section

    @ViewBuilder
    private var offlineCacheSection: some View {
        Section("Offline Cache") {
            // Cache size display
            cacheSizeDisplay

            // Max cache size picker
            Picker("Max Cache Size", selection: Binding(
                get: { appState.cachePreferences.maxCacheBytes },
                set: { newValue in
                    appState.cachePreferences.maxCacheBytes = newValue
                    if newValue > 0 {
                        Task { await enforceCacheLimit(newValue) }
                    }
                }
            )) {
                ForEach(Self.cacheSizeOptions, id: \.bytes) { option in
                    Text(option.label).tag(option.bytes)
                }
            }

            // Auto-pin toggle
            Toggle("Auto-Pin New Playlists", isOn: Binding(
                get: { appState.cachePreferences.autoPinNewPlaylists },
                set: { enabled in
                    if enabled {
                        // Add current unpinned playlists to exclusion before enabling
                        Task {
                            if let playlists = try? await appState.apiClient.getPlaylists() {
                                appState.cachePreferences.excludeUnpinnedPlaylists(playlists.map(\.key))
                            }
                            appState.cachePreferences.setAutoPinNewPlaylists(true)
                        }
                    } else {
                        appState.cachePreferences.setAutoPinNewPlaylists(false)
                    }
                }
            ))

            // Prefetch status and button
            prefetchControls

            // Clear cache
            Button("Clear All Cache", role: .destructive) {
                showClearCacheConfirmation = true
            }
            .disabled(cacheSize == 0)
        }
    }

    @ViewBuilder
    private var cacheSizeDisplay: some View {
        let maxBytes = appState.cachePreferences.maxCacheBytes
        if maxBytes > 0 {
            LabeledContent("Cache Size", value: "\(CacheUtils.formatBytes(cacheSize)) / \(CacheUtils.formatBytes(maxBytes))")
        } else {
            LabeledContent("Cache Size", value: CacheUtils.formatBytes(cacheSize))
        }
    }

    @ViewBuilder
    private var prefetchControls: some View {
        if let service = appState.backgroundPrefetchService {
            if service.isRunning {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Prefetching...")
                            .font(.subheadline)
                        Spacer()
                        if let playlist = service.currentPlaylist {
                            Text(playlist)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    if service.progressTotal > 0 {
                        ProgressView(
                            value: Double(service.progressCurrent),
                            total: Double(service.progressTotal))
                            .tint(.blue)
                    } else {
                        ProgressView()
                    }
                }
            } else {
                Button {
                    service.runOnce()
                } label: {
                    Label("Prefetch Now", systemImage: "arrow.down.circle")
                }
                .disabled(appState.cachePreferences.pinnedPlaylists.isEmpty)
            }

            if let lastRun = service.lastRunAt {
                HStack {
                    Text("Last prefetch: \(lastRun.formatted(.relative(presentation: .named)))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let result = service.lastResult {
                        Spacer()
                        Text("\(result.downloaded)↓ \(result.skipped)✓ \(result.failed)✗")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    @ViewBuilder
    private var connectionIcon: some View {
        if appState.apiClient.connectionType == .external {
            Image(systemName: "globe")
                .foregroundStyle(.blue)
        } else {
            Image(systemName: "house")
                .foregroundStyle(.green)
        }
    }

    @ViewBuilder
    private var connectionLabel: some View {
        if let type = appState.apiClient.connectionType {
            Text(type == .local ? "Connected via Local Network" : "Connected via External URL")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func loadSettings() async {
        // Profiles are fetched by AppState on connect; refresh if empty
        if appState.profiles.isEmpty {
            if let settings = try? await appState.apiClient.getSettings() {
                appState.profiles = settings.profiles
            }
        }
    }

    private func loadCacheSize() async {
        if let cacheManager = appState.audioCacheManager {
            cacheSize = await cacheManager.getTotalSize()
        }
    }

    private func enforceCacheLimit(_ maxBytes: Int64) async {
        guard let cacheManager = appState.audioCacheManager else { return }
        let pinnedKeys = Set(appState.cachePreferences.pinnedPlaylists)
        _ = await cacheManager.evictToLimit(
            maxBytes: maxBytes,
            pinnedPlaylists: pinnedKeys.isEmpty ? nil : pinnedKeys)
        cacheSize = await cacheManager.getTotalSize()
    }

    private func clearAllCache() async {
        if let cacheManager = appState.audioCacheManager {
            await cacheManager.clearAll()
        }
        if let metadataCache = appState.metadataCache {
            await metadataCache.clearAll()
        }
        cacheSize = 0
    }
}
