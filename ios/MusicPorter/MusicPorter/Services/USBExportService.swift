import Foundation
import UIKit
import UniformTypeIdentifiers

/// Handles exporting downloaded MP3 files to USB drives via UIDocumentPickerViewController.
@Observable
final class USBExportService {
    var isExporting = false
    var exportProgress: Double = 0
    var lastExportResult: ExportResult?

    /// Present a folder picker and copy files to the selected location.
    @MainActor
    func exportFiles(urls: [URL], from viewController: UIViewController) async -> ExportResult {
        isExporting = true
        exportProgress = 0

        return await withCheckedContinuation { continuation in
            let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder])
            picker.allowsMultipleSelection = false

            let delegate = PickerDelegate { [weak self] selectedURL in
                guard let self, let destDir = selectedURL else {
                    let result = ExportResult(success: false, filesCopied: 0, message: "Export cancelled")
                    self?.isExporting = false
                    self?.lastExportResult = result
                    continuation.resume(returning: result)
                    return
                }

                Task {
                    let result = await self.copyFiles(urls, to: destDir)
                    await MainActor.run {
                        self.isExporting = false
                        self.lastExportResult = result
                    }
                    continuation.resume(returning: result)
                }
            }

            picker.delegate = delegate
            // Keep delegate alive
            objc_setAssociatedObject(picker, "delegate", delegate, .OBJC_ASSOCIATION_RETAIN)
            viewController.present(picker, animated: true)
        }
    }

    private func copyFiles(_ urls: [URL], to destDir: URL) async -> ExportResult {
        let accessing = destDir.startAccessingSecurityScopedResource()
        defer { if accessing { destDir.stopAccessingSecurityScopedResource() } }

        var copied = 0
        var failed = 0
        let total = urls.count

        for (index, source) in urls.enumerated() {
            let dest = destDir.appendingPathComponent(source.lastPathComponent)
            do {
                if FileManager.default.fileExists(atPath: dest.path) {
                    try FileManager.default.removeItem(at: dest)
                }
                try FileManager.default.copyItem(at: source, to: dest)
                copied += 1
            } catch {
                failed += 1
            }
            await MainActor.run {
                self.exportProgress = Double(index + 1) / Double(total)
            }
        }

        return ExportResult(
            success: failed == 0,
            filesCopied: copied,
            message: failed == 0
                ? "Exported \(copied) files"
                : "Exported \(copied) files, \(failed) failed"
        )
    }
}

struct ExportResult {
    let success: Bool
    let filesCopied: Int
    let message: String
}

/// Internal delegate for UIDocumentPickerViewController.
private class PickerDelegate: NSObject, UIDocumentPickerDelegate {
    let completion: (URL?) -> Void

    init(completion: @escaping (URL?) -> Void) {
        self.completion = completion
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        completion(urls.first)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        completion(nil)
    }
}
