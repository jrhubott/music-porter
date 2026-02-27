import Foundation
import Observation

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
@MainActor @Observable
final class FileDownloadManager {
    var downloadProgress: DownloadProgress?
    var bulkProgress: BulkDownloadProgress?

    @ObservationIgnored private var apiClient: APIClient?
    @ObservationIgnored private let backgroundManager = BackgroundDownloadManager.shared

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
        wireBackgroundCallbacks()
    }

    /// Wire up background download delegate callbacks to update UI state.
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

                // Check if batch is complete
                if progress.completed >= progress.total {
                    DownloadStateStore.clear()
                }
            }
        }

        backgroundManager.onAllComplete = {
            DispatchQueue.main.async {
                DownloadStateStore.clear()
            }
        }
    }

    /// Download a single MP3 file using the background session.
    func downloadFile(playlist: String, filename: String) async throws -> URL {
        guard let apiClient, let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename) else {
            throw FileDownloadError.notConfigured
        }

        let request = apiClient.authenticatedRequest(for: url)
        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)

        return try await withCheckedThrowingContinuation { continuation in
            let previousHandler = backgroundManager.onFileComplete

            backgroundManager.onFileComplete = { [weak self] completedPlaylist, completedFilename, error in
                // Call through to the previous handler for state store updates
                previousHandler?(completedPlaylist, completedFilename, error)

                // Only handle our specific file
                guard completedPlaylist == playlist && completedFilename == filename else { return }

                // Restore previous handler
                DispatchQueue.main.async {
                    self?.backgroundManager.onFileComplete = previousHandler
                }

                if let error {
                    continuation.resume(throwing: error)
                } else {
                    let destFile = destDir.appendingPathComponent(filename)
                    continuation.resume(returning: destFile)
                }
            }

            backgroundManager.enqueue(
                request: request, playlist: playlist,
                filename: filename, destDir: destDir)
        }
    }

    /// Download all files in a playlist, skipping files that already exist locally.
    /// Uses background URLSession so downloads continue when the app is backgrounded.
    func downloadAll(playlist: String) async throws {
        guard let apiClient else {
            throw FileDownloadError.notConfigured
        }

        let response = try await apiClient.getFiles(playlist: playlist)
        let tracks = response.files

        // Determine which files already exist locally
        let existingFiles = Set(localFiles(playlist: playlist).map { $0.lastPathComponent })
        let toDownload = tracks.filter { !existingFiles.contains($0.filename) }

        let total = toDownload.count
        guard total > 0 else { return }

        downloadProgress = DownloadProgress(completed: 0, total: total, currentFile: "")

        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)

        // Persist download state for recovery after app termination
        let pendingState = PendingDownloadState(
            playlist: playlist,
            totalFiles: total,
            completedFiles: [],
            failedFiles: []
        )
        var allStates = DownloadStateStore.load()
        allStates.removeAll { $0.playlist == playlist }
        allStates.append(pendingState)
        DownloadStateStore.save(allStates)

        // Enqueue all downloads on the background session
        for track in toDownload {
            try Task.checkCancellation()
            guard let url = apiClient.fileDownloadURL(playlist: playlist, filename: track.filename) else {
                continue
            }
            let request = apiClient.authenticatedRequest(for: url)
            backgroundManager.enqueue(
                request: request, playlist: playlist,
                filename: track.filename, destDir: destDir)
        }

        // Wait for all downloads to complete by polling state store
        // The background delegate callbacks update progress and state store
        try await waitForDownloads(playlist: playlist, total: total)
    }

    /// Wait for all background downloads to finish for a playlist.
    private func waitForDownloads(playlist: String, total: Int) async throws {
        while true {
            try Task.checkCancellation()
            try await Task.sleep(for: .milliseconds(500))

            let states = DownloadStateStore.load()
            guard let state = states.first(where: { $0.playlist == playlist }) else {
                // State was cleared — downloads are complete
                break
            }

            let done = state.completedFiles.count + state.failedFiles.count
            if done >= total {
                break
            }
        }

        downloadProgress = DownloadProgress(completed: total, total: total, currentFile: "")
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

        for state in states {
            let completed = state.completedFiles.count
            let failed = state.failedFiles.count
            let done = completed + failed

            if done >= state.totalFiles {
                // All done — clear this playlist's state
                continue
            }

            // Update progress to reflect actual state
            downloadProgress = DownloadProgress(
                completed: done,
                total: state.totalFiles,
                currentFile: ""
            )
        }

        // If all states are complete, clear everything
        let allDone = states.allSatisfy { state in
            (state.completedFiles.count + state.failedFiles.count) >= state.totalFiles
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

    /// Cancel all in-progress background downloads.
    func cancelDownloads() {
        backgroundManager.cancelAll()
        DownloadStateStore.clear()
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
