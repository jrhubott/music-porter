import Foundation

/// A playlist configured on the server.
struct Playlist: Identifiable, Codable, Hashable {
    var id: String { key }
    let key: String
    let url: String
    let name: String
}
