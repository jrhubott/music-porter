import Foundation

// MARK: - Cache Index Types (snake_case JSON — matches cache-index.json)

/// A single cached audio file entry in cache-index.json.
struct CacheEntry: Codable {
    let uuid: String
    let playlist: String
    let displayFilename: String
    let size: Int
    let cachedAt: String
    var serverCreatedAt: String?
    var serverUpdatedAt: String?

    enum CodingKeys: String, CodingKey {
        case uuid, playlist, size
        case displayFilename = "display_filename"
        case cachedAt = "cached_at"
        case serverCreatedAt = "server_created_at"
        case serverUpdatedAt = "server_updated_at"
    }
}

/// Top-level structure of cache-index.json.
struct CacheIndex: Codable {
    let profile: String
    var entries: [String: CacheEntry]
}

// MARK: - Metadata Cache Types (camelCase JSON — matches metadata-cache.json)

/// Cached file info stored in metadata-cache.json.
/// Mirrors the server's file list response (Track wire format).
struct CachedFileInfo: Codable {
    let filename: String
    let displayFilename: String?
    let size: Int
    let duration: Double?
    let title: String?
    let artist: String?
    let album: String?
    let uuid: String?
    let hasCoverArt: Bool?
    let createdAt: Double?
    let updatedAt: Double?

    enum CodingKeys: String, CodingKey {
        case filename, size, duration, title, artist, album, uuid
        case displayFilename = "display_filename"
        case hasCoverArt = "has_cover_art"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Create from a Track model.
    init(from track: Track) {
        self.filename = track.filename
        self.displayFilename = track.displayFilename
        self.size = track.size
        self.duration = track.duration
        self.title = track.title
        self.artist = track.artist
        self.album = track.album
        self.uuid = track.uuid
        self.hasCoverArt = track.hasCoverArt
        self.createdAt = track.createdAt
        self.updatedAt = track.updatedAt
    }

    /// Convert back to a Track model.
    func toTrack() -> Track {
        Track(
            filename: filename,
            displayFilename: displayFilename,
            size: size,
            duration: duration,
            title: title,
            artist: artist,
            album: album,
            uuid: uuid,
            hasCoverArt: hasCoverArt,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

/// Cached data for a single playlist in metadata-cache.json.
struct CachedPlaylistData: Codable {
    let files: [CachedFileInfo]
    let etag: String?
    let playlistName: String?
    let fileCount: Int
    let cachedAt: String
}

/// Top-level structure of metadata-cache.json.
struct MetadataCacheData: Codable {
    let profile: String
    let version: Int
    var playlists: [String: CachedPlaylistData]
}

// MARK: - ETag Result

/// Result from an ETag-aware GET request.
enum ETagResult<T> {
    /// Server returned fresh data (200).
    case fresh(T, etag: String?)
    /// Server returned 304 Not Modified — use cached data.
    case notModified
}

// MARK: - Prefetch Types

/// Result of a prefetch operation.
struct PrefetchResult {
    let downloaded: Int
    let skipped: Int
    let failed: Int
    let capacityCapped: Int
    let aborted: Bool
    let durationMs: Int
}

/// Options for a prefetch operation.
struct PrefetchOptions {
    /// Playlist keys to prefetch.
    let playlists: [String]
    /// Output profile name for server-tagged downloads.
    var profile: String?
    /// Number of parallel downloads.
    var concurrency: Int = CacheConstants.defaultPrefetchConcurrency
    /// Maximum cache size in bytes. 0 = unlimited.
    var maxCacheBytes: Int64 = 0
    /// Pinned playlist keys — used for eviction priority (unpinned evicted first).
    var pinnedPlaylists: Set<String> = []
}

/// Progress update during prefetch.
struct PrefetchProgress {
    let phase: String
    let playlist: String?
    let file: String?
    let processed: Int
    let total: Int
    let downloaded: Int
    let skipped: Int
    let failed: Int
}

/// Cache status for a single playlist.
struct PlaylistCacheStatus {
    let playlistKey: String
    let total: Int
    let cached: Int
    let pinned: Bool
}
