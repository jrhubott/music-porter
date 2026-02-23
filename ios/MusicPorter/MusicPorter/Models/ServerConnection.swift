import Foundation

/// Represents a discovered or manually-configured server connection.
struct ServerConnection: Identifiable, Codable, Hashable {
    var id: String { "\(host):\(port)" }
    let host: String
    let port: Int
    var name: String
    var version: String?
    var platform: String?

    var baseURL: URL? {
        URL(string: "http://\(host):\(port)")
    }

    func apiURL(path: String) -> URL? {
        baseURL?.appendingPathComponent(path)
    }
}
