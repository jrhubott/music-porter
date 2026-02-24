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
            .navigationDestination(for: MusicKit.Playlist.self) { playlist in
                AppleMusicPlaylistDetailView(playlist: playlist)
            }
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
                    NavigationLink(value: playlist) {
                        appleMusicRow(playlist)
                    }
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
                    .buttonStyle(.borderless)
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

// MARK: - Playlist Detail

struct AppleMusicPlaylistDetailView: View {
    @Environment(AppState.self) private var appState
    let playlist: MusicKit.Playlist
    @State private var tracks: [MusicKit.Track] = []
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        List {
            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
            } else if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
            } else if tracks.isEmpty {
                Text("No tracks found")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(tracks) { track in
                    Button {
                        appState.audioPlayer.playAppleMusicTrack(track: track, in: tracks)
                    } label: {
                        trackRow(track)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .navigationTitle(playlist.name)
        .task {
            await loadTracks()
        }
    }

    private func loadTracks() async {
        isLoading = true
        error = nil
        do {
            tracks = try await appState.musicKit.fetchPlaylistTracks(playlist: playlist)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private var isNowPlayingAppleMusic: Bool {
        appState.audioPlayer.nowPlaying?.source == .appleMusic
    }

    private func trackRow(_ track: MusicKit.Track) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                if isNowPlayingAppleMusic && appState.audioPlayer.currentAppleMusicTrackID == track.id {
                    Image(systemName: "speaker.wave.2.fill")
                        .foregroundStyle(Color.accentColor)
                        .font(.caption)
                }
                Text(track.title)
                    .font(.body)
                    .foregroundStyle(
                        isNowPlayingAppleMusic && appState.audioPlayer.currentAppleMusicTrackID == track.id
                            ? Color.accentColor : .primary
                    )
            }
            HStack {
                Text(track.artistName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let albumTitle = track.albumTitle {
                    Text("·")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(albumTitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                if let duration = track.duration {
                    Text(Self.formatDuration(duration))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }
        }
        .padding(.vertical, 2)
    }

    private static func formatDuration(_ interval: TimeInterval) -> String {
        let minutes = Int(interval) / 60
        let seconds = Int(interval) % 60
        return "\(minutes):\(String(format: "%02d", seconds))"
    }
}
