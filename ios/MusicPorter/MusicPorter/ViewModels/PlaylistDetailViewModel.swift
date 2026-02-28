import Foundation

@MainActor @Observable
final class PlaylistDetailViewModel {
    var tracks: [Track] = []
    var playlistKey: String = ""
    var localFilenames: Set<String> = []
    var isLoading = false
    var error: String?

    func load(api: APIClient, playlist: String, downloadManager: FileDownloadManager) async {
        playlistKey = playlist
        isLoading = true
        error = nil
        do {
            let response = try await api.getFiles(playlist: playlist)
            tracks = response.files
            localFilenames = Set(downloadManager.localFiles(playlist: playlist).map(\.lastPathComponent))
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
