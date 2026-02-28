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
                guard let url = await apiClient.streamURL(taskId: taskId) else {
                    continuation.finish()
                    return
                }
                var request = await apiClient.authenticatedRequest(for: url)
                request.timeoutInterval = 300

                do {
                    let (bytes, _) = try await URLSession.shared.bytes(for: request)

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
