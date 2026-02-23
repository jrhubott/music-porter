import Foundation

/// Global app state shared across all views.
@Observable
final class AppState {
    // Services
    let apiClient = APIClient()
    let discovery = ServerDiscovery()
    let musicKit = MusicKitService()
    let downloadManager = FileDownloadManager()
    let usbExport = USBExportService()

    // Connection state
    var isConnected: Bool { apiClient.isConnected }
    var currentServer: ServerConnection? { apiClient.server }

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

    func connect(server: ServerConnection, apiKey: String) async throws {
        apiClient.configure(server: server, apiKey: apiKey)
        downloadManager.configure(apiClient: apiClient)
        let valid = try await apiClient.validateConnection()
        if valid {
            savedServer = server
        } else {
            throw APIError.unauthorized
        }
    }

    func disconnect() {
        apiClient.disconnect()
        savedServer = nil
    }

    /// Try to reconnect using saved server and keychain API key.
    func attemptAutoReconnect() async -> Bool {
        guard let server = savedServer, let apiKey = KeychainService.load() else { return false }
        do {
            try await connect(server: server, apiKey: apiKey)
            return true
        } catch {
            return false
        }
    }
}
