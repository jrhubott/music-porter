import Foundation

/// Summary of a tracked sync key with sync counts.
struct SyncKeySummary: Identifiable, Codable {
    let keyName: String
    let lastSyncAt: Double
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let newPlaylists: Int

    var id: String { keyName }

    var lastSyncDate: Date? {
        lastSyncAt > 0 ? Date(timeIntervalSince1970: lastSyncAt) : nil
    }

    enum CodingKeys: String, CodingKey {
        case keyName = "key_name"
        case lastSyncAt = "last_sync_at"
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case newPlaylists = "new_playlists"
    }
}

/// Backwards compatibility alias.
typealias USBKeySummary = SyncKeySummary

/// Per-playlist sync info within a sync key detail.
struct SyncPlaylistInfo: Identifiable, Codable {
    let name: String
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let isNewPlaylist: Bool

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case isNewPlaylist = "is_new_playlist"
    }
}

/// Backwards compatibility alias.
typealias USBPlaylistSyncInfo = SyncPlaylistInfo

/// Full sync status detail for one sync key.
struct SyncStatusDetail: Codable {
    let syncKey: String
    let lastSyncAt: Double
    let playlists: [SyncPlaylistInfo]
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let newPlaylists: Int

    var lastSyncDate: Date? {
        lastSyncAt > 0 ? Date(timeIntervalSince1970: lastSyncAt) : nil
    }

    enum CodingKeys: String, CodingKey {
        case syncKey = "sync_key"
        case lastSyncAt = "last_sync_at"
        case playlists
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case newPlaylists = "new_playlists"
    }
}

/// Backwards compatibility alias.
typealias USBSyncStatusDetail = SyncStatusDetail

/// Result of pruning stale tracking records.
struct SyncPruneResult: Codable {
    let prunedCount: Int
    let playlistsAffected: [String]

    enum CodingKeys: String, CodingKey {
        case prunedCount = "pruned_count"
        case playlistsAffected = "playlists_affected"
    }
}

/// Backwards compatibility alias.
typealias USBPruneResult = SyncPruneResult

/// A saved sync destination.
struct SyncDestination: Identifiable, Codable {
    let name: String
    let path: String
    let type: String
    let available: Bool

    var id: String { name }
}

/// Response from GET /api/sync/destinations.
struct SyncDestinationsResponse: Codable {
    let destinations: [SyncDestination]
}
