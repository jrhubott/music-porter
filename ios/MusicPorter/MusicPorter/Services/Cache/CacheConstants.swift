import Foundation

/// Constants matching sync client's cache module (cache/constants.ts).
/// Both implementations must stay in sync — see sync-client/packages/core/src/cache/.
enum CacheConstants {
    /// Subdirectory under Application Support for cached audio files.
    static let cacheDirname = "cache"

    /// Per-profile cache index filename.
    static let cacheIndexFilename = "cache-index.json"

    /// Per-profile metadata cache filename.
    static let metadataCacheFilename = "metadata-cache.json"

    /// Current schema version for the metadata cache file.
    static let metadataCacheVersion = 1

    /// Default maximum cache size in bytes (10 GB).
    static let defaultMaxCacheBytes: Int64 = 10 * 1024 * 1024 * 1024

    /// Background prefetch interval in seconds (5 minutes).
    static let backgroundPrefetchIntervalSeconds: TimeInterval = 300

    /// Default number of concurrent prefetch downloads.
    static let defaultPrefetchConcurrency = 4

    /// Suffix for temporary files during atomic writes.
    static let tempSuffix = ".tmp"

    /// Timeout for individual file downloads in seconds.
    static let fileDownloadTimeoutSeconds: TimeInterval = 300
}
