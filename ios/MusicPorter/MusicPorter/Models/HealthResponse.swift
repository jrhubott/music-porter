import Foundation

/// A single component check within a health response.
struct HealthCheckItem: Codable {
    let status: String      // "healthy" | "degraded" | "unhealthy"
    let message: String?
}

/// Response from GET /health (unauthenticated).
struct HealthResponse: Codable {
    let status: String      // "healthy" | "degraded" | "unhealthy"
    let version: String
    let uptimeS: Double
    let timestamp: String
    let checks: [String: HealthCheckItem]

    var isHealthy: Bool { status == "healthy" }
    var isDegraded: Bool { status == "degraded" }
    var isUnhealthy: Bool { status == "unhealthy" }

    enum CodingKeys: String, CodingKey {
        case status, version, timestamp, checks
        case uptimeS = "uptime_s"
    }
}
