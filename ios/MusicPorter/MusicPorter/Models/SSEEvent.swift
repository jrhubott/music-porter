import Foundation

/// A Server-Sent Event from the /api/stream endpoint.
enum SSEEvent {
    case log(level: String, message: String)
    case progress(current: Int, total: Int, percent: Int, stage: String)
    case heartbeat
    case done(status: String, result: [String: AnyCodableValue]?, error: String?)

    /// Parse a JSON data line from SSE.
    static func parse(from data: Data) -> SSEEvent? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return nil
        }
        switch type {
        case "log":
            return .log(
                level: json["level"] as? String ?? "INFO",
                message: json["message"] as? String ?? "")
        case "progress":
            return .progress(
                current: json["current"] as? Int ?? 0,
                total: json["total"] as? Int ?? 0,
                percent: json["percent"] as? Int ?? 0,
                stage: json["stage"] as? String ?? "")
        case "heartbeat":
            return .heartbeat
        case "done":
            return .done(
                status: json["status"] as? String ?? "unknown",
                result: nil,
                error: json["error"] as? String)
        default:
            return nil
        }
    }
}
