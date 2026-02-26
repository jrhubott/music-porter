import Foundation

/// REST API client for the music-porter server.
@MainActor @Observable
final class APIClient {
    var server: ServerConnection?
    var apiKey: String?
    var isConnected = false

    private var session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 60
        return URLSession(configuration: config)
    }()

    // MARK: - Connection

    func configure(server: ServerConnection, apiKey: String) {
        self.server = server
        self.apiKey = apiKey
        KeychainService.save(apiKey: apiKey)
    }

    /// Validate the API key against the server.
    func validateConnection() async throws -> AuthValidateResponse {
        let response: AuthValidateResponse = try await post("/api/auth/validate", body: [:] as [String: String])
        isConnected = response.valid
        return response
    }

    func disconnect() {
        server = nil
        apiKey = nil
        isConnected = false
        KeychainService.delete()
    }

    // MARK: - Status & Info

    func getStatus() async throws -> ServerStatus {
        try await get("/api/status")
    }

    func getServerInfo() async throws -> ServerInfoResponse {
        try await get("/api/server-info")
    }

    // MARK: - Playlists

    func getPlaylists() async throws -> [Playlist] {
        try await get("/api/playlists")
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

    func getFiles(playlist: String) async throws -> FileListResponse {
        try await get("/api/files/\(playlist)")
    }

    func fileDownloadURL(playlist: String, filename: String) -> URL? {
        server?.apiURL(path: "api/files/\(playlist)/\(filename)")
    }

    func artworkURL(playlist: String, filename: String) -> URL? {
        server?.apiURL(path: "api/files/\(playlist)/\(filename)/artwork")
    }

    func downloadAllURL(playlist: String) -> URL? {
        server?.apiURL(path: "api/files/\(playlist)/download-all")
    }

    // MARK: - Operations

    func runPipeline(playlist: String? = nil, url: String? = nil, auto: Bool = false,
                     preset: String? = nil, copyToUsb: Bool = false) async throws -> String {
        var body: [String: Any] = [:]
        if let playlist { body["playlist"] = playlist }
        if let url { body["url"] = url }
        if auto { body["auto"] = true }
        if let preset { body["preset"] = preset }
        if copyToUsb { body["copy_to_usb"] = true }
        let response: TaskIdResponse = try await postAny("/api/pipeline/run", body: body)
        return response.taskId
    }

    func runConvert(inputDir: String, outputDir: String? = nil, preset: String = "lossless",
                    force: Bool = false) async throws -> String {
        var body: [String: Any] = ["input_dir": inputDir, "preset": preset]
        if let outputDir { body["output_dir"] = outputDir }
        if force { body["force"] = true }
        let response: TaskIdResponse = try await postAny("/api/convert/run", body: body)
        return response.taskId
    }

    func updateTags(directory: String, album: String?, artist: String?) async throws -> String {
        var body: [String: Any] = ["directory": directory]
        if let album { body["album"] = album }
        if let artist { body["artist"] = artist }
        let response: TaskIdResponse = try await postAny("/api/tags/update", body: body)
        return response.taskId
    }

    func restoreTags(directory: String, all: Bool = false, album: Bool = false,
                     title: Bool = false, artist: Bool = false) async throws -> String {
        var body: [String: Any] = ["directory": directory]
        if all { body["all"] = true }
        if album { body["album"] = true }
        if title { body["title"] = true }
        if artist { body["artist"] = true }
        let response: TaskIdResponse = try await postAny("/api/tags/restore", body: body)
        return response.taskId
    }

    func coverArt(action: String, directory: String, source: String? = nil,
                  image: String? = nil, maxSize: Int? = nil) async throws -> String {
        var body: [String: Any] = ["directory": directory]
        if let source { body["source"] = source }
        if let image { body["image"] = image }
        if let maxSize { body["max_size"] = maxSize }
        let response: TaskIdResponse = try await postAny("/api/cover-art/\(action)", body: body)
        return response.taskId
    }

    // MARK: - USB

    func getUSBDrives() async throws -> [String] {
        try await get("/api/usb/drives")
    }

    func syncUSB(sourceDir: String, volume: String, usbDir: String? = nil) async throws -> String {
        var body: [String: Any] = ["source_dir": sourceDir, "volume": volume]
        if let usbDir { body["usb_dir"] = usbDir }
        let response: TaskIdResponse = try await postAny("/api/usb/sync", body: body)
        return response.taskId
    }

    // MARK: - USB Sync Status

    func getUSBSyncStatus() async throws -> [USBKeySummary] {
        try await get("/api/usb/sync-status")
    }

    func getUSBSyncStatusDetail(key: String) async throws -> USBSyncStatusDetail {
        try await get("/api/usb/sync-status/\(key)")
    }

    func getUSBKeys() async throws -> [USBKeySummary] {
        try await get("/api/usb/keys")
    }

    func deleteUSBKey(key: String) async throws {
        let _: OkResponse = try await delete("/api/usb/keys/\(key)")
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

    // MARK: - HTTP Helpers

    private func makeRequest(_ path: String, method: String) throws -> URLRequest {
        guard let server else { throw APIError.notConfigured }
        guard let url = server.apiURL(path: path) else { throw APIError.invalidResponse }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let apiKey {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path, method: "GET")
        let (data, response) = try await session.data(for: request)
        try checkResponse(response, data: data)
        return try decodeResponse(data, response: response)
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

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path, method: "DELETE")
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

    enum CodingKeys: String, CodingKey {
        case name, version, platform, profiles
        case apiVersion = "api_version"
    }
}

struct OkResponse: Codable {
    let ok: Bool?
    let error: String?
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
    let dirStructures: [String]
    let filenameFormats: [String]

    enum CodingKeys: String, CodingKey {
        case settings, profiles
        case qualityPresets = "quality_presets"
        case dirStructures = "dir_structures"
        case filenameFormats = "filename_formats"
    }
}

struct ProfileInfo: Codable {
    let description: String
    let qualityPreset: String
    let artworkSize: Int
    let id3Version: Int
    let directoryStructure: String
    let filenameFormat: String

    enum CodingKeys: String, CodingKey {
        case description
        case qualityPreset = "quality_preset"
        case artworkSize = "artwork_size"
        case id3Version = "id3_version"
        case directoryStructure = "directory_structure"
        case filenameFormat = "filename_format"
    }
}

struct SummaryResponse: Codable {
    let totalPlaylists: Int
    let totalFiles: Int
    let totalSizeBytes: Int
    let scanDuration: Double
    let tagIntegrity: TagIntegrityStats
    let coverArt: CoverArtStats
    let freshness: FreshnessStats
    let playlists: [PlaylistSummary]
    let profile: String

    enum CodingKeys: String, CodingKey {
        case profile, playlists, freshness
        case totalPlaylists = "total_playlists"
        case totalFiles = "total_files"
        case totalSizeBytes = "total_size_bytes"
        case scanDuration = "scan_duration"
        case tagIntegrity = "tag_integrity"
        case coverArt = "cover_art"
    }
}

struct TagIntegrityStats: Codable {
    let checked: Int
    let protected: Int
    let missing: Int
}

struct CoverArtStats: Codable {
    let withArt: Int
    let withoutArt: Int
    let original: Int
    let resized: Int

    enum CodingKeys: String, CodingKey {
        case original, resized
        case withArt = "with_art"
        case withoutArt = "without_art"
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
    let tagsChecked: Int
    let tagsProtected: Int
    let coverWith: Int
    let coverWithout: Int
    let lastModified: String?

    enum CodingKeys: String, CodingKey {
        case name, freshness
        case fileCount = "file_count"
        case sizeBytes = "size_bytes"
        case avgSizeMb = "avg_size_mb"
        case tagsChecked = "tags_checked"
        case tagsProtected = "tags_protected"
        case coverWith = "cover_with"
        case coverWithout = "cover_without"
        case lastModified = "last_modified"
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
