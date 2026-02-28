import Foundation

/// Local audio file cache — stores server-tagged files by profile.
///
/// Layout: <Application Support>/MusicPorter/cache/<profile>/<playlist>/<display_filename>
/// Index:  <Application Support>/MusicPorter/cache/<profile>/cache-index.json
///
/// Port of sync client's cache-manager.ts. Both implementations must use identical
/// JSON formats, schema versions, and cache invalidation behavior.
actor AudioCacheManager {
    private let cacheDir: URL
    private let indexPath: URL
    private let profile: String
    private var index: CacheIndex

    init(profile: String) {
        self.profile = profile
        self.cacheDir = CacheUtils.cacheDirectory(profile: profile)
        self.indexPath = cacheDir.appendingPathComponent(CacheConstants.cacheIndexFilename)
        self.index = CacheUtils.loadJsonIndex(
            path: indexPath,
            fallback: CacheIndex(profile: profile, entries: [:]),
            validator: { $0.profile == profile }
        )
    }

    // MARK: - Cache Hit

    /// Returns cached file URL if the file is cached, nil otherwise.
    /// Auto-prunes the entry if the file is missing from disk.
    func isCached(_ uuid: String) -> URL? {
        guard let entry = index.entries[uuid] else { return nil }
        let filePath = entryPath(entry)
        guard FileManager.default.fileExists(atPath: filePath.path) else {
            index.entries.removeValue(forKey: uuid)
            persistIndex()
            return nil
        }
        return filePath
    }

    // MARK: - Store

    /// Write data to cache and update the index.
    func storeData(
        _ data: Data,
        file: Track,
        playlistKey: String,
        serverCreatedAt: Double? = nil,
        serverUpdatedAt: Double? = nil
    ) {
        let displayName = file.displayFilename ?? file.filename
        let fileDir = cacheDir.appendingPathComponent(playlistKey)
        let fm = FileManager.default
        if !fm.fileExists(atPath: fileDir.path) {
            try? fm.createDirectory(at: fileDir, withIntermediateDirectories: true)
        }
        let filePath = fileDir.appendingPathComponent(displayName)
        let tmpPath = filePath.appendingPathExtension("tmp")

        do {
            try data.write(to: tmpPath)
            if fm.fileExists(atPath: filePath.path) {
                try fm.removeItem(at: filePath)
            }
            try fm.moveItem(at: tmpPath, to: filePath)

            var entry = CacheEntry(
                uuid: file.uuid ?? file.filename,
                playlist: playlistKey,
                displayFilename: displayName,
                size: data.count,
                cachedAt: CacheUtils.isoNow()
            )
            if let serverCreatedAt {
                entry.serverCreatedAt = ISO8601DateFormatter().string(
                    from: Date(timeIntervalSince1970: serverCreatedAt)
                )
            }
            if let serverUpdatedAt {
                entry.serverUpdatedAt = ISO8601DateFormatter().string(
                    from: Date(timeIntervalSince1970: serverUpdatedAt)
                )
            }
            index.entries[file.uuid ?? file.filename] = entry
            persistIndex()
        } catch {
            try? fm.removeItem(at: tmpPath)
            // Non-fatal — cache write failures don't break the app
        }
    }

    /// Copy an existing file into cache and update the index.
    func storeFromFile(
        _ sourcePath: URL,
        file: Track,
        playlistKey: String,
        serverCreatedAt: Double? = nil,
        serverUpdatedAt: Double? = nil
    ) {
        let displayName = file.displayFilename ?? file.filename
        let fileDir = cacheDir.appendingPathComponent(playlistKey)
        let fm = FileManager.default
        if !fm.fileExists(atPath: fileDir.path) {
            try? fm.createDirectory(at: fileDir, withIntermediateDirectories: true)
        }
        let filePath = fileDir.appendingPathComponent(displayName)
        let tmpPath = filePath.appendingPathExtension("tmp")

        do {
            if fm.fileExists(atPath: tmpPath.path) {
                try fm.removeItem(at: tmpPath)
            }
            try fm.copyItem(at: sourcePath, to: tmpPath)
            if fm.fileExists(atPath: filePath.path) {
                try fm.removeItem(at: filePath)
            }
            try fm.moveItem(at: tmpPath, to: filePath)

            let attrs = try fm.attributesOfItem(atPath: filePath.path)
            let fileSize = (attrs[.size] as? Int) ?? 0

            var entry = CacheEntry(
                uuid: file.uuid ?? file.filename,
                playlist: playlistKey,
                displayFilename: displayName,
                size: fileSize,
                cachedAt: CacheUtils.isoNow()
            )
            if let serverCreatedAt {
                entry.serverCreatedAt = ISO8601DateFormatter().string(
                    from: Date(timeIntervalSince1970: serverCreatedAt)
                )
            }
            if let serverUpdatedAt {
                entry.serverUpdatedAt = ISO8601DateFormatter().string(
                    from: Date(timeIntervalSince1970: serverUpdatedAt)
                )
            }
            index.entries[file.uuid ?? file.filename] = entry
            persistIndex()
        } catch {
            try? fm.removeItem(at: tmpPath)
        }
    }

    // MARK: - Copy Out

    /// Copy a cached file to a destination path. Returns true on success.
    func copyToDestination(_ uuid: String, destPath: URL) -> Bool {
        guard let cachedPath = isCached(uuid) else { return false }
        return CacheUtils.atomicCopyFile(src: cachedPath, dest: destPath)
    }

    /// Add an index entry for a file that already exists in cache (no copy).
    func recordEntry(file: Track, playlistKey: String) {
        let displayName = file.displayFilename ?? file.filename
        let filePath = cacheDir
            .appendingPathComponent(playlistKey)
            .appendingPathComponent(displayName)
        let fm = FileManager.default
        guard fm.fileExists(atPath: filePath.path) else { return }

        guard let attrs = try? fm.attributesOfItem(atPath: filePath.path),
              let fileSize = attrs[.size] as? Int else { return }

        index.entries[file.uuid ?? file.filename] = CacheEntry(
            uuid: file.uuid ?? file.filename,
            playlist: playlistKey,
            displayFilename: displayName,
            size: fileSize,
            cachedAt: CacheUtils.isoNow()
        )
        persistIndex()
    }

    // MARK: - Status

    /// Total size of all cached files in bytes.
    func getTotalSize() -> Int64 {
        var total: Int64 = 0
        for entry in index.entries.values {
            total += Int64(entry.size)
        }
        return total
    }

    /// Returns true if the cache has any entries.
    func hasData() -> Bool {
        !index.entries.isEmpty
    }

    /// Returns list of playlist keys that have cached entries.
    func getCachedPlaylists() -> [String] {
        var playlists = Set<String>()
        for entry in index.entries.values {
            playlists.insert(entry.playlist)
        }
        return Array(playlists)
    }

    /// Returns all cached entries for a playlist.
    func getCachedFileInfos(_ playlistKey: String) -> [CacheEntry] {
        index.entries.values.filter { $0.playlist == playlistKey }
    }

    /// Build cache status for a playlist.
    func getPlaylistCacheStatus(key: String, totalFiles: Int, pinned: Bool) -> PlaylistCacheStatus {
        let cached = index.entries.values.filter { $0.playlist == key }.count
        return PlaylistCacheStatus(playlistKey: key, total: totalFiles, cached: cached, pinned: pinned)
    }

    // MARK: - Staleness

    /// Returns true if the cached file is stale — i.e. the server's updated_at
    /// is newer than what we have cached.
    func isStale(uuid: String, serverUpdatedAt: Double?) -> Bool {
        guard let serverUpdatedAt else { return false }
        guard let entry = index.entries[uuid],
              let cachedUpdatedAt = entry.serverUpdatedAt else { return false }
        let formatter = ISO8601DateFormatter()
        guard let cachedDate = formatter.date(from: cachedUpdatedAt) else { return false }
        let serverTime = Date(timeIntervalSince1970: serverUpdatedAt)
        return serverTime > cachedDate
    }

    // MARK: - Eviction

    /// Remove index entries whose files are missing from disk. Returns count removed.
    func pruneStaleEntries() -> Int {
        let fm = FileManager.default
        var removed = 0
        for (uuid, entry) in index.entries {
            let filePath = entryPath(entry)
            if !fm.fileExists(atPath: filePath.path) {
                index.entries.removeValue(forKey: uuid)
                removed += 1
            }
        }
        if removed > 0 { persistIndex() }
        return removed
    }

    /// Evict oldest files until total size is under maxBytes. Returns bytes freed.
    /// When pinnedPlaylists is provided, unpinned playlists are evicted first.
    func evictToLimit(maxBytes: Int64, pinnedPlaylists: Set<String>? = nil) -> Int64 {
        var totalSize = getTotalSize()
        guard totalSize > maxBytes else { return 0 }

        let sorted = sortedForEviction(pinnedPlaylists: pinnedPlaylists)
        var freed: Int64 = 0
        let fm = FileManager.default

        for entry in sorted {
            if totalSize <= maxBytes { break }
            let filePath = entryPath(entry)
            if fm.fileExists(atPath: filePath.path) {
                try? fm.removeItem(at: filePath)
                freed += Int64(entry.size)
                totalSize -= Int64(entry.size)
            }
            index.entries.removeValue(forKey: entry.uuid)
        }

        persistIndex()
        CacheUtils.removeEmptyDirs(baseDir: cacheDir)
        return freed
    }

    /// Evict only unpinned files until targetBytes have been freed (or no unpinned
    /// files remain). Returns bytes actually freed.
    func evictUnpinnedBytes(targetBytes: Int64, pinnedPlaylists: Set<String>) -> Int64 {
        let unpinned = index.entries.values
            .filter { !pinnedPlaylists.contains($0.playlist) }
            .sorted { entryTimestamp($0) < entryTimestamp($1) }

        guard !unpinned.isEmpty else { return 0 }

        let fm = FileManager.default
        var freed: Int64 = 0
        for entry in unpinned {
            if freed >= targetBytes { break }
            let filePath = entryPath(entry)
            if fm.fileExists(atPath: filePath.path) {
                try? fm.removeItem(at: filePath)
                freed += Int64(entry.size)
            }
            index.entries.removeValue(forKey: entry.uuid)
        }

        if freed > 0 {
            persistIndex()
            CacheUtils.removeEmptyDirs(baseDir: cacheDir)
        }
        return freed
    }

    /// Evict oldest files regardless of pin status until targetBytes have been freed.
    /// Skips protectedUuids (files downloaded this session).
    func evictOldestBytes(targetBytes: Int64, protectedUuids: Set<String>) -> Int64 {
        let evictable = index.entries.values
            .filter { !protectedUuids.contains($0.uuid) }
            .sorted { entryTimestamp($0) < entryTimestamp($1) }

        guard !evictable.isEmpty else { return 0 }

        let fm = FileManager.default
        var freed: Int64 = 0
        for entry in evictable {
            if freed >= targetBytes { break }
            let filePath = entryPath(entry)
            if fm.fileExists(atPath: filePath.path) {
                try? fm.removeItem(at: filePath)
                freed += Int64(entry.size)
            }
            index.entries.removeValue(forKey: entry.uuid)
        }

        if freed > 0 {
            persistIndex()
            CacheUtils.removeEmptyDirs(baseDir: cacheDir)
        }
        return freed
    }

    /// Delete all cached files for a playlist.
    func clearPlaylist(_ playlistKey: String) {
        let uuids = index.entries
            .filter { $0.value.playlist == playlistKey }
            .map(\.key)

        let fm = FileManager.default
        for uuid in uuids {
            if let entry = index.entries[uuid] {
                let filePath = entryPath(entry)
                try? fm.removeItem(at: filePath)
            }
            index.entries.removeValue(forKey: uuid)
        }
        persistIndex()
        CacheUtils.removeEmptyDirs(baseDir: cacheDir)
    }

    /// Delete entire profile cache.
    func clearAll() {
        let fm = FileManager.default
        try? fm.removeItem(at: cacheDir)
        index = CacheIndex(profile: profile, entries: [:])
        try? fm.createDirectory(at: cacheDir, withIntermediateDirectories: true)
        persistIndex()
    }

    // MARK: - Internal

    private func entryPath(_ entry: CacheEntry) -> URL {
        cacheDir
            .appendingPathComponent(entry.playlist)
            .appendingPathComponent(entry.displayFilename)
    }

    private func persistIndex() {
        CacheUtils.saveJsonIndex(path: indexPath, data: index)
    }

    /// Parse a timestamp for sorting — uses server_created_at, falls back to cached_at.
    private func entryTimestamp(_ entry: CacheEntry) -> Date {
        let formatter = ISO8601DateFormatter()
        if let serverCreatedAt = entry.serverCreatedAt,
           let date = formatter.date(from: serverCreatedAt) {
            return date
        }
        return formatter.date(from: entry.cachedAt) ?? .distantPast
    }

    /// Sort entries for eviction: unpinned before pinned, then oldest first.
    private func sortedForEviction(pinnedPlaylists: Set<String>?) -> [CacheEntry] {
        Array(index.entries.values).sorted { a, b in
            if let pinned = pinnedPlaylists {
                let aPinned = pinned.contains(a.playlist)
                let bPinned = pinned.contains(b.playlist)
                if aPinned != bPinned { return !aPinned }
            }
            return entryTimestamp(a) < entryTimestamp(b)
        }
    }
}
