import Foundation

/// Response from GET /api/status
struct ServerStatus: Codable {
    let version: String
    let cookies: CookieStatus
    let library: LibraryStats
    let profile: String
    let busy: Bool
}

struct CookieStatus: Codable {
    let valid: Bool
    let exists: Bool
    let reason: String
    let daysRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case valid, exists, reason
        case daysRemaining = "days_remaining"
    }
}

struct LibraryStats: Codable {
    let playlists: Int
    let files: Int
    let sizeMb: Double

    enum CodingKeys: String, CodingKey {
        case playlists, files
        case sizeMb = "size_mb"
    }
}
