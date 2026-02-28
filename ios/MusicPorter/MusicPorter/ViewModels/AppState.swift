import Foundation

/// Global app state shared across all views.
@MainActor @Observable
final class AppState {
    /// The API version this iOS app expects from the server.
    static let supportedAPIVersion = 2

    /// Timeout for local URL connection attempts when an external URL is available.
    private static let localTimeoutSeconds = 3
    /// Timeout for external URL or local-only connection attempts.
    private static let standardTimeoutSeconds = 10

    // Services
    let apiClient = APIClient()
    let discovery = ServerDiscovery()
    let musicKit = MusicKitService()
    let downloadManager = FileDownloadManager()
    let usbExport = USBExportService()
    let audioPlayer = AudioPlayerService()

    // Cache services (initialized on connect, per-profile)
    var metadataCache: MetadataCache?
    var audioCacheManager: AudioCacheManager?
    var prefetchEngine: PrefetchEngine?

    // Connection state
    var isConnected: Bool { apiClient.isConnected }
    var currentServer: ServerConnection? { apiClient.server }

    // Tab coordination for guided flow
    var selectedTab: Int = 0
    var pendingPipelinePlaylist: Playlist?

    // Profiles
    var profiles: [String: ProfileInfo] = [:]
    var activeProfile: String {
        get { UserDefaults.standard.string(forKey: "activeProfile") ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: "activeProfile") }
    }

    /// Resolved USB directory from the active profile.
    var usbDir: String {
        profiles[activeProfile]?.usbDir ?? ""
    }

    /// Non-nil when the server's API version doesn't match what this app expects.
    var apiVersionWarning: String?

    // Reconnect state
    var isReconnecting = false
    var reconnectAttempt = 0

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
        isReconnecting = false
        reconnectAttempt = 0
    }

    func connect(server: ServerConnection, apiKey: String) async throws {
        apiClient.configure(server: server, apiKey: apiKey)
        downloadManager.configure(apiClient: apiClient)
        audioPlayer.configure(apiClient: apiClient)
        let response = try await resolveConnection(server: server)
        if response.valid {
            apiClient.server?.name = response.serverName
            apiClient.server?.version = response.version
            // Fetch external URL from server if not already set
            if apiClient.server?.externalURL == nil {
                await fetchExternalURL()
            }
            savedServer = apiClient.server ?? server
            checkAPIVersion(response.apiVersion)
            await fetchProfiles()
            initializeCacheServices()
        } else {
            throw APIError.unauthorized
        }
    }

    /// Fetch profiles from server and set active profile if not already set.
    private func fetchProfiles() async {
        guard let settings = try? await apiClient.getSettings() else { return }
        profiles = settings.profiles
        // Set active profile from server default if user hasn't chosen one
        if activeProfile.isEmpty, case .string(let outputType) = settings.settings["output_type"] {
            activeProfile = outputType
        }
    }

    /// Fetch the server's external URL from /api/server-info and store it.
    private func fetchExternalURL() async {
        guard let info = try? await apiClient.getServerInfo() else { return }
        if let ext = info.externalURL {
            apiClient.server?.externalURL = ext
        }
    }

    /// Try local URL first, then fall back to external URL.
    private func resolveConnection(server: ServerConnection) async throws -> AuthValidateResponse {
        var lastError: Error = APIError.notConfigured

        // Use shorter timeout for local when external is available as fallback
        let localTimeout = server.hasExternalURL
            ? Self.localTimeoutSeconds
            : Self.standardTimeoutSeconds

        // Try local URL first
        if let localURL = server.localURL {
            apiClient.setActiveURL(localURL, type: .local)
            do {
                return try await validateWithTimeout(seconds: localTimeout)
            } catch {
                lastError = error
            }
        }

        // Try external URL
        if let extStr = server.externalURL, let externalURL = URL(string: extStr) {
            apiClient.setActiveURL(externalURL, type: .external)
            do {
                return try await validateWithTimeout(seconds: Self.standardTimeoutSeconds)
            } catch {
                lastError = error
            }
        }

        throw lastError
    }

    /// Validate the connection with a timeout.
    private func validateWithTimeout(seconds: Int) async throws -> AuthValidateResponse {
        try await withThrowingTaskGroup(of: AuthValidateResponse.self) { group in
            group.addTask {
                try await self.apiClient.validateConnection()
            }
            group.addTask {
                try await Task.sleep(for: .seconds(seconds))
                throw URLError(.timedOut)
            }
            let result = try await group.next()!
            group.cancelAll()
            return result
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
        metadataCache = nil
        audioCacheManager = nil
        prefetchEngine = nil
    }

    /// Initialize cache services for the active profile.
    func initializeCacheServices() {
        let profile = activeProfile
        guard !profile.isEmpty else { return }
        let cache = MetadataCache(profile: profile)
        let audioCache = AudioCacheManager(profile: profile)
        metadataCache = cache
        audioCacheManager = audioCache
        prefetchEngine = PrefetchEngine(apiClient: apiClient, cacheManager: audioCache)
    }

    /// Switch to a different profile and reinitialize cache services.
    func switchProfile(_ newProfile: String) {
        activeProfile = newProfile
        initializeCacheServices()
    }

    /// Try to reconnect using saved server and keychain API key.
    /// Retries with increasing backoff until connected or cancelled.
    /// Never clears savedServer on failure — only explicit disconnect does that.
    func attemptAutoReconnect() async -> Bool {
        guard let server = savedServer, let apiKey = KeychainService.load() else { return false }
        isReconnecting = true
        reconnectAttempt = 0

        let task = Task<Bool, Never> {
            while !Task.isCancelled {
                reconnectAttempt += 1
                do {
                    try await connect(server: server, apiKey: apiKey)
                    // Connected successfully
                    isReconnecting = false
                    reconnectAttempt = 0
                    return true
                } catch {
                    if Task.isCancelled { break }
                    // Wait before retrying — backoff: 3s, 5s, 10s, then 10s cap
                    let delay: UInt64 = switch reconnectAttempt {
                    case 1: 3_000_000_000
                    case 2: 5_000_000_000
                    default: 10_000_000_000
                    }
                    try? await Task.sleep(nanoseconds: delay)
                }
            }
            isReconnecting = false
            return false
        }
        autoReconnectTask = task
        let result = await task.value
        autoReconnectTask = nil
        return result
    }
}
