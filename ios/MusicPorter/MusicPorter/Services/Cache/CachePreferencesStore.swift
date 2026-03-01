import Foundation

/// Persistent cache preferences backed by UserDefaults.
/// Always available — not tied to a server connection.
@MainActor @Observable
final class CachePreferencesStore {
    // MARK: - UserDefaults Keys

    private enum Keys {
        static let pinnedPlaylists = "cachePinnedPlaylists"
        static let unpinnedPlaylists = "cacheUnpinnedPlaylists"
        static let maxCacheBytes = "cacheMaxBytes"
        static let autoPinNewPlaylists = "cacheAutoPinNew"
    }

    // MARK: - Observable State

    private(set) var pinnedPlaylists: [String]
    private(set) var unpinnedPlaylists: [String]
    var maxCacheBytes: Int64 {
        didSet { UserDefaults.standard.set(maxCacheBytes, forKey: Keys.maxCacheBytes) }
    }
    private(set) var autoPinNewPlaylists: Bool

    // MARK: - Init

    init() {
        let defaults = UserDefaults.standard
        self.pinnedPlaylists = defaults.stringArray(forKey: Keys.pinnedPlaylists) ?? []
        self.unpinnedPlaylists = defaults.stringArray(forKey: Keys.unpinnedPlaylists) ?? []
        let stored = defaults.object(forKey: Keys.maxCacheBytes) as? Int64
        self.maxCacheBytes = stored ?? CacheConstants.defaultMaxCacheBytes
        self.autoPinNewPlaylists = defaults.bool(forKey: Keys.autoPinNewPlaylists)
    }

    // MARK: - Pin Management

    func pinPlaylist(_ key: String) {
        guard !pinnedPlaylists.contains(key) else { return }
        pinnedPlaylists.append(key)
        unpinnedPlaylists.removeAll { $0 == key }
        persist()
    }

    func unpinPlaylist(_ key: String) {
        pinnedPlaylists.removeAll { $0 == key }
        if autoPinNewPlaylists && !unpinnedPlaylists.contains(key) {
            unpinnedPlaylists.append(key)
        }
        persist()
    }

    func isPinned(_ key: String) -> Bool {
        pinnedPlaylists.contains(key)
    }

    /// When auto-pin is on, pin server keys not already pinned and not in exclusion list.
    /// Returns newly pinned keys.
    func syncPinsWithServer(_ serverKeys: [String]) -> [String] {
        guard autoPinNewPlaylists else { return [] }
        var newlyPinned: [String] = []
        for key in serverKeys {
            if !pinnedPlaylists.contains(key) && !unpinnedPlaylists.contains(key) {
                pinnedPlaylists.append(key)
                newlyPinned.append(key)
            }
        }
        if !newlyPinned.isEmpty { persist() }
        return newlyPinned
    }

    // MARK: - Auto-Pin Toggle

    func setAutoPinNewPlaylists(_ enabled: Bool) {
        autoPinNewPlaylists = enabled
        if !enabled {
            unpinnedPlaylists = []
        }
        UserDefaults.standard.set(enabled, forKey: Keys.autoPinNewPlaylists)
        persist()
    }

    /// Called when auto-pin is first enabled — adds currently unpinned server keys
    /// to the exclusion list so existing playlists aren't auto-pinned.
    func excludeUnpinnedPlaylists(_ serverKeys: [String]) {
        for key in serverKeys where !pinnedPlaylists.contains(key) {
            if !unpinnedPlaylists.contains(key) {
                unpinnedPlaylists.append(key)
            }
        }
        persist()
    }

    // MARK: - Persistence

    private func persist() {
        let defaults = UserDefaults.standard
        defaults.set(pinnedPlaylists, forKey: Keys.pinnedPlaylists)
        defaults.set(unpinnedPlaylists, forKey: Keys.unpinnedPlaylists)
    }
}
