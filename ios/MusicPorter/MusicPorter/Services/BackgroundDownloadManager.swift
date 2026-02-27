import Foundation

/// Metadata for an in-flight background download task.
struct DownloadTaskInfo {
    let playlist: String
    let filename: String
    let destDir: URL
}

/// Owns the background URLSession and implements URLSessionDownloadDelegate.
/// Separate from FileDownloadManager to avoid @MainActor conflicts with delegate callbacks.
final class BackgroundDownloadManager: NSObject, URLSessionDownloadDelegate {
    static let shared = BackgroundDownloadManager()

    /// Set by AppDelegate when the system wakes the app to handle completed background downloads.
    var backgroundCompletionHandler: (() -> Void)?

    /// Called when an individual file download completes or fails: (playlist, filename, error?).
    var onFileComplete: ((String, String, Error?) -> Void)?

    /// Called when all enqueued downloads in the session have finished.
    var onAllComplete: (() -> Void)?

    private let queue = DispatchQueue(label: "com.musicporter.background-download-manager")
    private var activeDownloads: [Int: DownloadTaskInfo] = [:]

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: "com.musicporter.background-downloads")
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    private override init() {
        super.init()
    }

    // MARK: - Public API

    /// Enqueue a download on the background session.
    func enqueue(request: URLRequest, playlist: String, filename: String, destDir: URL) {
        let task = session.downloadTask(with: request)
        let info = DownloadTaskInfo(playlist: playlist, filename: filename, destDir: destDir)
        queue.sync {
            activeDownloads[task.taskIdentifier] = info
        }
        task.resume()
    }

    /// Enqueue multiple downloads on the background session (used for foreground-to-background handoff).
    func enqueueRemaining(_ items: [(request: URLRequest, playlist: String, filename: String, destDir: URL)]) {
        for item in items {
            enqueue(request: item.request, playlist: item.playlist,
                    filename: item.filename, destDir: item.destDir)
        }
    }

    /// Cancel all pending and in-progress background downloads.
    func cancelAll() {
        session.getTasksWithCompletionHandler { _, _, downloadTasks in
            for task in downloadTasks {
                task.cancel()
            }
        }
        queue.sync {
            activeDownloads.removeAll()
        }
    }

    /// Number of in-flight download tasks.
    var pendingCount: Int {
        queue.sync { activeDownloads.count }
    }

    // MARK: - URLSessionDownloadDelegate

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        let info: DownloadTaskInfo? = queue.sync {
            activeDownloads.removeValue(forKey: downloadTask.taskIdentifier)
        }

        guard let info else { return }

        let destFile = info.destDir.appendingPathComponent(info.filename)

        do {
            try FileManager.default.createDirectory(at: info.destDir, withIntermediateDirectories: true)
            if FileManager.default.fileExists(atPath: destFile.path) {
                try FileManager.default.removeItem(at: destFile)
            }
            try FileManager.default.moveItem(at: location, to: destFile)
            onFileComplete?(info.playlist, info.filename, nil)
        } catch {
            onFileComplete?(info.playlist, info.filename, error)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let error else { return }

        // Only handle actual errors — successful completion is handled in didFinishDownloadingTo
        let info: DownloadTaskInfo? = queue.sync {
            activeDownloads.removeValue(forKey: task.taskIdentifier)
        }

        if let info {
            onFileComplete?(info.playlist, info.filename, error)
        }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        onAllComplete?()
        DispatchQueue.main.async { [weak self] in
            self?.backgroundCompletionHandler?()
            self?.backgroundCompletionHandler = nil
        }
    }
}
