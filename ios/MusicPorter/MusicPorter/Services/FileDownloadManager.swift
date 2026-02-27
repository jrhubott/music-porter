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

/// Manages downloading MP3 files from the server to the device.
/// Uses foreground URLSession for fast LAN downloads, with automatic
/// handoff to background URLSession when the app is backgrounded.
@MainActor @Observable
final class FileDownloadManager {
    var downloadProgress: DownloadProgress?
    var bulkProgress: BulkDownloadProgress?

    @ObservationIgnored private var apiClient: APIClient?
    @ObservationIgnored private let backgroundManager = BackgroundDownloadManager.shared
    @ObservationIgnored private var backgroundTaskID: UIBackgroundTaskIdentifier = .invalid

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
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
    func downloadFile(playlist: String, filename: String) async throws -> URL {
        guard let apiClient, let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename) else {
            throw FileDownloadError.notConfigured
        }

        let request = apiClient.authenticatedRequest(for: url)
        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)

        let (tempURL, _) = try await URLSession.shared.download(for: request)

        let destFile = destDir.appendingPathComponent(filename)
        if FileManager.default.fileExists(atPath: destFile.path) {
            try FileManager.default.removeItem(at: destFile)
        }
        try FileManager.default.moveItem(at: tempURL, to: destFile)

        return destFile
    }

    /// Download all files in a playlist, skipping files that already exist locally.
    /// Uses foreground URLSession for fast LAN downloads. If the app is backgrounded,
    /// remaining files are handed off to the background URLSession.
    func downloadAll(playlist: String) async throws {
        guard let apiClient else {
            throw FileDownloadError.notConfigured
        }

        let response = try await apiClient.getFiles(playlist: playlist)
        let tracks = response.files

        let existingFiles = Set(localFiles(playlist: playlist).map { $0.lastPathComponent })
        let toDownload = tracks.filter { !existingFiles.contains($0.filename) }

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
            // Expiration handler: hand off remaining files to background URLSession
            guard let self else { return }
            Task { @MainActor in
                self.handOffToBackground(playlist: playlist, destDir: destDir)
                self.endBackgroundTask()
            }
        }

        defer {
            endBackgroundTask()
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

        // Sequential foreground downloads — fast on LAN
        for track in toDownload {
            try Task.checkCancellation()

            guard let url = apiClient.fileDownloadURL(playlist: playlist, filename: track.filename) else {
                continue
            }
            let request = apiClient.authenticatedRequest(for: url)

            downloadProgress?.currentFile = track.filename

            do {
                let (tempURL, _) = try await URLSession.shared.download(for: request)

                let destFile = destDir.appendingPathComponent(track.filename)
                if FileManager.default.fileExists(atPath: destFile.path) {
                    try FileManager.default.removeItem(at: destFile)
                }
                try FileManager.default.moveItem(at: tempURL, to: destFile)

                DownloadStateStore.markFileComplete(playlist: playlist, filename: track.filename)
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                DownloadStateStore.markFileFailed(playlist: playlist, filename: track.filename)
                print("Download failed: \(track.filename) — \(error.localizedDescription)")
            }

            if var progress = downloadProgress {
                progress.completed += 1
                downloadProgress = progress
            }
        }

        downloadProgress = DownloadProgress(completed: total, total: total, currentFile: "")
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
