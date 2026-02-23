import SwiftUI

struct PlaylistDetailView: View {
    @Environment(AppState.self) private var appState
    let playlist: Playlist
    @State private var vm = PlaylistDetailViewModel()

    var body: some View {
        List {
            ForEach(vm.tracks) { track in
                TrackRow(track: track, playlist: playlist.key, api: appState.apiClient)
            }

            if vm.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
            }

            if let error = vm.error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        }
        .navigationTitle(playlist.name)
        .refreshable { await vm.load(api: appState.apiClient, playlist: playlist.key) }
        .task { await vm.load(api: appState.apiClient, playlist: playlist.key) }
    }
}
