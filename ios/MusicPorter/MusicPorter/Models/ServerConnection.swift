import Foundation

/// Represents a discovered or manually-configured server connection.
struct ServerConnection: Identifiable, Codable, Hashable {
    var id: String { "\(host):\(port)" }
    let host: String
    let port: Int
    var name: String
    var version: String?
    var platform: String?
    var url: String?

    var baseURL: URL? {
        if let url, let parsed = URL(string: url) {
            return parsed
        }
        var components = URLComponents()
        components.scheme = "http"
        components.host = host  // URLComponents handles IPv6 bracketing automatically
        components.port = port
        return components.url
    }

    func apiURL(path: String) -> URL? {
        guard var components = baseURL.flatMap({ URLComponents(url: $0, resolvingAgainstBaseURL: false) }) else {
            return nil
        }
        components.path = path.hasPrefix("/") ? path : "/" + path
        return components.url
    }
}
