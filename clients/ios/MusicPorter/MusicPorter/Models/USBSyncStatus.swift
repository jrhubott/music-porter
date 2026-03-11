import Foundation

/// Summary of a destination group's sync status.
struct SyncStatusSummary: Identifiable, Codable {
    let destinations: [String]
    let lastSyncAt: Double
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let newPlaylists: Int

    var id: String { destinations.joined(separator: ",") }

    /// Display label for the destination group.
    var displayLabel: String { destinations.joined(separator: ", ") }

    /// The first destination name (used for detail lookup).
    var primaryDestination: String { destinations.first ?? "" }

    var lastSyncDate: Date? {
        lastSyncAt > 0 ? Date(timeIntervalSince1970: lastSyncAt) : nil
    }

    enum CodingKeys: String, CodingKey {
        case destinations
        case lastSyncAt = "last_sync_at"
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case newPlaylists = "new_playlists"
    }
}

/// Per-playlist sync info within a sync status detail.
struct SyncPlaylistInfo: Identifiable, Codable {
    let name: String
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let isNewPlaylist: Bool
    /// "synced" | "new" | "behind" | "skipped". nil for older server versions.
    let syncStatus: String?

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case isNewPlaylist = "is_new_playlist"
        case syncStatus = "sync_status"
    }
}

/// Full sync status detail for a destination group.
struct SyncStatusDetail: Codable {
    let destinations: [String]
    let lastSyncAt: Double
    let playlists: [SyncPlaylistInfo]
    let totalFiles: Int
    let syncedFiles: Int
    let newFiles: Int
    let newPlaylists: Int
    /// Saved playlist preferences for this group. nil = sync all playlists.
    let playlistPrefs: [String]?

    /// Display label for the destination group.
    var displayLabel: String { destinations.joined(separator: ", ") }

    var lastSyncDate: Date? {
        lastSyncAt > 0 ? Date(timeIntervalSince1970: lastSyncAt) : nil
    }

    enum CodingKeys: String, CodingKey {
        case destinations
        case lastSyncAt = "last_sync_at"
        case playlists
        case totalFiles = "total_files"
        case syncedFiles = "synced_files"
        case newFiles = "new_files"
        case newPlaylists = "new_playlists"
        case playlistPrefs = "playlist_prefs"
    }
}

/// Result of resetting sync tracking for a destination.
struct ResetTrackingResponse: Codable {
    let reset: Bool
    let filesCleared: Int

    enum CodingKeys: String, CodingKey {
        case reset
        case filesCleared = "files_cleared"
    }
}

/// A saved sync destination.
struct SyncDestination: Identifiable, Codable {
    let name: String
    let path: String
    let type: String
    let available: Bool
    let linkedDestinations: [String]
    /// Saved playlist preferences. nil = sync all playlists.
    let playlistPrefs: [String]?
    /// Optional free-text description for this destination.
    let description: String?

    var id: String { name }

    /// Whether this destination is linked with other destinations.
    var hasLinkedDestinations: Bool { !linkedDestinations.isEmpty }

    enum CodingKeys: String, CodingKey {
        case name, path, type, available, description
        case linkedDestinations = "linked_destinations"
        case playlistPrefs = "playlist_prefs"
    }
}

/// Response from GET /api/sync/destinations.
struct SyncDestinationsResponse: Codable {
    let destinations: [SyncDestination]
}

/// Response from POST /api/sync/destinations/resolve.
struct ResolveDestinationResponse: Codable {
    let destination: SyncDestination
    let created: Bool
    let syncStatus: SyncStatusDetail?

    enum CodingKeys: String, CodingKey {
        case destination, created
        case syncStatus = "sync_status"
    }
}
