import Foundation
import UIKit

/// Connection type indicating which URL the client resolved to.
enum ConnectionType: String {
    case local
    case external
}

/// REST API client for the music-porter server.
@MainActor @Observable
final class APIClient {
    var server: ServerConnection?
    var apiKey: String?
    var isConnected = false
    var activeBaseURL: URL?
    var connectionType: ConnectionType?

    private var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 60
        return URLSession(configuration: config)
    }()

    // In-memory ETag cache for playlists list (matching sync client pattern)
    private var playlistsETag: String?
    private var playlistsCache: [Playlist]?

    // MARK: - Connection

    func configure(server: ServerConnection, apiKey: String) {
        self.server = server
        self.apiKey = apiKey
        KeychainService.save(apiKey: apiKey)
    }

    /// Set the active URL and connection type after resolving dual-URL.
    func setActiveURL(_ url: URL, type: ConnectionType) {
        activeBaseURL = url
        connectionType = type
    }

    /// Validate the API key against the server.
    func validateConnection() async throws -> AuthValidateResponse {
        let response: AuthValidateResponse = try await post("/api/auth/validate", body: [:] as [String: String])
        isConnected = response.valid
        return response
    }

    /// Unauthenticated health probe. Safe to call before auth is established.
    /// Returns a HealthResponse for both 200 (healthy/degraded) and 503 (unhealthy).
    /// Throws on network failure (connection refused, timeout, etc.).
    func fetchHealth(baseURL: URL? = nil) async throws -> HealthResponse {
        let base = baseURL ?? activeBaseURL
        guard let base else { throw APIError.notConfigured }
        guard var comps = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw APIError.notConfigured
        }
        comps.path = "/health"
        comps.queryItems = nil
        guard let url = comps.url else { throw APIError.notConfigured }
        let request = URLRequest(url: url)      // no Authorization header
        let (data, _) = try await session.data(for: request)
        return try JSONDecoder().decode(HealthResponse.self, from: data)
    }

    func disconnect() {
        server = nil
        apiKey = nil
        isConnected = false
        activeBaseURL = nil
        connectionType = nil
        playlistsETag = nil
        playlistsCache = nil
        KeychainService.delete()
    }

    // MARK: - URL Construction

    /// Build a full API URL from a path using the active base URL.
    func buildURL(path: String, queryItems: [URLQueryItem]? = nil) -> URL? {
        guard let baseURL = activeBaseURL else { return nil }
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.path = path.hasPrefix("/") ? path : "/" + path
        if let queryItems { components.queryItems = queryItems }
        return components.url
    }

    // MARK: - Status & Info

    func getStatus() async throws -> ServerStatus {
        try await get("/api/status")
    }

    /// Lightweight health check: returns true if the server responds within the timeout.
    func ping(timeoutSeconds: Int) async -> Bool {
        await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                do {
                    let _: ServerStatus = try await self.getStatus()
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

    func getServerInfo() async throws -> ServerInfoResponse {
        try await get("/api/server-info")
    }

    // MARK: - Playlists

    func getPlaylists() async throws -> [Playlist] {
        let result: ETagResult<[Playlist]> = try await getWithETag("/api/playlists", etag: playlistsETag)
        switch result {
        case .fresh(let playlists, let etag):
            playlistsETag = etag
            playlistsCache = playlists
            return playlists
        case .notModified:
            if let cached = playlistsCache { return cached }
            return try await get("/api/playlists")
        }
    }

    func addPlaylist(key: String, url: String, name: String) async throws {
        let _: OkResponse = try await post("/api/playlists", body: [
            "key": key, "url": url, "name": name,
        ])
    }

    func updatePlaylist(key: String, url: String?, name: String?) async throws {
        var body: [String: String] = [:]
        if let url { body["url"] = url }
        if let name { body["name"] = name }
        let _: OkResponse = try await put("/api/playlists/\(key)", body: body)
    }

    func deletePlaylist(key: String) async throws {
        let _: OkResponse = try await delete("/api/playlists/\(key)")
    }

    func deletePlaylistData(key: String, deleteSource: Bool = true,
                            deleteExport: Bool = true, removeConfig: Bool = false) async throws -> DeleteDataResponse {
        let body: [String: Any] = [
            "delete_source": deleteSource,
            "delete_export": deleteExport,
            "remove_config": removeConfig,
        ]
        return try await postAny("/api/playlists/\(key)/delete-data", body: body)
    }

    // MARK: - Directories

    func getMusicDirectories() async throws -> [String] {
        try await get("/api/directories/music")
    }

    func getExportDirectories() async throws -> [ExportDirectory] {
        try await get("/api/directories/export")
    }

    // MARK: - Files

    func getFiles(playlist: String, profile: String? = nil) async throws -> FileListResponse {
        var queryItems: [URLQueryItem]?
        if let profile, !profile.isEmpty {
            queryItems = [URLQueryItem(name: "profile", value: profile)]
        }
        return try await get("/api/files/\(playlist)", queryItems: queryItems)
    }

    /// Fetch a playlist's file list with ETag support via MetadataCache.
    /// Returns cached data on 304, stores fresh data with its ETag.
    func getFilesWithETag(
        playlist: String,
        profile: String?,
        metadataCache: MetadataCache
    ) async throws -> FileListResponse {
        let cachedETag = await metadataCache.getETag(playlist)
        let path = "/api/files/\(playlist)"
        var queryItems: [URLQueryItem]?
        if let profile, !profile.isEmpty {
            queryItems = [URLQueryItem(name: "profile", value: profile)]
        }

        let result: ETagResult<FileListResponse> = try await getWithETag(path, etag: cachedETag, queryItems: queryItems)
        switch result {
        case .fresh(let response, let etag):
            let cachedFiles = response.files.map { CachedFileInfo(from: $0) }
            await metadataCache.storePlaylistFiles(
                playlist,
                files: cachedFiles,
                etag: etag,
                name: response.playlist
            )
            return response
        case .notModified:
            if let cached = await metadataCache.getPlaylistFiles(playlist) {
                let tracks = cached.files.map { $0.toTrack() }
                return FileListResponse(
                    playlist: cached.playlistName ?? playlist,
                    fileCount: cached.fileCount,
                    files: tracks
                )
            }
            // Fallback if metadata cache is empty despite 304
            return try await get(path)
        }
    }

    /// Download raw file data for cache storage.
    func downloadFileData(
        playlist: String,
        filename: String,
        profile: String? = nil
    ) async throws -> Data {
        guard let url = fileDownloadURL(playlist: playlist, filename: filename, profile: profile) else {
            throw APIError.notConfigured
        }
        let request = authenticatedRequest(for: url)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return data
    }

    func fileDownloadURL(playlist: String, filename: String, profile: String? = nil) -> URL? {
        guard let base = buildURL(path: "/api/files/\(playlist)/\(filename)") else { return nil }
        guard let profile, !profile.isEmpty else { return base }
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
        components?.queryItems = [URLQueryItem(name: "profile", value: profile)]
        return components?.url ?? base
    }

    func artworkURL(playlist: String, filename: String) -> URL? {
        buildURL(path: "/api/files/\(playlist)/\(filename)/artwork")
    }

    func downloadAllURL(playlist: String) -> URL? {
        buildURL(path: "/api/files/\(playlist)/download-all")
    }

    /// URL for SSE task event streaming.
    func streamURL(taskId: String) -> URL? {
        buildURL(path: "/api/stream/\(taskId)")
    }

    /// Fetch cover art image with authentication.
    func fetchArtwork(playlist: String, filename: String) async -> UIImage? {
        guard let url = artworkURL(playlist: playlist, filename: filename) else { return nil }
        let request = authenticatedRequest(for: url)
        guard let (data, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else { return nil }
        return UIImage(data: data)
    }

    // MARK: - EQ Presets

    func getEQPresets(profile: String? = nil) async throws -> EQPresetsResponse {
        var queryItems: [URLQueryItem]?
        if let profile { queryItems = [URLQueryItem(name: "profile", value: profile)] }
        return try await get("/api/eq", queryItems: queryItems)
    }

    func setEQPreset(profile: String, playlist: String? = nil, eq: EQConfig) async throws {
        var body: [String: Any] = [
            "profile": profile,
            "loudnorm": eq.loudnorm,
            "bass_boost": eq.bassBoost,
            "treble_boost": eq.trebleBoost,
            "compressor": eq.compressor,
        ]
        if let playlist { body["playlist"] = playlist }
        let _: OkResponse = try await postAny("/api/eq", body: body)
    }

    func deleteEQPreset(profile: String, playlist: String? = nil) async throws {
        var body: [String: Any] = ["profile": profile]
        if let playlist { body["playlist"] = playlist }
        let _: OkResponse = try await deleteAny("/api/eq", body: body)
    }

    func resolveEQ(profile: String, playlist: String? = nil) async throws -> EQResolveResponse {
        var queryItems = [URLQueryItem(name: "profile", value: profile)]
        if let playlist { queryItems.append(URLQueryItem(name: "playlist", value: playlist)) }
        return try await get("/api/eq/resolve", queryItems: queryItems)
    }

    // MARK: - Operations

    func runPipeline(playlist: String? = nil, url: String? = nil, auto: Bool = false,
                     preset: String? = nil, syncDestination: String? = nil,
                     eq: EQConfig? = nil) async throws -> String {
        var body: [String: Any] = [:]
        if let playlist { body["playlist"] = playlist }
        if let url { body["url"] = url }
        if auto { body["auto"] = true }
        if let preset { body["preset"] = preset }
        if let syncDestination { body["sync_destination"] = syncDestination }
        if let eqDict = eq?.toDict() { body["eq"] = eqDict }
        let response: TaskIdResponse = try await postAny("/api/pipeline/run", body: body)
        return response.taskId
    }

    func runConvert(inputDir: String, outputDir: String? = nil, preset: String = "lossless",
                    force: Bool = false, eq: EQConfig? = nil) async throws -> String {
        var body: [String: Any] = ["input_dir": inputDir, "preset": preset]
        if let outputDir { body["output_dir"] = outputDir }
        if force { body["force"] = true }
        if let eqDict = eq?.toDict() { body["eq"] = eqDict }
        let response: TaskIdResponse = try await postAny("/api/convert/run", body: body)
        return response.taskId
    }

    // MARK: - Sync Destinations

    func getSyncDestinations() async throws -> SyncDestinationsResponse {
        try await get("/api/sync/destinations")
    }

    func addSyncDestination(name: String, path: String) async throws {
        let _: OkResponse = try await post("/api/sync/destinations", body: ["name": name, "path": path])
    }

    func deleteSyncDestination(name: String) async throws {
        let _: OkResponse = try await delete("/api/sync/destinations/\(name)")
    }

    func syncToDestination(sourceDir: String, destination: String, profile: String? = nil, playlistKeys: [String]? = nil) async throws -> String {
        var body: [String: Any] = ["source_dir": sourceDir, "destination": destination]
        if let profile { body["profile"] = profile }
        if let playlistKeys { body["playlist_keys"] = playlistKeys }
        let response: TaskIdResponse = try await postAny("/api/sync/run", body: body)
        return response.taskId
    }

    func savePlaylistPrefs(destination: String, playlistKeys: [String]?) async throws {
        let encoded = destination.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? destination
        if let playlistKeys {
            let _: OkResponse = try await put("/api/sync/destinations/\(encoded)/playlist-prefs", body: ["playlist_keys": playlistKeys])
        } else {
            let _: OkResponse = try await putAny("/api/sync/destinations/\(encoded)/playlist-prefs", body: ["playlist_keys": NSNull()])
        }
    }

    // MARK: - Sync Status

    func getSyncStatus() async throws -> [SyncStatusSummary] {
        try await get("/api/sync/status")
    }

    func getSyncStatusDetail(destName: String) async throws -> SyncStatusDetail {
        try await get("/api/sync/status/\(destName)")
    }

    func resolveDestination(path: String? = nil, name: String? = nil, driveName: String? = nil, linkTo: String? = nil) async throws -> ResolveDestinationResponse {
        var body: [String: String] = [:]
        if let path { body["path"] = path }
        if let name { body["name"] = name }
        if let driveName { body["drive_name"] = driveName }
        if let linkTo { body["link_to"] = linkTo }
        return try await post("/api/sync/destinations/resolve", body: body)
    }

    func linkDestination(name: String, targetDest: String) async throws {
        let _: OkResponse = try await put("/api/sync/destinations/\(name)/link", body: ["destination": targetDest])
    }

    func unlinkDestination(name: String) async throws {
        let _: OkResponse = try await putAny("/api/sync/destinations/\(name)/link", body: ["destination": NSNull()])
    }

    func resetDestinationTracking(name: String) async throws -> ResetTrackingResponse {
        try await postAny("/api/sync/destinations/\(name)/reset", body: [:] as [String: String])
    }

    func getFileSyncStatus(playlist: String) async throws -> [String: [String]] {
        try await get("/api/files/\(playlist)/sync-status")
    }

    func recordClientSync(
        destination: String,
        playlist: String,
        files: [String],
        destPath: String? = nil
    ) async throws {
        var body: [String: Any] = [
            "destination": destination,
            "playlist": playlist,
            "files": files,
        ]
        if let destPath { body["dest_path"] = destPath }
        let _: OkResponse = try await postAny("/api/sync/client-record", body: body)
    }

    // MARK: - Tasks

    func getTasks() async throws -> [TaskInfo] {
        try await get("/api/tasks")
    }

    func getTask(id: String) async throws -> TaskInfo {
        try await get("/api/tasks/\(id)")
    }

    func cancelTask(id: String) async throws {
        let _: OkResponse = try await post("/api/tasks/\(id)/cancel", body: [:] as [String: String])
    }

    // MARK: - Settings

    func getSettings() async throws -> SettingsResponse {
        try await get("/api/settings")
    }

    func updateSettings(_ settings: [String: Any]) async throws {
        let _: OkResponse = try await postAny("/api/settings", body: settings)
    }

    // MARK: - Cookies

    func getBrowsers() async throws -> BrowsersResponse {
        try await get("/api/cookies/browsers")
    }

    func refreshCookies(browser: String = "auto") async throws -> String {
        let response: TaskIdResponse = try await postAny("/api/cookies/refresh", body: ["browser": browser])
        return response.taskId
    }

    // MARK: - Summary

    func getSummary() async throws -> SummaryResponse {
        try await get("/api/summary")
    }

    // MARK: - Library Stats (source music/ directory)

    func getLibraryStats() async throws -> LibraryStatsResponse {
        try await get("/api/library-stats")
    }

    // MARK: - About

    func getAbout() async throws -> AboutResponse {
        try await get("/api/about")
    }

    // MARK: - HTTP Helpers

    private func makeRequest(_ path: String, method: String, queryItems: [URLQueryItem]? = nil) throws -> URLRequest {
        guard let url = buildURL(path: path, queryItems: queryItems) else { throw APIError.notConfigured }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let apiKey {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func get<T: Decodable>(_ path: String, queryItems: [URLQueryItem]? = nil) async throws -> T {
        let request = try makeRequest(path, method: "GET", queryItems: queryItems)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    /// GET with If-None-Match header for ETag-based conditional requests.
    private func getWithETag<T: Decodable>(
        _ path: String,
        etag: String?,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> ETagResult<T> {
        var request = try makeRequest(path, method: "GET", queryItems: queryItems)
        if let etag {
            request.setValue(etag, forHTTPHeaderField: "If-None-Match")
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        let httpNotModifiedStatus = 304
        if http.statusCode == httpNotModifiedStatus {
            return .notModified
        }
        try checkResponse(response, data: data)
        let decoded: T = try decodeResponse(data, response: response)
        let responseETag = http.value(forHTTPHeaderField: "ETag")
        return .fresh(decoded, etag: responseETag)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        var request = try makeRequest(path, method: "POST")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func postAny<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var request = try makeRequest(path, method: "POST")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func put<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        var request = try makeRequest(path, method: "PUT")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func putAny<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var request = try makeRequest(path, method: "PUT")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path, method: "DELETE")
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func deleteAny<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var request = try makeRequest(path, method: "DELETE")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
    }

    private func decodeResponse<T: Decodable>(_ data: Data, response: URLResponse) throws -> T {
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch is DecodingError {
            let preview = String(data: data.prefix(200), encoding: .utf8) ?? "(binary)"
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if preview.trimmingCharacters(in: .whitespaces).hasPrefix("<") {
                throw APIError.serverError(
                    status: status,
                    message: "Server returned HTML instead of JSON. "
                        + "If using a reverse proxy, ensure it forwards /api/ requests correctly.")
            }
            throw APIError.serverError(
                status: status,
                message: "Unexpected response format from server")
        }
    }

    private func checkResponse(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        if http.statusCode == 401 {
            throw APIError.unauthorized
        }
        if http.statusCode == 409 {
            throw APIError.serverBusy
        }
        guard (200...299).contains(http.statusCode) else {
            let message = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
            throw APIError.serverError(status: http.statusCode, message: message ?? "Unknown error")
        }
    }

    /// Create an authenticated URLRequest for use with external download managers.
    func authenticatedRequest(for url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        if let apiKey {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }
}

// MARK: - Response Types

struct AuthValidateResponse: Codable {
    let valid: Bool
    let version: String
    let serverName: String
    let apiVersion: Int?

    enum CodingKeys: String, CodingKey {
        case valid, version
        case serverName = "server_name"
        case apiVersion = "api_version"
    }
}

struct ServerInfoResponse: Codable {
    let name: String
    let version: String
    let platform: String
    let profiles: [String]
    let apiVersion: Int
    let externalURL: String?

    enum CodingKeys: String, CodingKey {
        case name, version, platform, profiles
        case apiVersion = "api_version"
        case externalURL = "external_url"
    }
}

struct OkResponse: Codable {
    let ok: Bool?
    let error: String?
}

struct DeletedCountResponse: Codable {
    let ok: Bool
    let deleted: Int
}

struct DeleteDataResponse: Codable {
    let success: Bool
    let playlistKey: String
    let sourceDeleted: Bool
    let exportDeleted: Bool
    let configRemoved: Bool
    let filesDeleted: Int
    let bytesFreed: Int

    enum CodingKeys: String, CodingKey {
        case success
        case playlistKey = "playlist_key"
        case sourceDeleted = "source_deleted"
        case exportDeleted = "export_deleted"
        case configRemoved = "config_removed"
        case filesDeleted = "files_deleted"
        case bytesFreed = "bytes_freed"
    }
}

struct EQPresetsResponse: Codable {
    let configs: [EQPresetEntry]
}

struct EQPresetEntry: Codable, Identifiable {
    var id: String { "\(profile)_\(playlist ?? "_default")" }
    let profile: String
    let playlist: String?
    let loudnorm: Bool
    let bassBoost: Bool
    let trebleBoost: Bool
    let compressor: Bool

    enum CodingKeys: String, CodingKey {
        case profile, playlist, loudnorm, compressor
        case bassBoost = "bass_boost"
        case trebleBoost = "treble_boost"
    }
}

struct TaskIdResponse: Codable {
    let taskId: String

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
    }
}

struct BrowsersResponse: Codable {
    let `default`: String
    let installed: [String]
}

struct SettingsResponse: Codable {
    let settings: [String: AnyCodableValue]
    let profiles: [String: ProfileInfo]
    let qualityPresets: [String]

    enum CodingKeys: String, CodingKey {
        case settings, profiles
        case qualityPresets = "quality_presets"
    }
}

struct ProfileInfo: Codable {
    let description: String
    let id3Title: String
    let id3Artist: String
    let id3Album: String
    let id3Genre: String
    let id3Extra: [String: String]
    let filename: String
    let directory: String
    let id3Versions: [String]
    let artworkSize: Int
    let usbDir: String

    enum CodingKeys: String, CodingKey {
        case description
        case id3Title = "id3_title"
        case id3Artist = "id3_artist"
        case id3Album = "id3_album"
        case id3Genre = "id3_genre"
        case id3Extra = "id3_extra"
        case filename, directory
        case id3Versions = "id3_versions"
        case artworkSize = "artwork_size"
        case usbDir = "usb_dir"
    }
}

struct SummaryResponse: Codable {
    let totalPlaylists: Int
    let totalFiles: Int
    let totalSizeBytes: Int
    let scanDuration: Double
    let freshness: FreshnessStats
    let playlists: [PlaylistSummary]

    enum CodingKeys: String, CodingKey {
        case playlists, freshness
        case totalPlaylists = "total_playlists"
        case totalFiles = "total_files"
        case totalSizeBytes = "total_size_bytes"
        case scanDuration = "scan_duration"
    }
}

struct FreshnessStats: Codable {
    let current: Int
    let recent: Int
    let stale: Int
    let outdated: Int
}

struct PlaylistSummary: Identifiable, Codable {
    var id: String { name }
    let name: String
    let fileCount: Int
    let sizeBytes: Int
    let avgSizeMb: Double
    let freshness: String
    let lastModified: String?

    enum CodingKeys: String, CodingKey {
        case name, freshness
        case fileCount = "file_count"
        case sizeBytes = "size_bytes"
        case avgSizeMb = "avg_size_mb"
        case lastModified = "last_modified"
    }
}

struct AboutResponse: Codable {
    let version: String
    let releaseNotes: String?

    enum CodingKeys: String, CodingKey {
        case version
        case releaseNotes = "release_notes"
    }
}

struct LibraryStatsResponse: Codable {
    let totalPlaylists: Int
    let totalFiles: Int
    let totalSizeBytes: Int
    let totalExported: Int
    let totalUnconverted: Int
    let scanDuration: Double

    enum CodingKeys: String, CodingKey {
        case totalPlaylists = "total_playlists"
        case totalFiles = "total_files"
        case totalSizeBytes = "total_size_bytes"
        case totalExported = "total_exported"
        case totalUnconverted = "total_unconverted"
        case scanDuration = "scan_duration"
    }
}

enum APIError: LocalizedError {
    case notConfigured
    case invalidResponse
    case unauthorized
    case serverBusy
    case serverError(status: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: return "Not connected to a server"
        case .invalidResponse: return "Invalid server response"
        case .unauthorized: return "Invalid API key"
        case .serverBusy: return "Server is busy with another operation"
        case .serverError(let status, let message): return "Server error (\(status)): \(message)"
        }
    }
}
