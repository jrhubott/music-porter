import Foundation

/// Utility functions for cache file operations.
/// Port of sync client's cache-utils.ts.
enum CacheUtils {
    /// Application Support base directory for MusicPorter cache.
    static func cacheBaseDirectory() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport
            .appendingPathComponent("MusicPorter")
            .appendingPathComponent(CacheConstants.cacheDirname)
    }

    /// Profile-specific cache directory.
    static func cacheDirectory(profile: String) -> URL {
        cacheBaseDirectory().appendingPathComponent(profile)
    }

    /// Load and parse a JSON file. Returns `fallback` on missing/corrupt/invalid files.
    /// When `validator` is provided, it must return true for the parsed data to be accepted.
    static func loadJsonIndex<T: Decodable>(
        path: URL,
        fallback: T,
        validator: ((T) -> Bool)? = nil
    ) -> T {
        let fm = FileManager.default
        guard fm.fileExists(atPath: path.path) else { return fallback }
        do {
            let data = try Data(contentsOf: path)
            let parsed = try JSONDecoder().decode(T.self, from: data)
            if let validator, !validator(parsed) { return fallback }
            return parsed
        } catch {
            return fallback
        }
    }

    /// Atomically write a JSON file: serialize to `.tmp`, then rename to final path.
    /// Creates parent directories if needed. Errors are silently swallowed (non-fatal).
    static func saveJsonIndex<T: Encodable>(path: URL, data: T) {
        let fm = FileManager.default
        do {
            let dir = path.deletingLastPathComponent()
            if !fm.fileExists(atPath: dir.path) {
                try fm.createDirectory(at: dir, withIntermediateDirectories: true)
            }
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let jsonData = try encoder.encode(data)
            let tmpPath = path.appendingPathExtension("tmp")
            try jsonData.write(to: tmpPath, options: .atomic)
            // Rename tmp to final (atomic on same filesystem)
            if fm.fileExists(atPath: path.path) {
                try fm.removeItem(at: path)
            }
            try fm.moveItem(at: tmpPath, to: path)
        } catch {
            // Non-fatal — cache metadata loss is recoverable
        }
    }

    /// Remove empty subdirectories under `baseDir`.
    static func removeEmptyDirs(baseDir: URL) {
        let fm = FileManager.default
        guard let entries = try? fm.contentsOfDirectory(
            at: baseDir,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        ) else { return }
        for entry in entries {
            guard let isDir = try? entry.resourceValues(forKeys: [.isDirectoryKey]).isDirectory,
                  isDir else { continue }
            let contents = (try? fm.contentsOfDirectory(atPath: entry.path)) ?? []
            if contents.isEmpty {
                try? fm.removeItem(at: entry)
            }
        }
    }

    /// Copy a file atomically: write to `.tmp` beside the destination, then rename.
    /// Creates parent directories if needed. Returns true on success.
    static func atomicCopyFile(src: URL, dest: URL) -> Bool {
        let fm = FileManager.default
        do {
            let destDir = dest.deletingLastPathComponent()
            if !fm.fileExists(atPath: destDir.path) {
                try fm.createDirectory(at: destDir, withIntermediateDirectories: true)
            }
            let tmpPath = dest.appendingPathExtension("tmp")
            if fm.fileExists(atPath: tmpPath.path) {
                try fm.removeItem(at: tmpPath)
            }
            try fm.copyItem(at: src, to: tmpPath)
            if fm.fileExists(atPath: dest.path) {
                try fm.removeItem(at: dest)
            }
            try fm.moveItem(at: tmpPath, to: dest)
            return true
        } catch {
            return false
        }
    }

    /// Current timestamp as ISO 8601 string.
    static func isoNow() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    /// Format bytes into human-readable string.
    static func formatBytes(_ bytes: Int64) -> String {
        let bytesPerKB: Int64 = 1024
        let bytesPerMB: Int64 = 1024 * 1024
        let bytesPerGB: Int64 = 1024 * 1024 * 1024
        if bytes >= bytesPerGB {
            return String(format: "%.1f GB", Double(bytes) / Double(bytesPerGB))
        }
        if bytes >= bytesPerMB {
            return String(format: "%.1f MB", Double(bytes) / Double(bytesPerMB))
        }
        if bytes >= bytesPerKB {
            return String(format: "%.1f KB", Double(bytes) / Double(bytesPerKB))
        }
        return "\(bytes) B"
    }
}
