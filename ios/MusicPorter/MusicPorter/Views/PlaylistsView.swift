import SwiftUI

struct PlaylistsView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = PlaylistsViewModel()

    var body: some View {
        NavigationStack {
            List {
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

                if let error = vm.error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Playlists")
            .navigationDestination(for: Playlist.self) { playlist in
                PlaylistDetailView(playlist: playlist)
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
            .sheet(isPresented: $vm.showAddSheet) {
                AddPlaylistSheet(vm: vm)
            }
            .refreshable { await vm.load(api: appState.apiClient) }
            .task { await vm.load(api: appState.apiClient) }
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
