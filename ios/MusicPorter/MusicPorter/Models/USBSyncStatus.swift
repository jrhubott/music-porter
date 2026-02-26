import Foundation

/// Summary of a tracked USB key with sync counts.
struct USBKeySummary: Identifiable, Codable {
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

/// Per-playlist sync info within a USB key detail.
struct USBPlaylistSyncInfo: Identifiable, Codable {
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

/// Full sync status detail for one USB key.
struct USBSyncStatusDetail: Codable {
    let usbKey: String
    let lastSyncAt: Double
    let playlists: [USBPlaylistSyncInfo]
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let newPlaylists: Int

    var lastSyncDate: Date? {
        lastSyncAt > 0 ? Date(timeIntervalSince1970: lastSyncAt) : nil
    }

    enum CodingKeys: String, CodingKey {
        case usbKey = "usb_key"
        case lastSyncAt = "last_sync_at"
        case playlists
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case newPlaylists = "new_playlists"
    }
}

/// Result of pruning stale tracking records for a USB key.
struct USBPruneResult: Codable {
    let prunedCount: Int
    let playlistsAffected: [String]

    enum CodingKeys: String, CodingKey {
        case prunedCount = "pruned_count"
        case playlistsAffected = "playlists_affected"
    }
}
