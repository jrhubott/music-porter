import Foundation

/// A server-side background task.
struct TaskInfo: Identifiable, Codable {
    let id: String
    let operation: String
    let description: String
    let status: String
    let result: [String: AnyCodableValue]?
    let error: String?
    let elapsed: Double?

    enum CodingKeys: String, CodingKey {
        case id, operation, description, status, result, error, elapsed
    }

    var isRunning: Bool { status == "running" }
    var isCompleted: Bool { status == "completed" }
    var isFailed: Bool { status == "failed" }
}

/// Type-erased Codable value for JSON dictionaries with mixed types.
enum AnyCodableValue: Codable, Hashable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(String.self) { self = .string(v) }
        else { self = .null }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }
}
