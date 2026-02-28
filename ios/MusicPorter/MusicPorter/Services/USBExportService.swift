import Foundation
import UIKit
import UniformTypeIdentifiers

/// Handles exporting downloaded MP3 files to a user-selected folder (USB drive, external storage, etc.).
@Observable
final class USBExportService {
    var isExporting = false
    var exportProgress: Double = 0
    var currentFileName: String?
    var lastExportResult: ExportResult?

    /// Copy files to a destination directory selected via DocumentExportPicker.
    /// If `subdirectory` is provided, creates it under `destDir` and copies there.
    @MainActor
    func exportFiles(urls: [URL], to destDir: URL, subdirectory: String? = nil) async -> ExportResult {
        isExporting = true
        exportProgress = 0
        currentFileName = nil
        lastExportResult = nil

        let result = await copyFiles(urls, to: destDir, subdirectory: subdirectory)
        isExporting = false
        lastExportResult = result
        return result
    }

    @MainActor
    func reset() {
        lastExportResult = nil
        currentFileName = nil
    }

    private func copyFiles(_ urls: [URL], to destDir: URL, subdirectory: String? = nil) async -> ExportResult {
        let accessing = destDir.startAccessingSecurityScopedResource()
        defer { if accessing { destDir.stopAccessingSecurityScopedResource() } }

        var targetDir = destDir
        if let subdirectory, !subdirectory.isEmpty {
            targetDir = destDir.appendingPathComponent(subdirectory)
            do {
                try FileManager.default.createDirectory(at: targetDir, withIntermediateDirectories: true)
            } catch {
                return ExportResult(
                    success: false, filesCopied: 0, totalFiles: urls.count,
                    message: "Failed to create directory: \(subdirectory)"
                )
            }
        }

        var copied = 0
        var failed = 0
        let total = urls.count

        for (index, source) in urls.enumerated() {
            let name = source.lastPathComponent
            await MainActor.run {
                self.currentFileName = name
                self.exportProgress = Double(index) / Double(total)
            }

            let dest = targetDir.appendingPathComponent(name)
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
