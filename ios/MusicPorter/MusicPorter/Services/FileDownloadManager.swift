import Foundation

/// Manages downloading MP3 files from the server to the device.
@Observable
final class FileDownloadManager: NSObject {
    var downloads: [String: DownloadState] = [:]  // keyed by filename
    var downloadedFiles: [URL] = []

    private var apiClient: APIClient?
    private lazy var downloadSession: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: "com.musicporter.downloads")
        config.isDiscretionary = false
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()
    private var completionHandlers: [String: (URL?, Error?) -> Void] = [:]

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

        // Use regular download (not background) for simplicity
        let (tempURL, _) = try await URLSession.shared.download(for: request)

        if FileManager.default.fileExists(atPath: destFile.path) {
            try FileManager.default.removeItem(at: destFile)
        }
        try FileManager.default.moveItem(at: tempURL, to: destFile)

        await MainActor.run {
            self.downloads[filename] = .completed(destFile)
        }
        return destFile
    }

    /// Download all files in a playlist as a ZIP.
    func downloadAll(playlist: String) async throws -> URL {
        guard let apiClient, let url = apiClient.downloadAllURL(playlist: playlist) else {
            throw FileDownloadError.notConfigured
        }

        let request = apiClient.authenticatedRequest(for: url)
        let destDir = getPlaylistDirectory(playlist: playlist)
        try FileManager.default.createDirectory(at: destDir, withIntermediateDirectories: true)
        let destFile = destDir.appendingPathComponent("\(playlist).zip")

        let (tempURL, _) = try await URLSession.shared.download(for: request)

        if FileManager.default.fileExists(atPath: destFile.path) {
            try FileManager.default.removeItem(at: destFile)
        }
        try FileManager.default.moveItem(at: tempURL, to: destFile)

        return destFile
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

extension FileDownloadManager: URLSessionDownloadDelegate {
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        // Background download completion handled here
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64,
                    totalBytesExpectedToWrite: Int64) {
        guard let url = downloadTask.originalRequest?.url else { return }
        let filename = url.lastPathComponent
        let progress = totalBytesExpectedToWrite > 0
            ? Double(totalBytesWritten) / Double(totalBytesExpectedToWrite) : 0
        Task { @MainActor in
            self.downloads[filename] = .downloading(progress)
        }
    }
}

enum DownloadState {
    case pending
    case downloading(Double)
    case completed(URL)
    case failed(Error)
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
