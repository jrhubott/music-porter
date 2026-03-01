import SwiftUI

struct PlaylistDetailView: View {
    @Environment(AppState.self) private var appState
    let playlist: Playlist
    @State private var vm = PlaylistDetailViewModel()

    var body: some View {
        List {
            ForEach(vm.tracks) { track in
                Button {
                    appState.audioPlayer.playServerTrack(
                        track: track,
                        in: vm.tracks,
                        playlist: playlist.key
                    )
                } label: {
                    TrackRow(
                        track: track,
                        playlist: playlist.key,
                        api: appState.apiClient,
                        isNowPlaying: appState.audioPlayer.currentServerTrackID == track.filename,
                        isCached: vm.cachedUUIDs.contains(track.uuid ?? "")
                    )
                }
                .buttonStyle(.plain)
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
        .refreshable {
            await vm.load(
                api: appState.apiClient, playlist: playlist.key,
                audioCacheManager: appState.audioCacheManager,
                metadataCache: appState.metadataCache,
                profile: appState.activeProfile)
        }
        .task {
            await vm.load(
                api: appState.apiClient, playlist: playlist.key,
                audioCacheManager: appState.audioCacheManager,
                metadataCache: appState.metadataCache,
                profile: appState.activeProfile)
        }
    }
}
