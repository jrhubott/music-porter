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
    let usbExport = USBExportService()
    let folderSync = FolderSyncService()
    let audioPlayer = AudioPlayerService()

    // Cache preferences (always available, not tied to connection)
    let cachePreferences = CachePreferencesStore()

    // Cache services (initialized on connect, per-profile)
    var metadataCache: MetadataCache?
    var audioCacheManager: AudioCacheManager?
    var prefetchEngine: PrefetchEngine?
    var backgroundPrefetchService: BackgroundPrefetchService?

    // Connection health monitoring
    var connectionMonitor: ConnectionMonitor?

    // Connection state
    var isConnected: Bool { apiClient.isConnected }
    var currentServer: ServerConnection? { apiClient.server }
    var isOfflineMode = false

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
        connectionMonitor?.notifyManualOffline()
        Task { await checkAndEnterOfflineMode() }
    }

    func connect(server: ServerConnection, apiKey: String) async throws {
        apiClient.configure(server: server, apiKey: apiKey)
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

            // Start or restart connection health monitoring
            if connectionMonitor == nil {
                connectionMonitor = ConnectionMonitor(appState: self)
            }
            connectionMonitor?.notifyConnected()
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
    /// Uses an unauthenticated health probe to determine reachability before
    /// attempting full auth, so a server with a bad API key shows as reachable
    /// rather than offline.
    private func resolveConnection(server: ServerConnection) async throws -> AuthValidateResponse {
        var lastError: Error = APIError.notConfigured

        // Use shorter timeout for local when external is available as fallback
        let localTimeout = server.hasExternalURL
            ? Self.localTimeoutSeconds
            : Self.standardTimeoutSeconds

        // Try local URL — health probe first to distinguish reachability from auth failure
        if let localURL = server.localURL {
            if await probeReachable(baseURL: localURL, timeoutSeconds: localTimeout) {
                apiClient.setActiveURL(localURL, type: .local)
                do {
                    return try await validateWithTimeout(seconds: localTimeout)
                } catch {
                    lastError = error
                }
            }
        }

        // Try external URL
        if let extStr = server.externalURL, let externalURL = URL(string: extStr) {
            if await probeReachable(baseURL: externalURL, timeoutSeconds: Self.standardTimeoutSeconds) {
                apiClient.setActiveURL(externalURL, type: .external)
                do {
                    return try await validateWithTimeout(seconds: Self.standardTimeoutSeconds)
                } catch {
                    lastError = error
                }
            }
        }

        throw lastError
    }

    /// Returns true if the server at baseURL responds to GET /health within the timeout.
    /// A 503 response (server unhealthy) still means "reachable" — only a network
    /// failure (connection refused, timeout) returns false.
    private func probeReachable(baseURL: URL, timeoutSeconds: Int) async -> Bool {
        await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                do {
                    _ = try await self.apiClient.fetchHealth(baseURL: baseURL)
                    return true
                } catch {
                    return false
                }
            }
            group.addTask {
                try? await Task.sleep(for: .seconds(timeoutSeconds))
                return false
            }
            let result = await group.next() ?? false
            group.cancelAll()
            return result
        }
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

    /// Disconnect from the server.
    /// - Parameter explicit: When `true` (user tapped Disconnect), clears everything.
    ///   When `false` (connection lost), keeps `savedServer` and cache services alive for offline mode.
    func disconnect(explicit: Bool = true) {
        audioPlayer.stop()
        backgroundPrefetchService?.stop()
        backgroundPrefetchService = nil
        prefetchEngine = nil
        apiClient.disconnect()
        apiVersionWarning = nil

        if explicit {
            connectionMonitor?.notifyDisconnected()
            connectionMonitor = nil
            savedServer = nil
            isOfflineMode = false
            metadataCache = nil
            audioCacheManager = nil
        }
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

        // Wire cache into audio player
        audioPlayer.configure(apiClient: apiClient, audioCacheManager: audioCache)

        // Start background prefetch service
        let prefetchService = BackgroundPrefetchService(appState: self)
        backgroundPrefetchService = prefetchService
        prefetchService.start()
        prefetchService.notifyConnected()
    }

    /// Switch to a different profile and reinitialize cache services.
    func switchProfile(_ newProfile: String) {
        activeProfile = newProfile
        initializeCacheServices()
    }

    // MARK: - Offline Mode

    /// Enter offline mode: show cached content without a server connection.
    /// Does not manage connection monitor — callers handle that based on context
    /// (manual vs auto-detected offline).
    func enterOfflineMode() {
        isOfflineMode = true
        isReconnecting = false
        autoReconnectTask?.cancel()
        autoReconnectTask = nil
        reconnectAttempt = 0
        initializeCacheServicesForOffline()
    }

    /// Go offline while connected: keeps cache alive, stops server calls, no auto-reconnect.
    /// Called from Settings "Go Offline" button.
    func goOffline() {
        isOfflineMode = true
        apiClient.isConnected = false
        backgroundPrefetchService?.stop()
        connectionMonitor?.notifyManualOffline()
    }

    /// Initialize cache services for offline use — only needs a profile string, no server.
    /// Does NOT create PrefetchEngine or BackgroundPrefetchService (those need server).
    private func initializeCacheServicesForOffline() {
        let profile = activeProfile
        guard !profile.isEmpty else { return }
        // Only create if not already initialized (may still exist from previous connection)
        if metadataCache == nil {
            metadataCache = MetadataCache(profile: profile)
        }
        if audioCacheManager == nil {
            let audioCache = AudioCacheManager(profile: profile)
            audioCacheManager = audioCache
            audioPlayer.configure(apiClient: apiClient, audioCacheManager: audioCache)
        }
    }

    /// Check if offline mode is viable and enter it if so.
    func checkAndEnterOfflineMode() async {
        guard !activeProfile.isEmpty, savedServer != nil else { return }
        guard let cache = metadataCache ?? MetadataCache(profile: activeProfile) as MetadataCache? else { return }
        let cachedPlaylists = await cache.getCachedPlaylists()
        guard !cachedPlaylists.isEmpty else { return }
        enterOfflineMode()
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
