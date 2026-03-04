import Foundation

/// Per-playlist entry in the sync manifest.
struct SyncManifestPlaylist: Codable {
    /// Map of display_filename → Unix timestamp of last sync.
    var files: [String: Double]
}

/// Manifest written to `.music-porter-sync.json` at the sync destination root.
/// Tracks which files have already been synced to support incremental sync.
struct SyncManifest: Codable {
    var destinationName: String
    var serverOrigin: String
    var lastSyncAt: String       // ISO 8601
    var playlists: [String: SyncManifestPlaylist]

    static let manifestFilename = ".music-porter-sync.json"

    enum CodingKeys: String, CodingKey {
        case destinationName = "destination_name"
        case serverOrigin = "server_origin"
        case lastSyncAt = "last_sync_at"
        case playlists
    }

    /// Read manifest from a destination folder. Returns nil if missing or unreadable.
    static func read(from folderURL: URL) -> SyncManifest? {
        let fileURL = folderURL.appendingPathComponent(manifestFilename)
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return try? JSONDecoder().decode(SyncManifest.self, from: data)
    }

    /// Write manifest to the given destination folder.
    func write(to folderURL: URL) {
        let fileURL = folderURL.appendingPathComponent(SyncManifest.manifestFilename)
        guard let data = try? JSONEncoder().encode(self) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
