import Foundation

/// Represents a discovered or manually-configured server connection.
struct ServerConnection: Identifiable, Codable, Hashable {
    var id: String { "\(host):\(port)" }
    let host: String
    let port: Int
    var name: String
    var version: String?
    var platform: String?
    var externalURL: String?

    /// Build local URL from host and port.
    var localURL: URL? {
        var components = URLComponents()
        components.scheme = "http"
        components.host = host  // URLComponents handles IPv6 bracketing automatically
        components.port = port
        return components.url
    }

    var hasExternalURL: Bool {
        guard let externalURL else { return false }
        return URL(string: externalURL) != nil
    }

    // Backward-compatible JSON keys (saved data uses "url")
    enum CodingKeys: String, CodingKey {
        case host, port, name, version, platform
        case externalURL = "url"
    }
}
