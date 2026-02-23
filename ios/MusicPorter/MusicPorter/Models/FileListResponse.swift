import Foundation

/// Response from GET /api/files/<playlist_key>
struct FileListResponse: Codable {
    let playlist: String
    let profile: String
    let fileCount: Int
    let files: [Track]

    enum CodingKeys: String, CodingKey {
        case playlist, profile, files
        case fileCount = "file_count"
    }
}
