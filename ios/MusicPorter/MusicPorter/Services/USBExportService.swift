import Foundation
import UIKit
import UniformTypeIdentifiers

/// A group of files belonging to a single playlist for USB export.
struct PlaylistExportGroup {
    let playlist: String
    let urls: [URL]
}

/// Handles exporting downloaded MP3 files to a user-selected folder (USB drive, external storage, etc.).
/// Creates playlist subdirectories matching the server's sync directory structure.
@Observable
final class USBExportService {
    var isExporting = false
    var exportProgress: Double = 0
    var currentFileName: String?
    var lastExportResult: ExportResult?

    /// Copy files grouped by playlist to a destination directory, creating subdirectories per playlist.
    /// Directory structure: `destDir/<playlist>/<filename>.mp3`
    @MainActor
    func exportFiles(groups: [PlaylistExportGroup], to destDir: URL) async -> ExportResult {
        isExporting = true
        exportProgress = 0
        currentFileName = nil
        lastExportResult = nil

        let result = await copyGroupedFiles(groups, to: destDir)
        isExporting = false
        lastExportResult = result
        return result
    }

    /// Legacy flat export for backward compatibility (single playlist or ungrouped files).
    @MainActor
    func exportFiles(urls: [URL], to destDir: URL) async -> ExportResult {
        isExporting = true
        exportProgress = 0
        currentFileName = nil
        lastExportResult = nil

        let result = await copyFiles(urls, to: destDir)
        isExporting = false
        lastExportResult = result
        return result
    }

    @MainActor
    func reset() {
        lastExportResult = nil
        currentFileName = nil
    }

    private func copyGroupedFiles(_ groups: [PlaylistExportGroup], to destDir: URL) async -> ExportResult {
        let accessing = destDir.startAccessingSecurityScopedResource()
        defer { if accessing { destDir.stopAccessingSecurityScopedResource() } }

        let total = groups.reduce(0) { $0 + $1.urls.count }
        var copied = 0
        var failed = 0
        var processed = 0

        for group in groups {
            let playlistDir = destDir.appendingPathComponent(group.playlist)

            // Create playlist subdirectory
            do {
                try FileManager.default.createDirectory(at: playlistDir, withIntermediateDirectories: true)
            } catch {
                // If directory creation fails, count all files in this group as failed
                failed += group.urls.count
                processed += group.urls.count
                let currentProcessed = processed
                await MainActor.run {
                    self.exportProgress = Double(currentProcessed) / Double(total)
                }
                continue
            }

            for source in group.urls {
                let name = source.lastPathComponent
                let currentProcessed = processed
                await MainActor.run {
                    self.currentFileName = "\(group.playlist)/\(name)"
                    self.exportProgress = Double(currentProcessed) / Double(total)
                }

                let dest = playlistDir.appendingPathComponent(name)
                do {
                    if FileManager.default.fileExists(atPath: dest.path) {
                        try FileManager.default.removeItem(at: dest)
                    }
                    try FileManager.default.copyItem(at: source, to: dest)
                    copied += 1
                } catch {
                    failed += 1
                }
                processed += 1
            }
        }

        await MainActor.run {
            self.exportProgress = 1.0
            self.currentFileName = nil
        }

        return ExportResult(
            success: failed == 0,
            filesCopied: copied,
            totalFiles: total,
            message: failed == 0
                ? "Exported \(copied) files across \(groups.count) playlists"
                : "Exported \(copied) files, \(failed) failed"
        )
    }

    private func copyFiles(_ urls: [URL], to destDir: URL) async -> ExportResult {
        let accessing = destDir.startAccessingSecurityScopedResource()
        defer { if accessing { destDir.stopAccessingSecurityScopedResource() } }

        var copied = 0
        var failed = 0
        let total = urls.count

        for (index, source) in urls.enumerated() {
            let name = source.lastPathComponent
            await MainActor.run {
                self.currentFileName = name
                self.exportProgress = Double(index) / Double(total)
            }

            let dest = destDir.appendingPathComponent(name)
            do {
                if FileManager.default.fileExists(atPath: dest.path) {
                    try FileManager.default.removeItem(at: dest)
                }
                try FileManager.default.copyItem(at: source, to: dest)
                copied += 1
            } catch {
                failed += 1
            }
        }

        await MainActor.run {
            self.exportProgress = 1.0
            self.currentFileName = nil
        }

        return ExportResult(
            success: failed == 0,
            filesCopied: copied,
            totalFiles: total,
            message: failed == 0
                ? "Exported \(copied) files"
                : "Exported \(copied) files, \(failed) failed"
        )
    }
}

struct ExportResult {
    let success: Bool
    let filesCopied: Int
    let totalFiles: Int
    let message: String
}
