import Foundation

@MainActor @Observable
final class PlaylistDetailViewModel {
    var tracks: [Track] = []
    var playlistKey: String = ""
    var profile: String = ""
    var isLoading = false
    var error: String?

    func load(api: APIClient, playlist: String) async {
        playlistKey = playlist
        isLoading = true
        error = nil
        do {
            let response = try await api.getFiles(playlist: playlist)
            tracks = response.files
            profile = response.profile
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
