import SwiftUI
import MusicKit

struct AppleMusicBrowserView: View {
    @Environment(AppState.self) private var appState
    @State private var playlists: [MusicKit.Playlist] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var searchQuery = ""

    var body: some View {
        List {
            if !appState.musicKit.isAuthorized {
                Section {
                    Button("Authorize Apple Music") {
                        Task { await appState.musicKit.requestAuthorization() }
                    }
                }
            } else {
                if isLoading {
                    ProgressView()
                }
                ForEach(playlists) { playlist in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(playlist.name)
                                .font(.headline)
                            if let desc = playlist.shortDescription {
                                Text(desc)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        Spacer()
                        if let url = playlist.url {
                            Button {
                                Task { await sendToServer(url: url.absoluteString, name: playlist.name) }
                            } label: {
                                Image(systemName: "arrow.right.circle.fill")
                                    .foregroundStyle(.blue)
                            }
                        }
                    }
                }
            }

            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        }
        .navigationTitle("Apple Music")
        .searchable(text: $searchQuery)
        .onChange(of: searchQuery) { _, newValue in
            Task { await search(query: newValue) }
        }
        .task { await loadLibrary() }
    }

    private func loadLibrary() async {
        guard appState.musicKit.isAuthorized else { return }
        isLoading = true
        playlists = (try? await appState.musicKit.fetchLibraryPlaylists()) ?? []
        isLoading = false
    }

    private func search(query: String) async {
        guard !query.isEmpty else {
            await loadLibrary()
            return
        }
        isLoading = true
        playlists = (try? await appState.musicKit.searchPlaylists(query: query)) ?? []
        isLoading = false
    }

    private func sendToServer(url: String, name: String) async {
        error = nil
        do {
            let _ = try await appState.apiClient.runPipeline(url: url)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
