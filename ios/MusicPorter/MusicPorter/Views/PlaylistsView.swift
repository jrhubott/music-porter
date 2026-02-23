import SwiftUI
import MusicKit

struct PlaylistsView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = PlaylistsViewModel()

    var body: some View {
        @Bindable var vmBindable = vm
        NavigationStack {
            List {
                serverPlaylistsSection
                appleMusicSection
                errorSection
            }
            .navigationTitle("Playlists")
            .navigationDestination(for: Playlist.self) { playlist in
                PlaylistDetailView(playlist: playlist)
            }
            .searchable(text: $vmBindable.searchQuery, prompt: "Search Apple Music")
            .onChange(of: vm.searchQuery) { _, newValue in
                Task { await vm.searchAppleMusic(query: newValue, musicKit: appState.musicKit) }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        vm.showAddSheet = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $vmBindable.showAddSheet) {
                AddPlaylistSheet(vm: vm)
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

    // MARK: - Server Playlists

    private var serverPlaylistsSection: some View {
        Section("Server Playlists") {
            ForEach(vm.playlists) { playlist in
                NavigationLink(value: playlist) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(playlist.name)
                                .font(.headline)
                            Text(playlist.key)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        let count = vm.fileCount(for: playlist.key)
                        if count > 0 {
                            Text("\(count) files")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .onDelete { indexSet in
                for index in indexSet {
                    let key = vm.playlists[index].key
                    Task { await vm.deletePlaylist(api: appState.apiClient, key: key) }
                }
            }
        }
    }

    // MARK: - Apple Music

    private var appleMusicSection: some View {
        Section("Apple Music") {
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

struct AddPlaylistSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @Bindable var vm: PlaylistsViewModel

    var body: some View {
        NavigationStack {
            Form {
                TextField("Key (e.g. Pop_Workout)", text: $vm.newKey)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                TextField("Apple Music URL", text: $vm.newURL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                TextField("Display Name", text: $vm.newName)
            }
            .navigationTitle("Add Playlist")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        Task {
                            await vm.addPlaylist(api: appState.apiClient)
                        }
                    }
                    .disabled(vm.newKey.isEmpty || vm.newURL.isEmpty || vm.newName.isEmpty)
                }
            }
        }
    }
}
