import Foundation

/// Global app state shared across all views.
@MainActor @Observable
final class AppState {
    /// The API version this iOS app expects from the server.
    static let supportedAPIVersion = 1

    // Services
    let apiClient = APIClient()
    let discovery = ServerDiscovery()
    let musicKit = MusicKitService()
    let downloadManager = FileDownloadManager()
    let usbExport = USBExportService()
    let audioPlayer = AudioPlayerService()

    // Connection state
    var isConnected: Bool { apiClient.isConnected }
    var currentServer: ServerConnection? { apiClient.server }

    /// Non-nil when the server's API version doesn't match what this app expects.
    var apiVersionWarning: String?

    // Auto-reconnect task (cancellable to avoid race with QR scan connect)
    private var autoReconnectTask: Task<Bool, Never>?

    // Saved connection for auto-reconnect
    var savedServer: ServerConnection? {
        get {
            guard let data = UserDefaults.standard.data(forKey: "savedServer") else { return nil }
            return try? JSONDecoder().decode(ServerConnection.self, from: data)
        }
        set {
            if let newValue, let data = try? JSONEncoder().encode(newValue) {
                UserDefaults.standard.set(data, forKey: "savedServer")
            } else {
                UserDefaults.standard.removeObject(forKey: "savedServer")
            }
        }
    }

    func cancelAutoReconnect() {
        autoReconnectTask?.cancel()
        autoReconnectTask = nil
    }

    func connect(server: ServerConnection, apiKey: String) async throws {
        cancelAutoReconnect()
        apiClient.configure(server: server, apiKey: apiKey)
        downloadManager.configure(apiClient: apiClient)
        audioPlayer.configure(apiClient: apiClient)
        let response = try await apiClient.validateConnection()
        if response.valid {
            savedServer = server
            checkAPIVersion(response.apiVersion)
        } else {
            throw APIError.unauthorized
        }
    }

    private func checkAPIVersion(_ serverVersion: Int?) {
        guard let serverVersion else {
            apiVersionWarning = "Server does not report an API version. Some features may not work correctly. Update the server."
            return
        }
        if serverVersion != Self.supportedAPIVersion {
            if serverVersion > Self.supportedAPIVersion {
                apiVersionWarning = "Server API version (\(serverVersion)) is newer than this app supports (\(Self.supportedAPIVersion)). Update the app for full compatibility."
            } else {
                apiVersionWarning = "Server API version (\(serverVersion)) is older than this app expects (\(Self.supportedAPIVersion)). Update the server for full compatibility."
            }
        } else {
            apiVersionWarning = nil
        }
    }

    func disconnect() {
        audioPlayer.stop()
        apiClient.disconnect()
        savedServer = nil
        apiVersionWarning = nil
    }

    /// Try to reconnect using saved server and keychain API key.
    /// Times out after 3 seconds to avoid blocking the UI.
    /// Stores the task so it can be cancelled by a QR scan connect.
    func attemptAutoReconnect() async -> Bool {
        guard let server = savedServer, let apiKey = KeychainService.load() else { return false }
        let task = Task<Bool, Never> {
            do {
                try await withThrowingTaskGroup(of: Bool.self) { group in
                    group.addTask {
                        try await self.connect(server: server, apiKey: apiKey)
                        return true
                    }
                    group.addTask {
                        try await Task.sleep(for: .seconds(3))
                        throw CancellationError()
                    }
                    let result = try await group.next() ?? false
                    group.cancelAll()
                    return result
                }
                return true
            } catch {
                if !Task.isCancelled {
                    // Clear stale saved connection on failure (but not if cancelled by QR scan)
                    savedServer = nil
                }
                return false
            }
        }
        autoReconnectTask = task
        let result = await task.value
        autoReconnectTask = nil
        return result
    }
}
