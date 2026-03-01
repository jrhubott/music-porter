import Foundation

@MainActor @Observable
final class PlaylistDetailViewModel {
    var tracks: [Track] = []
    var playlistKey: String = ""
    var cachedUUIDs: Set<String> = []
    var isLoading = false
    var error: String?

    func load(
        api: APIClient,
        playlist: String,
        audioCacheManager: AudioCacheManager? = nil,
        metadataCache: MetadataCache? = nil,
        profile: String? = nil
    ) async {
        playlistKey = playlist
        isLoading = true
        error = nil
        do {
            let response: FileListResponse
            if let metadataCache, let profile, !profile.isEmpty {
                response = try await api.getFilesWithETag(
                    playlist: playlist, profile: profile, metadataCache: metadataCache)
            } else {
                response = try await api.getFiles(playlist: playlist)
            }
            tracks = response.files
            if let audioCacheManager {
                let cachedInfos = await audioCacheManager.getCachedFileInfos(playlist)
                cachedUUIDs = Set(cachedInfos.map(\.uuid))
            } else {
                cachedUUIDs = []
            }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
