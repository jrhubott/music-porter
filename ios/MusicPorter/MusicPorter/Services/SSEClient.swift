import Foundation

/// Parses Server-Sent Events from /api/stream/<task_id>.
actor SSEClient {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// Stream events from a server task.
    func events(taskId: String) -> AsyncStream<SSEEvent> {
        AsyncStream { continuation in
            let task = Task {
                guard let server = await apiClient.server else {
                    continuation.finish()
                    return
                }
                guard let url = server.apiURL(path: "api/stream/\(taskId)") else {
                    continuation.finish()
                    return
                }
                var request = URLRequest(url: url)
                if let key = await apiClient.apiKey {
                    request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
                }
                request.timeoutInterval = 300

                do {
                    let (bytes, _) = try await URLSession.shared.bytes(for: request)
                    var buffer = ""

                    for try await line in bytes.lines {
                        if line.hasPrefix("data: ") {
                            let jsonStr = String(line.dropFirst(6))
                            if let data = jsonStr.data(using: .utf8),
                               let event = SSEEvent.parse(from: data) {
                                continuation.yield(event)
                                if case .done = event {
                                    continuation.finish()
                                    return
                                }
                            }
                        }
                    }
                } catch {
                    // Stream ended
                }
                continuation.finish()
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }
}
