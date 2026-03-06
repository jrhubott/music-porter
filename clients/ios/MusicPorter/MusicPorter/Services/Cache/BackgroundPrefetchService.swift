import Foundation
import os

/// Periodically prefetches pinned playlists into the local cache.
@MainActor @Observable
final class BackgroundPrefetchService {
    // MARK: - Observable State

    private(set) var isRunning = false
    private(set) var currentPlaylist: String?
    private(set) var progressCurrent = 0
    private(set) var progressTotal = 0
    private(set) var lastRunAt: Date?
    private(set) var lastResult: PrefetchResult?

    // MARK: - Private State

    private weak var appState: AppState?
    @ObservationIgnored private var timer: Timer?
    @ObservationIgnored private var prefetchTask: Task<Void, Never>?
    @ObservationIgnored private let logger = Logger(subsystem: "com.musicporter", category: "BackgroundPrefetch")

    /// Initial delay before first prefetch after connect (seconds).
    private static let initialDelaySeconds: TimeInterval = 2

    // MARK: - Init

    init(appState: AppState) {
        self.appState = appState
    }

    // MARK: - Lifecycle

    func start() {
        stop()
        timer = Timer.scheduledTimer(
            withTimeInterval: CacheConstants.backgroundPrefetchIntervalSeconds,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.runOnce()
            }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        prefetchTask?.cancel()
        prefetchTask = nil
        isRunning = false
    }

    /// Trigger an immediate prefetch after connecting.
    func notifyConnected() {
        Task {
            try? await Task.sleep(for: .seconds(Self.initialDelaySeconds))
            guard !Task.isCancelled else { return }
            runNow()
        }
    }

    /// Cancel any running prefetch and start a new one immediately.
    /// Use this for user-initiated actions (pin/unpin, app startup).
    func runNow() {
        if isRunning {
            logger.info("Interrupting running prefetch for restart")
            prefetchTask?.cancel()
            prefetchTask = nil
            isRunning = false
        }
        startPrefetch()
    }

    /// Run a single prefetch cycle. Skips if one is already running.
    /// Used by the periodic timer — never interrupts a running prefetch.
    func runOnce() {
        guard !isRunning else { return }
        startPrefetch()
    }

    // MARK: - Internal

    private func startPrefetch() {
        guard let appState, appState.isConnected else { return }
        guard let prefetchEngine = appState.prefetchEngine,
              let metadataCache = appState.metadataCache else { return }
        let profile = appState.activeProfile
        guard !profile.isEmpty else { return }

        let cachePrefs = appState.cachePreferences

        progressCurrent = 0
        progressTotal = 0
        currentPlaylist = nil

        prefetchTask = Task { [weak self] in
            guard let self else { return }

            // Auto-pin sync: get server playlist keys
            if cachePrefs.autoPinNewPlaylists, let playlists = try? await appState.apiClient.getPlaylists() {
                let serverKeys = playlists.map(\.key)
                let newPins = cachePrefs.syncPinsWithServer(serverKeys)
                if !newPins.isEmpty {
                    self.logger.info("Auto-pinned \(newPins.count) new playlists: \(newPins.joined(separator: ", "))")
                }
            }

            let pinnedPlaylists = cachePrefs.pinnedPlaylists
            guard !pinnedPlaylists.isEmpty else {
                return
            }

            let options = PrefetchOptions(
                playlists: pinnedPlaylists,
                profile: profile,
                maxCacheBytes: cachePrefs.maxCacheBytes,
                pinnedPlaylists: Set(pinnedPlaylists)
            )

            let result = await prefetchEngine.prefetch(
                options: options,
                metadataCache: metadataCache
            ) { [weak self] progress in
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    // Only show progress UI when there are files to download
                    if progress.total > progress.skipped {
                        self.isRunning = true
                    }
                    self.currentPlaylist = progress.playlist
                    self.progressCurrent = progress.processed
                    self.progressTotal = progress.total
                }
            }

            // If cancelled (by runNow()), don't reset state — the new task owns it
            guard !Task.isCancelled else { return }

            self.lastResult = result
            self.lastRunAt = Date()
            self.isRunning = false
            self.currentPlaylist = nil
            self.prefetchTask = nil

            self.logger.info("Prefetch complete: \(result.downloaded) downloaded, \(result.skipped) skipped, \(result.failed) failed (\(result.durationMs)ms)")
        }
    }
}
