import Foundation
import MusicKit

/// Provides access to the user's Apple Music library via MusicKit.
@Observable
final class MusicKitService {
    var isAuthorized = false
    var authorizationStatus: MusicAuthorization.Status = .notDetermined

    func requestAuthorization() async {
        let status = await MusicAuthorization.request()
        await MainActor.run {
            self.authorizationStatus = status
            self.isAuthorized = (status == .authorized)
        }
    }

    /// Fetch the user's library playlists.
    func fetchLibraryPlaylists() async throws -> [MusicKit.Playlist] {
        guard isAuthorized else { return [] }
        var request = MusicLibraryRequest<MusicKit.Playlist>()
        request.sort(by: \.name, ascending: true)
        let response = try await request.response()
        return Array(response.items)
    }

    /// Search the Apple Music catalog for playlists.
    func searchPlaylists(query: String) async throws -> [MusicKit.Playlist] {
        guard isAuthorized else { return [] }
        var request = MusicCatalogSearchRequest(term: query, types: [MusicKit.Playlist.self])
        request.limit = 25
        let response = try await request.response()
        return Array(response.playlists)
    }
}
