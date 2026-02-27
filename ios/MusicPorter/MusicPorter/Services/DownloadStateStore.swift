import Foundation

/// Persisted state for a playlist download batch, surviving app termination.
struct PendingDownloadState: Codable {
    let playlist: String
    let totalFiles: Int
    var completedFiles: [String]
    var failedFiles: [String]
    /// Full list of filenames to download (needed for background handoff).
    var allFiles: [String]
}

/// Lightweight UserDefaults-backed persistence for background download progress.
/// Uses an in-memory cache to batch writes — call `flushIfDirty()` periodically
/// and before background handoff to persist the current state.
enum DownloadStateStore {
    private static let key = "pendingDownloads"

    /// In-memory cache of download states. `nil` means cache is cold (not loaded yet).
    private static var cache: [PendingDownloadState]?
    /// Whether the cache has unsaved changes.
    private static var isDirty = false
    /// Number of modifications since last flush.
    private static var modCount = 0
    /// Flush to UserDefaults every N modifications.
    private static let flushInterval = 10

    static func save(_ states: [PendingDownloadState]) {
        cache = states
        persistToDefaults(states)
        isDirty = false
        modCount = 0
    }

    static func load() -> [PendingDownloadState] {
        if let cached = cache {
            return cached
        }
        let loaded = loadFromDefaults()
        cache = loaded
        return loaded
    }

    static func clear() {
        cache = nil
        isDirty = false
        modCount = 0
        UserDefaults.standard.removeObject(forKey: key)
    }

    static func markFileComplete(playlist: String, filename: String) {
        var states = load()
        guard let index = states.firstIndex(where: { $0.playlist == playlist }) else { return }
        if !states[index].completedFiles.contains(filename) {
            states[index].completedFiles.append(filename)
        }
        cache = states
        markDirty()
    }

    static func markFileFailed(playlist: String, filename: String) {
        var states = load()
        guard let index = states.firstIndex(where: { $0.playlist == playlist }) else { return }
        if !states[index].failedFiles.contains(filename) {
            states[index].failedFiles.append(filename)
        }
        cache = states
        markDirty()
    }

    /// Persist the in-memory cache to UserDefaults if there are unsaved changes.
    static func flushIfDirty() {
        guard isDirty, let states = cache else { return }
        persistToDefaults(states)
        isDirty = false
        modCount = 0
    }

    /// Return filenames that haven't completed or failed yet for a given playlist.
    static func remainingFiles(playlist: String) -> [String] {
        let states = load()
        guard let state = states.first(where: { $0.playlist == playlist }) else { return [] }
        let done = Set(state.completedFiles).union(state.failedFiles)
        return state.allFiles.filter { !done.contains($0) }
    }

    // MARK: - Private

    private static func markDirty() {
        isDirty = true
        modCount += 1
        if modCount >= flushInterval {
            flushIfDirty()
        }
    }

    private static func persistToDefaults(_ states: [PendingDownloadState]) {
        guard let data = try? JSONEncoder().encode(states) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    private static func loadFromDefaults() -> [PendingDownloadState] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let states = try? JSONDecoder().decode([PendingDownloadState].self, from: data) else {
            return []
        }
        return states
    }
}
