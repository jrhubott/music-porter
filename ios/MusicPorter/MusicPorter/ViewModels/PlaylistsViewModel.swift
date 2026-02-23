import Foundation

@Observable
final class PlaylistsViewModel {
    var playlists: [Playlist] = []
    var exportDirs: [ExportDirectory] = []
    var isLoading = false
    var error: String?

    // Add playlist form
    var newKey = ""
    var newURL = ""
    var newName = ""
    var showAddSheet = false

    func load(api: APIClient) async {
        isLoading = true
        error = nil
        do {
            async let p = api.getPlaylists()
            async let e = api.getExportDirectories()
            playlists = try await p
            exportDirs = try await e
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    func addPlaylist(api: APIClient) async {
        guard !newKey.isEmpty, !newURL.isEmpty, !newName.isEmpty else { return }
        do {
            try await api.addPlaylist(key: newKey, url: newURL, name: newName)
            newKey = ""
            newURL = ""
            newName = ""
            showAddSheet = false
            await load(api: api)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func deletePlaylist(api: APIClient, key: String) async {
        do {
            try await api.deletePlaylist(key: key)
            await load(api: api)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func fileCount(for key: String) -> Int {
        exportDirs.first { $0.name == key }?.files ?? 0
    }
}
