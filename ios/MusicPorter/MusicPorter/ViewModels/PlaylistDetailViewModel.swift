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
        profile: String? = nil,
        isOffline: Bool = false
    ) async {
        playlistKey = playlist
        isLoading = true
        error = nil

        if isOffline {
            await loadFromCache(playlist: playlist, metadataCache: metadataCache, audioCacheManager: audioCacheManager)
        } else {
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
                // Graceful degradation: fall back to cache on API failure
                await loadFromCache(playlist: playlist, metadataCache: metadataCache, audioCacheManager: audioCacheManager)
            }
        }
        isLoading = false
    }

    private func loadFromCache(
        playlist: String,
        metadataCache: MetadataCache?,
        audioCacheManager: AudioCacheManager?
    ) async {
        if let metadataCache, let data = await metadataCache.getPlaylistFiles(playlist) {
            tracks = data.files.map { $0.toTrack() }
        }
        if let audioCacheManager {
            let cachedInfos = await audioCacheManager.getCachedFileInfos(playlist)
            cachedUUIDs = Set(cachedInfos.map(\.uuid))
        }
    }
}
