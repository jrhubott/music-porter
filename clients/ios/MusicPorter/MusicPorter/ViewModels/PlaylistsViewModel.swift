import Foundation
import MusicKit

@MainActor @Observable
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

    // USB export
    var defaultUsbDir = "RZR/Music"

    // Apple Music state
    var appleMusicPlaylists: [MusicKit.Playlist] = []
    var isLoadingAppleMusic = false
    var appleMusicError: String?
    var searchQuery = ""
    var addingPlaylistURL: String?

    // Guided flow state — set after adding a playlist from Apple Music
    var lastAddedPlaylist: Playlist?
    var showProcessPrompt = false

    func load(api: APIClient, metadataCache: MetadataCache? = nil, isOffline: Bool = false) async {
        isLoading = true
        error = nil

        if isOffline {
            await loadFromCache(metadataCache: metadataCache)
        } else {
            do {
                async let p = api.getPlaylists()
                async let e = api.getExportDirectories()
                playlists = try await p
                exportDirs = try await e
            } catch {
                // Graceful degradation: fall back to cache on API failure
                await loadFromCache(metadataCache: metadataCache)
            }
            // Fetch usb_dir from server settings (best-effort)
            if let settings = try? await api.getSettings(),
               case .string(let dir) = settings.settings["usb_dir"] {
                defaultUsbDir = dir
            }
        }
        isLoading = false
    }

    private func loadFromCache(metadataCache: MetadataCache?) async {
        guard let metadataCache else { return }
        let cachedKeys = await metadataCache.getCachedPlaylists()
        var cachedPlaylists: [Playlist] = []
        var cachedExportDirs: [ExportDirectory] = []
        for key in cachedKeys.sorted() {
            if let data = await metadataCache.getPlaylistFiles(key) {
                let name = data.playlistName ?? key
                cachedPlaylists.append(Playlist(key: key, url: "", name: name))
                cachedExportDirs.append(ExportDirectory(name: key, displayName: name, files: data.fileCount))
            }
        }
        playlists = cachedPlaylists
        exportDirs = cachedExportDirs
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

    func deletePlaylistData(api: APIClient, key: String, deleteSource: Bool,
                            deleteExport: Bool, removeConfig: Bool) async {
        do {
            let result = try await api.deletePlaylistData(
                key: key, deleteSource: deleteSource,
                deleteExport: deleteExport, removeConfig: removeConfig)
            if result.configRemoved {
                await load(api: api)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func fileCount(for key: String) -> Int {
        exportDirs.first { $0.name == key }?.files ?? 0
    }

    // MARK: - Apple Music

    func loadAppleMusic(musicKit: MusicKitService) async {
        guard musicKit.isAuthorized else { return }
        isLoadingAppleMusic = true
        appleMusicError = nil
        do {
            appleMusicPlaylists = try await musicKit.fetchLibraryPlaylists()
        } catch {
            appleMusicError = error.localizedDescription
        }
        isLoadingAppleMusic = false
    }

    func searchAppleMusic(query: String, musicKit: MusicKitService) async {
        guard musicKit.isAuthorized else { return }
        guard !query.isEmpty else {
            await loadAppleMusic(musicKit: musicKit)
            return
        }
        isLoadingAppleMusic = true
        appleMusicError = nil
        do {
            appleMusicPlaylists = try await musicKit.searchPlaylists(query: query)
        } catch {
            appleMusicError = error.localizedDescription
        }
        isLoadingAppleMusic = false
    }

    func addAppleMusicPlaylist(api: APIClient, url: String, name: String) async {
        let key = Self.generateKey(from: name)
        addingPlaylistURL = url
        do {
            try await api.addPlaylist(key: key, url: url, name: name)
            await load(api: api)
            // Set guided flow state
            if let added = playlists.first(where: { $0.key == key }) {
                lastAddedPlaylist = added
                showProcessPrompt = true
            }
        } catch {
            self.error = error.localizedDescription
        }
        addingPlaylistURL = nil
    }

    func dismissProcessPrompt() {
        showProcessPrompt = false
        lastAddedPlaylist = nil
    }

    func isAlreadyAdded(url: URL?) -> Bool {
        guard let url else { return false }
        let urlString = url.absoluteString
        return playlists.contains { $0.url == urlString }
    }

    static func generateKey(from name: String) -> String {
        let cleaned = name.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0 == " " }
        let result = String(cleaned)
            .replacingOccurrences(of: " ", with: "_")
            .replacingOccurrences(of: "__+", with: "_", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        return result.isEmpty ? "Untitled" : result
    }
}
