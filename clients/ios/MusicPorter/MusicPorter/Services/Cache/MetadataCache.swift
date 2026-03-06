import Foundation

/// Persistent cache for API response metadata (playlist file lists + ETags).
///
/// Stores one JSON file per profile at <Application Support>/MusicPorter/cache/<profile>/metadata-cache.json.
/// Separate from the audio cache index (cache-index.json).
///
/// Port of sync client's metadata-cache.ts. Both implementations must use identical
/// JSON formats, schema versions, and cache invalidation behavior.
actor MetadataCache {
    private let cachePath: URL
    private var data: MetadataCacheData

    init(profile: String) {
        let cacheDir = CacheUtils.cacheDirectory(profile: profile)
        let fm = FileManager.default
        if !fm.fileExists(atPath: cacheDir.path) {
            try? fm.createDirectory(at: cacheDir, withIntermediateDirectories: true)
        }
        self.cachePath = cacheDir.appendingPathComponent(CacheConstants.metadataCacheFilename)
        self.data = CacheUtils.loadJsonIndex(
            path: cachePath,
            fallback: MetadataCacheData(
                profile: profile,
                version: CacheConstants.metadataCacheVersion,
                playlists: [:]
            ),
            validator: { $0.profile == profile && $0.version == CacheConstants.metadataCacheVersion }
        )
    }

    // MARK: - Read

    /// Get cached playlist data, or nil if not cached.
    func getPlaylistFiles(_ playlistKey: String) -> CachedPlaylistData? {
        data.playlists[playlistKey]
    }

    /// Get list of playlist keys that have cached metadata.
    func getCachedPlaylists() -> [String] {
        Array(data.playlists.keys)
    }

    /// Get the cached ETag for a playlist, or nil if not cached.
    func getETag(_ playlistKey: String) -> String? {
        data.playlists[playlistKey]?.etag
    }

    // MARK: - Write

    /// Store a playlist file list with its ETag.
    func storePlaylistFiles(
        _ playlistKey: String,
        files: [CachedFileInfo],
        etag: String?,
        name: String? = nil
    ) {
        data.playlists[playlistKey] = CachedPlaylistData(
            files: files,
            etag: etag,
            playlistName: name,
            fileCount: files.count,
            cachedAt: CacheUtils.isoNow()
        )
        persist()
    }

    /// Remove cached data for a playlist.
    func removePlaylist(_ playlistKey: String) {
        guard data.playlists[playlistKey] != nil else { return }
        data.playlists.removeValue(forKey: playlistKey)
        persist()
    }

    /// Clear all cached metadata.
    func clearAll() {
        data.playlists = [:]
        persist()
    }

    // MARK: - Internal

    private func persist() {
        CacheUtils.saveJsonIndex(path: cachePath, data: data)
    }
}
