import SwiftUI

struct SyncStatusView: View {
    @Environment(AppState.self) private var appState
    @State private var keys: [SyncKeySummary] = []
    @State private var detail: SyncStatusDetail?
    @State private var selectedKey: String?
    @State private var destinations: [SyncDestination] = []
    @State private var usbKeyNames: Set<String> = []
    @State private var vm = OperationViewModel()
    @State private var profile: String = ""
    @State private var usbDir: String = ""
    @State private var isLoading = false
    @State private var error: String?
    @State private var showDeleteConfirm = false
    @State private var keyToDelete: String?
    @State private var showDeletePlaylistConfirm = false
    @State private var playlistToDelete: (String, String)?
    @State private var showDeleteDestConfirm = false
    @State private var destToDelete: String?

    var body: some View {
        List {
            if isLoading && keys.isEmpty {
                ProgressView("Loading sync status...")
                    .frame(maxWidth: .infinity)
            } else if keys.isEmpty {
                ContentUnavailableView(
                    "No Sync History",
                    systemImage: "arrow.left.arrow.right",
                    description: Text("Sync files to a destination to start tracking.")
                )
            } else {
                keysSection
                if let detail, selectedKey != nil {
                    detailSection(detail)
                }
            }

            if !destinations.isEmpty {
                destinationsSection
            }

            if let error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }

            if vm.isRunning || !vm.logMessages.isEmpty {
                ProgressPanel(vm: vm)
            }
        }
        .navigationTitle("Sync Status")
        .refreshable { await load() }
        .task { await load() }
        .confirmationDialog(
            "Delete Sync Key",
            isPresented: $showDeleteConfirm,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                if let key = keyToDelete {
                    Task { await deleteKey(key) }
                }
            }
        } message: {
            Text("Delete all sync tracking data for \(keyToDelete ?? "")?")
        }
        .confirmationDialog(
            "Remove Destination",
            isPresented: $showDeleteDestConfirm,
            titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) {
                if let name = destToDelete {
                    Task { await deleteDestination(name) }
                }
            }
        } message: {
            Text("Remove saved destination \"\(destToDelete ?? "")\"?")
        }
        .confirmationDialog(
            "Delete Playlist Tracking",
            isPresented: $showDeletePlaylistConfirm,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                if let (key, playlist) = playlistToDelete {
                    Task { await deletePlaylist(key, playlist) }
                }
            }
        } message: {
            if let (key, playlist) = playlistToDelete {
                Text("Delete tracking for \"\(playlist)\" on \"\(key)\"?")
            }
        }
    }

    // MARK: - Keys List

    private var keysSection: some View {
        Section("Sync Keys") {
            ForEach(keys) { key in
                Button {
                    selectedKey = key.keyName
                    Task { await loadDetail(key.keyName) }
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: usbKeyNames.contains(key.keyName) ? "externaldrive.connected.to.line.below" : "folder.fill")
                                    .foregroundStyle(.secondary)
                                Text(key.keyName)
                                    .font(.subheadline.weight(.medium))
                            }
                            HStack(spacing: 8) {
                                Text("\(key.syncedFiles)/\(key.totalFiles) files")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let date = key.lastSyncDate {
                                    Text(date, style: .relative)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            if key.newFiles > 0 {
                                Text("+\(key.newFiles) new")
                                    .font(.caption)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.yellow.opacity(0.2))
                                    .foregroundStyle(.yellow)
                                    .clipShape(Capsule())
                            } else {
                                Text("synced")
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                            if key.newPlaylists > 0 {
                                Text("\(key.newPlaylists) new PL")
                                    .font(.caption)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.2))
                                    .foregroundStyle(.blue)
                                    .clipShape(Capsule())
                            }
                        }
                        if selectedKey == key.keyName {
                            Image(systemName: "chevron.down")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) {
                        keyToDelete = key.keyName
                        showDeleteConfirm = true
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
                .swipeActions(edge: .leading) {
                    Button {
                        Task { await syncKey(key.keyName) }
                    } label: {
                        Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .tint(.blue)
                    .disabled(!isKeyAvailable(key.keyName) || vm.isRunning)
                }
            }
        }
    }

    // MARK: - Playlist Detail

    private func detailSection(_ detail: SyncStatusDetail) -> some View {
        Section("Playlists: \(detail.usbKey)") {
            Button {
                Task { await pruneKey(detail.usbKey) }
            } label: {
                Label("Prune Stale Records", systemImage: "eraser")
                    .font(.subheadline)
                    .foregroundStyle(.yellow)
            }
            if detail.playlists.isEmpty {
                Text("No export files found")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(detail.playlists) { playlist in
                    HStack {
                        Text(playlist.name)
                            .font(.subheadline)
                        Spacer()
                        Text("\(playlist.syncedFiles)/\(playlist.totalFiles)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if playlist.isNewPlaylist {
                            Text("NEW")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(.blue.opacity(0.2))
                                .foregroundStyle(.blue)
                                .clipShape(Capsule())
                        } else if playlist.newFiles > 0 {
                            Text("+\(playlist.newFiles)")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(.yellow.opacity(0.2))
                                .foregroundStyle(.yellow)
                                .clipShape(Capsule())
                        } else {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                                .foregroundStyle(.green)
                        }
                    }
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) {
                            playlistToDelete = (detail.usbKey, playlist.name)
                            showDeletePlaylistConfirm = true
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                    .swipeActions(edge: .leading) {
                        Button {
                            Task { await syncPlaylist(detail.usbKey, playlist: playlist.name) }
                        } label: {
                            Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                        }
                        .tint(.blue)
                        .disabled(!isKeyAvailable(detail.usbKey) || vm.isRunning)
                    }
                }
            }
        }
    }

    // MARK: - Saved Destinations

    private var destinationsSection: some View {
        Section("Saved Destinations") {
            ForEach(destinations) { dest in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(dest.name)
                            .font(.subheadline.weight(.medium))
                        Text(dest.path)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if dest.available {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(.green)
                    } else {
                        Text("unavailable")
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .swipeActions(edge: .trailing) {
                    Button(role: .destructive) {
                        destToDelete = dest.name
                        showDeleteDestConfirm = true
                    } label: {
                        Label("Remove", systemImage: "trash")
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        error = nil
        do {
            async let k = appState.apiClient.getSyncStatus()
            async let d = appState.apiClient.getSyncDestinations()
            async let st = appState.apiClient.getStatus()
            async let se = appState.apiClient.getSettings()
            keys = try await k
            let destResponse = try? await d
            destinations = destResponse?.saved ?? []
            usbKeyNames = Set((destResponse?.usb ?? []).map { $0.name })
            if let status = try? await st {
                profile = status.profile
            }
            if let settings = try? await se {
                if case .string(let dir) = settings.settings["usb_dir"] {
                    usbDir = dir
                } else {
                    usbDir = "RZR/Music"
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private func loadDetail(_ key: String) async {
        do {
            detail = try await appState.apiClient.getSyncStatusDetail(key: key)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func deleteKey(_ key: String) async {
        do {
            try await appState.apiClient.deleteSyncKey(key: key)
            if selectedKey == key {
                selectedKey = nil
                detail = nil
            }
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func deletePlaylist(_ key: String, _ playlist: String) async {
        do {
            _ = try await appState.apiClient.deleteSyncPlaylist(key: key, playlist: playlist)
            await loadDetail(key)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func deleteDestination(_ name: String) async {
        do {
            try await appState.apiClient.deleteSyncDestination(name: name)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func pruneKey(_ key: String) async {
        do {
            _ = try await appState.apiClient.pruneSyncKey(key: key)
            await loadDetail(key)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Sync Availability

    private func isKeyAvailable(_ keyName: String) -> Bool {
        if usbKeyNames.contains(keyName) { return true }
        return destinations.first(where: { $0.name == keyName })?.available == true
    }

    private func destType(for keyName: String) -> String {
        usbKeyNames.contains(keyName) ? "usb" : "saved"
    }

    // MARK: - Sync Actions

    private func syncKey(_ keyName: String) async {
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.syncToDestination(
                sourceDir: "export/\(profile)",
                type: destType(for: keyName),
                destination: keyName,
                usbDir: destType(for: keyName) == "usb" ? usbDir : nil
            )
        }
        await load()
    }

    private func syncPlaylist(_ keyName: String, playlist: String) async {
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.syncToDestination(
                sourceDir: "export/\(profile)/\(playlist)",
                type: destType(for: keyName),
                destination: keyName,
                usbDir: destType(for: keyName) == "usb" ? usbDir : nil
            )
        }
        await load()
    }
}
