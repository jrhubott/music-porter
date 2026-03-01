import Foundation
import Observation
import UIKit

/// Progress state for a batch download operation.
struct DownloadProgress {
    var completed: Int
    var total: Int
    var currentFile: String

    var fraction: Double {
        total > 0 ? Double(completed) / Double(total) : 0
    }
}

/// Progress state for a multi-playlist download-all operation.
struct BulkDownloadProgress {
    var completedPlaylists: Int
    var totalPlaylists: Int
    var currentPlaylistName: String
}

/// Gates concurrent access to a fixed number of slots.
private actor ConcurrencyLimiter {
    private let limit: Int
    private var active = 0
    private var waiters: [CheckedContinuation<Void, Never>] = []

    init(limit: Int) { self.limit = limit }

    func acquire() async {
        if active < limit {
            active += 1
        } else {
            await withCheckedContinuation { continuation in
                waiters.append(continuation)
            }
        }
    }

    func release() {
        if let next = waiters.first {
            waiters.removeFirst()
            next.resume()
        } else {
            active -= 1
        }
    }
}

/// Manages downloading MP3 files from the server to the device.
/// Uses foreground URLSession for fast LAN downloads, with automatic
/// handoff to background URLSession when the app is backgrounded.
@MainActor @Observable
final class FileDownloadManager {
    var downloadProgress: DownloadProgress?
    var bulkProgress: BulkDownloadProgress?

    @ObservationIgnored private var apiClient: APIClient?
    @ObservationIgnored private var audioCacheManager: AudioCacheManager?
    @ObservationIgnored private let backgroundManager = BackgroundDownloadManager.shared
    @ObservationIgnored private var backgroundTaskID: UIBackgroundTaskIdentifier = .invalid

    /// Dedicated URLSession with tuned timeouts and connection limits for LAN downloads.
    @ObservationIgnored private let downloadSession: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        config.httpMaximumConnectionsPerHost = 6
        return URLSession(configuration: config)
    }()

    func configure(apiClient: APIClient, audioCacheManager: AudioCacheManager? = nil) {
        self.apiClient = apiClient
        self.audioCacheManager = audioCacheManager
        wireBackgroundCallbacks()
    }

    /// Wire up background download delegate callbacks to update UI state.
    /// Only fires when the app was backgrounded and the background session completed downloads.
    private func wireBackgroundCallbacks() {
        backgroundManager.onFileComplete = { [weak self] playlist, filename, error in
            if let error {
                DownloadStateStore.markFileFailed(playlist: playlist, filename: filename)
                print("Background download failed: \(playlist)/\(filename) — \(error.localizedDescription)")
            } else {
                DownloadStateStore.markFileComplete(playlist: playlist, filename: filename)
            }

            // Update progress on the main actor
            DispatchQueue.main.async { [weak self] in
                guard let self, var progress = self.downloadProgress else { return }
                progress.completed += 1
                progress.currentFile = filename
                self.downloadProgress = progress

                if progress.completed >= progress.total {
                    DownloadStateStore.clear()
                    self.downloadProgress = nil
                }
            }
        }

        backgroundManager.onAllComplete = {
            DispatchQueue.main.async {
                DownloadStateStore.clear()
            }
        }
    }

    /// Download a single MP3 file using the foreground session (fast, immediate).
    /// When a track is provided, checks the cache first and writes through on download.
    func downloadFile(playlist: String, filename: String, track: Track? = nil) async throws -> URL {
        guard let apiClient, let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename) else {
            throw FileDownloadError.notConfigured
        }

        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
        let destFile = destDir.appendingPathComponent(filename)

        // Cache hit: copy from cache instead of downloading
        if let track, let uuid = track.uuid, let cacheManager = audioCacheManager {
            let copied = await cacheManager.copyToDestination(uuid, destPath: destFile)
            if copied { return destFile }
        }

        let request = apiClient.authenticatedRequest(for: url)
        let (tempURL, _) = try await downloadSession.download(for: request)

        if FileManager.default.fileExists(atPath: destFile.path) {
            try FileManager.default.removeItem(at: destFile)
        }
        try FileManager.default.moveItem(at: tempURL, to: destFile)

        // Write-through: store in cache for offline access
        if let track, let cacheManager = audioCacheManager {
            await cacheManager.storeFromFile(
                destFile, file: track, playlistKey: playlist,
                serverCreatedAt: track.createdAt, serverUpdatedAt: track.updatedAt)
        }

        return destFile
    }

    /// Download all files in a playlist, skipping files that already exist locally.
    /// Uses foreground URLSession with concurrent downloads for fast LAN throughput.
    /// If the app is backgrounded, remaining files are handed off to the background URLSession.
    func downloadAll(playlist: String) async throws {
        guard let apiClient else {
            throw FileDownloadError.notConfigured
        }

        let response = try await apiClient.getFiles(playlist: playlist)
        let tracks = response.files

        let existingFiles = Set(localFiles(playlist: playlist).map { $0.lastPathComponent })
        var toDownload: [Track] = []

        // Filter: skip local files, copy from cache if available
        for track in tracks {
            if existingFiles.contains(track.filename) { continue }
            if let uuid = track.uuid, let cacheManager = audioCacheManager {
                let destDir = getPlaylistDirectory(playlist: playlist)
                try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
                let destFile = destDir.appendingPathComponent(track.filename)
                let copied = await cacheManager.copyToDestination(uuid, destPath: destFile)
                if copied { continue }
            }
            toDownload.append(track)
        }

        let total = toDownload.count
        guard total > 0 else { return }

        let filenames = toDownload.map(\.filename)

        downloadProgress = DownloadProgress(completed: 0, total: total, currentFile: "")

        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)

        // Persist download state for recovery and background handoff
        let pendingState = PendingDownloadState(
            playlist: playlist,
            totalFiles: total,
            completedFiles: [],
            failedFiles: [],
            allFiles: filenames
        )
        var allStates = DownloadStateStore.load()
        allStates.removeAll { $0.playlist == playlist }
        allStates.append(pendingState)
        DownloadStateStore.save(allStates)

        // Begin a UIKit background task so we get ~30s of execution if the app backgrounds
        backgroundTaskID = UIApplication.shared.beginBackgroundTask { [weak self] in
            // Expiration handler: flush state and hand off remaining files to background URLSession
            guard let self else { return }
            Task { @MainActor in
                DownloadStateStore.flushIfDirty()
                self.handOffToBackground(playlist: playlist, destDir: destDir)
                self.endBackgroundTask()
            }
        }

        defer {
            endBackgroundTask()
            // Flush any remaining cached state
            DownloadStateStore.flushIfDirty()
            // If all files completed, clear state
            let remaining = DownloadStateStore.remainingFiles(playlist: playlist)
            if remaining.isEmpty {
                var states = DownloadStateStore.load()
                states.removeAll { $0.playlist == playlist }
                if states.isEmpty {
                    DownloadStateStore.clear()
                } else {
                    DownloadStateStore.save(states)
                }
            }
        }

        // Prepare all authenticated requests on @MainActor before entering TaskGroup
        var downloadItems: [(filename: String, request: URLRequest, track: Track)] = []
        for track in toDownload {
            guard let url = apiClient.fileDownloadURL(playlist: playlist, filename: track.filename) else {
                continue
            }
            let request = apiClient.authenticatedRequest(for: url)
            downloadItems.append((filename: track.filename, request: request, track: track))
        }

        // Concurrent foreground downloads — fast on LAN
        let limiter = ConcurrencyLimiter(limit: 6)
        let session = downloadSession
        let cacheManager = audioCacheManager

        try await withThrowingTaskGroup(of: Void.self) { group in
            for item in downloadItems {
                group.addTask { [weak self] in
                    await limiter.acquire()
                    defer { Task { await limiter.release() } }

                    try Task.checkCancellation()

                    do {
                        let (tempURL, _) = try await session.download(for: item.request)

                        let destFile = destDir.appendingPathComponent(item.filename)
                        if FileManager.default.fileExists(atPath: destFile.path) {
                            try FileManager.default.removeItem(at: destFile)
                        }
                        try FileManager.default.moveItem(at: tempURL, to: destFile)

                        // Write-through: store in cache for offline access
                        if let cacheManager {
                            await cacheManager.storeFromFile(
                                destFile, file: item.track, playlistKey: playlist,
                                serverCreatedAt: item.track.createdAt,
                                serverUpdatedAt: item.track.updatedAt)
                        }

                        await self?.fileCompleted(
                            playlist: playlist, filename: item.filename, failed: false)
                    } catch is CancellationError {
                        throw CancellationError()
                    } catch {
                        await self?.fileCompleted(
                            playlist: playlist, filename: item.filename, failed: true)
                        print("Download failed: \(item.filename) — \(error.localizedDescription)")
                    }
                }
            }
            try await group.waitForAll()
        }

        downloadProgress = DownloadProgress(completed: total, total: total, currentFile: "")
    }

    /// Update state store and UI progress after a single file completes.
    /// Serializes concurrent progress updates on the main actor.
    private func fileCompleted(playlist: String, filename: String, failed: Bool) {
        if failed {
            DownloadStateStore.markFileFailed(playlist: playlist, filename: filename)
        } else {
            DownloadStateStore.markFileComplete(playlist: playlist, filename: filename)
        }

        if var progress = downloadProgress {
            progress.completed += 1
            progress.currentFile = filename
            downloadProgress = progress
        }
    }

    /// Hand off remaining unfinished downloads to the background URLSession.
    /// Called from the `beginBackgroundTask` expiration handler when the app is about to suspend.
    private func handOffToBackground(playlist: String, destDir: URL) {
        guard let apiClient else { return }

        let remaining = DownloadStateStore.remainingFiles(playlist: playlist)
        guard !remaining.isEmpty else { return }

        var items: [(request: URLRequest, playlist: String, filename: String, destDir: URL)] = []
        for filename in remaining {
            guard let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename) else {
                continue
            }
            let request = apiClient.authenticatedRequest(for: url)
            items.append((request: request, playlist: playlist, filename: filename, destDir: destDir))
        }

        backgroundManager.enqueueRemaining(items)
        print("Handed off \(items.count) remaining downloads to background session")
    }

    private func endBackgroundTask() {
        guard backgroundTaskID != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTaskID)
        backgroundTaskID = .invalid
    }

    /// Download all playlists sequentially.
    /// Respects cooperative cancellation between playlists.
    func downloadAllPlaylists(dirs: [ExportDirectory]) async throws {
        let total = dirs.count
        guard total > 0 else { return }

        for (index, dir) in dirs.enumerated() {
            try Task.checkCancellation()

            bulkProgress = BulkDownloadProgress(
                completedPlaylists: index,
                totalPlaylists: total,
                currentPlaylistName: dir.displayName
            )

            try await downloadAll(playlist: dir.name)
        }

        bulkProgress = BulkDownloadProgress(
            completedPlaylists: total,
            totalPlaylists: total,
            currentPlaylistName: ""
        )
    }

    /// Reconcile background download state when the app returns to foreground.
    /// Checks what's on disk vs what was pending and updates progress accordingly.
    func reconcileBackgroundDownloads() {
        let states = DownloadStateStore.load()
        guard !states.isEmpty else { return }

        var allDone = true

        for state in states {
            // Count actual files on disk for this playlist
            let filesOnDisk = localFiles(playlist: state.playlist).count
            let remaining = DownloadStateStore.remainingFiles(playlist: state.playlist)

            if remaining.isEmpty {
                continue
            }

            allDone = false

            // Update progress to reflect actual on-disk state
            downloadProgress = DownloadProgress(
                completed: filesOnDisk,
                total: state.totalFiles,
                currentFile: ""
            )
        }

        if allDone {
            DownloadStateStore.clear()
            downloadProgress = nil
        }
    }

    /// Returns the playlist name if there's an incomplete download that should be resumed.
    /// Checks persisted download state for any playlist with remaining (undownloaded) files.
    func stalledDownloadPlaylist() -> String? {
        let states = DownloadStateStore.load()
        for state in states {
            if !DownloadStateStore.remainingFiles(playlist: state.playlist).isEmpty {
                return state.playlist
            }
        }
        return nil
    }

    /// Clear download progress (call after download completes).
    func clearProgress() {
        downloadProgress = nil
        bulkProgress = nil
    }

    /// Cancel all in-progress downloads — background session tasks and state cleanup.
    /// The foreground Task is cancelled by the caller (LibraryView.cancelDownload).
    func cancelDownloads() {
        backgroundManager.cancelAll()
        DownloadStateStore.clear()
        endBackgroundTask()
    }

    /// Get the local directory for a playlist's downloads.
    func getPlaylistDirectory(playlist: String) -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent("MusicPorter/\(playlist)")
    }

    /// List locally downloaded MP3 files for a playlist.
    func localFiles(playlist: String) -> [URL] {
        let dir = getPlaylistDirectory(playlist: playlist)
        guard let contents = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: [.fileSizeKey],
            options: .skipsHiddenFiles) else { return [] }
        return contents.filter { $0.pathExtension.lowercased() == "mp3" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// Delete all local files for a playlist.
    func deletePlaylist(playlist: String) throws {
        let dir = getPlaylistDirectory(playlist: playlist)
        if FileManager.default.fileExists(atPath: dir.path) {
            try FileManager.default.removeItem(at: dir)
        }
    }

    /// Total size of locally downloaded files.
    func localStorageUsed() -> Int {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let base = docs.appendingPathComponent("MusicPorter")
        guard let enumerator = FileManager.default.enumerator(
            at: base, includingPropertiesForKeys: [.fileSizeKey],
            options: .skipsHiddenFiles) else { return 0 }
        var total = 0
        for case let url as URL in enumerator {
            if let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize {
                total += size
            }
        }
        return total
    }
}

enum FileDownloadError: LocalizedError {
    case notConfigured
    case fileNotFound

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "Download manager not configured"
        case .fileNotFound: return "File not found"
        }
    }
}
