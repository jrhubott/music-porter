import Foundation

/// Persisted state for a playlist download batch, surviving app termination.
struct PendingDownloadState: Codable {
    let playlist: String
    let totalFiles: Int
    var completedFiles: [String]
    var failedFiles: [String]
}

/// Lightweight UserDefaults-backed persistence for background download progress.
enum DownloadStateStore {
    private static let key = "pendingDownloads"

    static func save(_ states: [PendingDownloadState]) {
        guard let data = try? JSONEncoder().encode(states) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    static func load() -> [PendingDownloadState] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let states = try? JSONDecoder().decode([PendingDownloadState].self, from: data) else {
            return []
        }
        return states
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: key)
    }

    static func markFileComplete(playlist: String, filename: String) {
        var states = load()
        guard let index = states.firstIndex(where: { $0.playlist == playlist }) else { return }
        if !states[index].completedFiles.contains(filename) {
            states[index].completedFiles.append(filename)
        }
        save(states)
    }

    static func markFileFailed(playlist: String, filename: String) {
        var states = load()
        guard let index = states.firstIndex(where: { $0.playlist == playlist }) else { return }
        if !states[index].failedFiles.contains(filename) {
            states[index].failedFiles.append(filename)
        }
        save(states)
    }
}
