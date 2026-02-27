import Foundation
import UIKit
import UniformTypeIdentifiers

/// Where a file will be sourced from during USB export.
enum ExportSource {
    case local(URL)
    case server(playlist: String, filename: String)
}

/// A single file entry in an export manifest with its source.
struct ExportManifestEntry {
    let playlist: String
    let filename: String
    let source: ExportSource
}

/// A group of files belonging to a single playlist for USB export.
struct PlaylistExportGroup {
    let playlist: String
    let entries: [ExportManifestEntry]
}

/// Handles exporting downloaded MP3 files to a user-selected folder (USB drive, external storage, etc.).
/// Creates playlist subdirectories matching the server's sync directory structure.
/// Supports both local files and server-side streaming with optional device caching.
@Observable
final class USBExportService {
    var isExporting = false
    var exportProgress: Double = 0
    var currentFileName: String?
    var currentFileSource: ExportSource?
    var lastExportResult: ExportResult?

    @ObservationIgnored private var apiClient: APIClient?
    @ObservationIgnored private var downloadManager: FileDownloadManager?

    /// Whether to also save server-fetched files to the device during USB export.
    var cacheToDevice: Bool {
        get { UserDefaults.standard.bool(forKey: "exportCacheToDevice") }
        set { UserDefaults.standard.set(newValue, forKey: "exportCacheToDevice") }
    }

    /// Configure with API client and download manager for server-side fetching.
    func configure(apiClient: APIClient, downloadManager: FileDownloadManager) {
        self.apiClient = apiClient
        self.downloadManager = downloadManager
    }

    /// Copy files grouped by playlist to a destination directory, creating subdirectories per playlist.
    /// Directory structure: `destDir/<playlist>/<filename>.mp3`
    @MainActor
    func exportFiles(groups: [PlaylistExportGroup], to destDir: URL, cacheToDevice: Bool = false, profile: String? = nil) async -> ExportResult {
        isExporting = true
        exportProgress = 0
        currentFileName = nil
        currentFileSource = nil
        lastExportResult = nil

        // Request extended background execution time for file copy operations
        var backgroundTaskID = UIBackgroundTaskIdentifier.invalid
        backgroundTaskID = UIApplication.shared.beginBackgroundTask(withName: "USB Export") {
            // Expiration handler — log that time expired; in-flight copy stops when suspended
            print("USB Export background task expired")
            if backgroundTaskID != .invalid {
                UIApplication.shared.endBackgroundTask(backgroundTaskID)
                backgroundTaskID = .invalid
            }
        }

        defer {
            if backgroundTaskID != .invalid {
                UIApplication.shared.endBackgroundTask(backgroundTaskID)
            }
        }

        let result = await copyGroupedFiles(groups, to: destDir, cacheToDevice: cacheToDevice, profile: profile)
        isExporting = false
        currentFileSource = nil
        lastExportResult = result
        return result
    }

    /// Legacy flat export for backward compatibility (single playlist or ungrouped files).
    /// Wraps URLs as local ExportManifestEntries.
    @MainActor
    func exportFiles(urls: [URL], to destDir: URL) async -> ExportResult {
        let entries = urls.map { url in
            ExportManifestEntry(
                playlist: "",
                filename: url.lastPathComponent,
                source: .local(url))
        }
        let group = PlaylistExportGroup(playlist: "", entries: entries)
        return await exportFiles(groups: [group], to: destDir)
    }

    @MainActor
    func reset() {
        lastExportResult = nil
        currentFileName = nil
        currentFileSource = nil
    }

    private func copyGroupedFiles(
        _ groups: [PlaylistExportGroup], to destDir: URL, cacheToDevice: Bool, profile: String? = nil
    ) async -> ExportResult {
        let accessing = destDir.startAccessingSecurityScopedResource()
        defer { if accessing { destDir.stopAccessingSecurityScopedResource() } }

        let total = groups.reduce(0) { $0 + $1.entries.count }
        var localCopied = 0
        var serverFetched = 0
        var failed = 0
        var processed = 0

        for group in groups {
            let playlistDir = destDir.appendingPathComponent(group.playlist)

            // Create playlist subdirectory
            do {
                try FileManager.default.createDirectory(at: playlistDir, withIntermediateDirectories: true)
            } catch {
                // If directory creation fails, count all files in this group as failed
                failed += group.entries.count
                processed += group.entries.count
                let currentProcessed = processed
                await MainActor.run {
                    self.exportProgress = Double(currentProcessed) / Double(total)
                }
                continue
            }

            for entry in group.entries {
                if Task.isCancelled { break }

                let currentProcessed = processed
                await MainActor.run {
                    self.currentFileName = "\(group.playlist)/\(entry.filename)"
                    self.currentFileSource = entry.source
                    self.exportProgress = Double(currentProcessed) / Double(total)
                }

                let dest = playlistDir.appendingPathComponent(entry.filename)

                switch entry.source {
                case .local(let sourceURL):
                    do {
                        if FileManager.default.fileExists(atPath: dest.path) {
                            try FileManager.default.removeItem(at: dest)
                        }
                        try FileManager.default.copyItem(at: sourceURL, to: dest)
                        localCopied += 1
                    } catch {
                        failed += 1
                    }

                case .server(let playlist, let filename):
                    do {
                        // Resolve URL and build request on MainActor (APIClient is @MainActor)
                        let request: URLRequest? = await MainActor.run {
                            guard let apiClient,
                                  let url = apiClient.fileDownloadURL(playlist: playlist, filename: filename, profile: profile) else {
                                return nil
                            }
                            return apiClient.authenticatedRequest(for: url)
                        }

                        guard let request else {
                            failed += 1
                            processed += 1
                            continue
                        }

                        let (tempURL, response) = try await URLSession.shared.download(for: request)

                        // Validate HTTP response
                        if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                            try? FileManager.default.removeItem(at: tempURL)
                            failed += 1
                            processed += 1
                            continue
                        }

                        // Copy temp file to USB destination
                        if FileManager.default.fileExists(atPath: dest.path) {
                            try FileManager.default.removeItem(at: dest)
                        }
                        try FileManager.default.copyItem(at: tempURL, to: dest)

                        // Optionally cache to device
                        if cacheToDevice, let downloadManager {
                            let cacheDir = await MainActor.run {
                                downloadManager.getPlaylistDirectory(playlist: playlist)
                            }
                            try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
                            let cacheFile = cacheDir.appendingPathComponent(filename)
                            if FileManager.default.fileExists(atPath: cacheFile.path) {
                                try? FileManager.default.removeItem(at: cacheFile)
                            }
                            try? FileManager.default.copyItem(at: tempURL, to: cacheFile)
                        }

                        // Clean up temp file
                        try? FileManager.default.removeItem(at: tempURL)

                        serverFetched += 1
                    } catch is CancellationError {
                        break
                    } catch {
                        failed += 1
                    }
                }

                processed += 1
            }

            if Task.isCancelled { break }
        }

        await MainActor.run {
            self.exportProgress = 1.0
            self.currentFileName = nil
            self.currentFileSource = nil
        }

        let totalCopied = localCopied + serverFetched
        let message: String
        if failed == 0 {
            if serverFetched == 0 {
                message = "Exported \(totalCopied) files across \(groups.count) playlists"
            } else {
                message = "Exported \(totalCopied) files (\(localCopied) local, \(serverFetched) from server)"
            }
        } else {
            message = "Exported \(totalCopied) files (\(localCopied) local, \(serverFetched) from server), \(failed) failed"
        }

        return ExportResult(
            success: failed == 0,
            filesCopied: totalCopied,
            totalFiles: total,
            localCopied: localCopied,
            serverFetched: serverFetched,
            failed: failed,
            message: message
        )
    }
}

struct ExportResult {
    let success: Bool
    let filesCopied: Int
    let totalFiles: Int
    let localCopied: Int
    let serverFetched: Int
    let failed: Int
    let message: String
}
