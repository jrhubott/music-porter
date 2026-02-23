import SwiftUI
import MusicKit

struct AppleMusicView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = PlaylistsViewModel()

    var body: some View {
        @Bindable var vmBindable = vm
        NavigationStack {
            List {
                appleMusicSection
                errorSection
            }
            .navigationTitle("Apple Music")
            .searchable(text: $vmBindable.searchQuery, prompt: "Search Apple Music")
            .onChange(of: vm.searchQuery) { _, newValue in
                Task { await vm.searchAppleMusic(query: newValue, musicKit: appState.musicKit) }
            }
            .refreshable {
                await vm.load(api: appState.apiClient)
                await vm.loadAppleMusic(musicKit: appState.musicKit)
            }
            .task {
                await vm.load(api: appState.apiClient)
                await vm.loadAppleMusic(musicKit: appState.musicKit)
            }
        }
    }

    // MARK: - Apple Music

    private var appleMusicSection: some View {
        Section("Apple Music Library") {
            if !appState.musicKit.isAuthorized {
                Button("Authorize Apple Music") {
                    Task { await appState.musicKit.requestAuthorization() }
                }
            } else {
                if vm.isLoadingAppleMusic {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                }
                ForEach(vm.appleMusicPlaylists) { playlist in
                    appleMusicRow(playlist)
                }
                if let appleMusicError = vm.appleMusicError {
                    Label(appleMusicError, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }
        }
    }

    private func appleMusicRow(_ playlist: MusicKit.Playlist) -> some View {
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
                if vm.isAlreadyAdded(url: url) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else if vm.addingPlaylistURL == url.absoluteString {
                    ProgressView()
                } else {
                    Button {
                        Task {
                            await vm.addAppleMusicPlaylist(
                                api: appState.apiClient,
                                url: url.absoluteString,
                                name: playlist.name
                            )
                        }
                    } label: {
                        Image(systemName: "plus.circle")
                            .foregroundStyle(.blue)
                    }
                }
            }
        }
    }

    // MARK: - Error

    @ViewBuilder
    private var errorSection: some View {
        if let error = vm.error {
            Section {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            }
        }
    }
}
