import SwiftUI

struct SyncStatusView: View {
    @Environment(AppState.self) private var appState
    @State private var keys: [USBKeySummary] = []
    @State private var detail: USBSyncStatusDetail?
    @State private var selectedKey: String?
    @State private var isLoading = false
    @State private var error: String?
    @State private var showDeleteConfirm = false
    @State private var keyToDelete: String?
    @State private var showDeletePlaylistConfirm = false
    @State private var playlistToDelete: (String, String)?

    var body: some View {
        List {
            if isLoading && keys.isEmpty {
                ProgressView("Loading sync status...")
                    .frame(maxWidth: .infinity)
            } else if keys.isEmpty {
                ContentUnavailableView(
                    "No USB Sync History",
                    systemImage: "externaldrive",
                    description: Text("Sync files to a USB drive to start tracking.")
                )
            } else {
                keysSection
                if let detail, selectedKey != nil {
                    detailSection(detail)
                }
            }

            if let error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("USB Sync Status")
        .refreshable { await load() }
        .task { await load() }
        .confirmationDialog(
            "Delete USB Key",
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
        Section("USB Keys") {
            ForEach(keys) { key in
                Button {
                    selectedKey = key.keyName
                    Task { await loadDetail(key.keyName) }
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "externaldrive.connected.to.line.below")
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
            }
        }
    }

    // MARK: - Playlist Detail

    private func detailSection(_ detail: USBSyncStatusDetail) -> some View {
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
                }
            }
        }
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        error = nil
        do {
            keys = try await appState.apiClient.getUSBSyncStatus()
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private func loadDetail(_ key: String) async {
        do {
            detail = try await appState.apiClient.getUSBSyncStatusDetail(key: key)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func deleteKey(_ key: String) async {
        do {
            try await appState.apiClient.deleteUSBKey(key: key)
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
            _ = try await appState.apiClient.deleteUSBPlaylist(key: key, playlist: playlist)
            await loadDetail(key)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func pruneKey(_ key: String) async {
        do {
            _ = try await appState.apiClient.pruneUSBKey(key: key)
            await loadDetail(key)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
