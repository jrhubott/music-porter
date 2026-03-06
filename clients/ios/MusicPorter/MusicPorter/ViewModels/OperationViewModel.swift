import Foundation

/// Shared view model for running server operations with SSE progress tracking.
@MainActor @Observable
final class OperationViewModel {
    var isRunning = false
    var isCompleted: Bool { status == "completed" }
    var taskId: String?
    var logMessages: [LogEntry] = []
    var progress: Double = 0
    var progressStage: String = ""
    var status: String = ""
    var error: String?

    struct LogEntry: Identifiable {
        let id = UUID()
        let level: String
        let message: String
        let timestamp = Date()
    }

    /// Run an operation and stream its progress.
    func run(api: APIClient, operation: () async throws -> String) async {
        isRunning = true
        logMessages = []
        progress = 0
        progressStage = ""
        status = "starting"
        error = nil

        do {
            let id = try await operation()
            taskId = id
            status = "running"

            let sseClient = SSEClient(apiClient: api)
            for await event in await sseClient.events(taskId: id) {
                handleEvent(event)
            }
        } catch let apiError as APIError {
            error = apiError.localizedDescription
            status = "failed"
        } catch {
            self.error = error.localizedDescription
            status = "failed"
        }

        isRunning = false
    }

    private func handleEvent(_ event: SSEEvent) {
        switch event {
        case .log(let level, let message):
            logMessages.append(LogEntry(level: level, message: message))
        case .progress(_, _, let percent, let stage):
            progress = Double(percent) / 100.0
            progressStage = stage
        case .heartbeat:
            break
        case .done(let doneStatus, _, let err):
            status = doneStatus
            if let err, !err.isEmpty {
                error = err
            }
        }
    }

    func reset() {
        isRunning = false
        taskId = nil
        logMessages = []
        progress = 0
        progressStage = ""
        status = ""
        error = nil
    }
}
