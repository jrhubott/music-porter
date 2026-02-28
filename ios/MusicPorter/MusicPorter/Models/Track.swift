import Foundation

/// A single MP3 track in a playlist.
struct Track: Identifiable, Codable, Hashable {
    var id: String { filename }
    let filename: String
    var displayFilename: String?
    let size: Int
    var duration: Double?
    var title: String?
    var artist: String?
    var album: String?
    var uuid: String?
    var hasCoverArt: Bool?
    var createdAt: Double?
    var updatedAt: Double?

    enum CodingKeys: String, CodingKey {
        case filename, size, duration, title, artist, album, uuid
        case displayFilename = "display_filename"
        case hasCoverArt = "has_cover_art"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Display title (falls back to display filename stem, then filename stem).
    var displayTitle: String {
        title ?? displayFilename?.replacingOccurrences(of: ".mp3", with: "")
            ?? filename.replacingOccurrences(of: ".mp3", with: "")
    }
}
