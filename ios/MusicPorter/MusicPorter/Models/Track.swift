import Foundation

/// A single MP3 track in a playlist.
struct Track: Identifiable, Codable, Hashable {
    var id: String { filename }
    let filename: String
    let size: Int
    var duration: Double?
    var title: String?
    var artist: String?
    var album: String?
    var hasCoverArt: Bool?
    var hasProtectionTags: Bool?

    enum CodingKeys: String, CodingKey {
        case filename, size, duration, title, artist, album
        case hasCoverArt = "has_cover_art"
        case hasProtectionTags = "has_protection_tags"
    }

    /// Display title (falls back to filename stem).
    var displayTitle: String {
        title ?? filename.replacingOccurrences(of: ".mp3", with: "")
    }
}
