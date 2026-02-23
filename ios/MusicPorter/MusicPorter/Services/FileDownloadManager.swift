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

/// Manages downloading MP3 files from the server to the device.
@MainActor @Observable
final class FileDownloadManager {
    var downloadProgress: DownloadProgress?

    @ObservationIgnored private var apiClient: APIClient?

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// Download a single MP3 file.
    func downloadFile(playlist: String, filename: String) async throws -> URL {
        guard let apiClient, let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename) else {
            throw FileDownloadError.notConfigured
        }

        let request = apiClient.authenticatedRequest(for: url)
        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
        let destFile = destDir.appendingPathComponent(filename)

        let (tempURL, _) = try await URLSession.shared.download(for: request)

        if FileManager.default.fileExists(atPath: destFile.path) {
            try FileManager.default.removeItem(at: destFile)
        }
        try FileManager.default.moveItem(at: tempURL, to: destFile)

        return destFile
    }

    /// Download all files in a playlist individually, skipping files that already exist locally.
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

        for (index, track) in toDownload.enumerated() {
            downloadProgress = DownloadProgress(
                completed: index, total: total, currentFile: track.filename)

            guard let url = apiClient.fileDownloadURL(playlist: playlist, filename: track.filename) else {
                continue
            }

            let request = apiClient.authenticatedRequest(for: url)

            do {
                let (tempURL, response) = try await URLSession.shared.download(for: request)

                // Check for successful HTTP status
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                    continue
                }

                let destFile = destDir.appendingPathComponent(track.filename)
                if FileManager.default.fileExists(atPath: destFile.path) {
                    try FileManager.default.removeItem(at: destFile)
                }
                try FileManager.default.moveItem(at: tempURL, to: destFile)
            } catch {
                // Skip failed files and continue with the rest
                continue
            }
        }

        downloadProgress = DownloadProgress(completed: total, total: total, currentFile: "")
    }

    /// Clear download progress (call after download completes).
    func clearProgress() {
        downloadProgress = nil
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
