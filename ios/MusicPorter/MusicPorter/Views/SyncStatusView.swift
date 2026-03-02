import SwiftUI

struct SyncStatusView: View {
    @Environment(AppState.self) private var appState
    @State private var groups: [SyncStatusSummary] = []
    @State private var detail: SyncStatusDetail?
    @State private var selectedGroup: String?
    @State private var destinations: [SyncDestination] = []
    @State private var usbDestNames: Set<String> = []
    @State private var vm = OperationViewModel()
    @State private var isLoading = false
    @State private var error: String?
    @State private var showResetConfirm = false
    @State private var destToReset: String?
    @State private var showDeleteDestConfirm = false
    @State private var destToDelete: String?

    var body: some View {
        List {
            if isLoading && groups.isEmpty {
                ProgressView("Loading sync status...")
                    .frame(maxWidth: .infinity)
            } else if groups.isEmpty {
                ContentUnavailableView(
                    "No Sync History",
                    systemImage: "arrow.left.arrow.right",
                    description: Text("Sync files to a destination to start tracking.")
                )
            } else {
                groupsSection
                if let detail, selectedGroup != nil {
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
            "Reset Sync Tracking",
            isPresented: $showResetConfirm,
            titleVisibility: .visible
        ) {
            Button("Reset", role: .destructive) {
                if let name = destToReset {
                    Task { await resetTracking(name) }
                }
            }
        } message: {
            Text("Reset all sync tracking data for \(destToReset ?? "")? All files will be re-synced on next sync.")
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
    }

    // MARK: - Destination Groups

    private var groupsSection: some View {
        Section("Destination Groups") {
            ForEach(groups) { group in
                Button {
                    selectedGroup = group.primaryDestination
                    Task { await loadDetail(group.primaryDestination) }
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: usbDestNames.contains(group.primaryDestination) ? "externaldrive.connected.to.line.below" : "folder.fill")
                                    .foregroundStyle(.secondary)
                                Text(group.displayLabel)
                                    .font(.subheadline.weight(.medium))
                            }
                            HStack(spacing: 8) {
                                Text("\(group.syncedFiles)/\(group.totalFiles) files")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let date = group.lastSyncDate {
                                    Text(date, style: .relative)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            if group.newFiles > 0 {
                                Text("+\(group.newFiles) new")
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
                            if group.newPlaylists > 0 {
                                Text("\(group.newPlaylists) new PL")
                                    .font(.caption)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.2))
                                    .foregroundStyle(.blue)
                                    .clipShape(Capsule())
                            }
                        }
                        if selectedGroup == group.primaryDestination {
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
                        destToReset = group.primaryDestination
                        showResetConfirm = true
                    } label: {
                        Label("Reset", systemImage: "arrow.counterclockwise")
                    }
                }
                .swipeActions(edge: .leading) {
                    Button {
                        Task { await syncDestination(group.primaryDestination) }
                    } label: {
                        Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .tint(.blue)
                    .disabled(!isDestAvailable(group.primaryDestination) || vm.isRunning)
                }
            }
        }
    }

    // MARK: - Playlist Detail

    private func detailSection(_ detail: SyncStatusDetail) -> some View {
        Section("Playlists: \(detail.displayLabel)") {
            Button {
                Task { await resetTracking(detail.destinations.first ?? "") }
            } label: {
                Label("Reset Sync Tracking", systemImage: "arrow.counterclockwise")
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
                    .swipeActions(edge: .leading) {
                        Button {
                            Task { await syncPlaylist(detail.destinations.first ?? "", playlist: playlist.name) }
                        } label: {
                            Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                        }
                        .tint(.blue)
                        .disabled(!isDestAvailable(detail.destinations.first ?? "") || vm.isRunning)
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
                        if dest.hasLinkedDestinations {
                            Text("Linked with: \(dest.linkedDestinations.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.cyan)
                        }
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
            async let g = appState.apiClient.getSyncStatus()
            async let d = appState.apiClient.getSyncDestinations()
            groups = try await g
            let destResponse = try? await d
            let allDests = destResponse?.destinations ?? []
            destinations = allDests
            usbDestNames = Set(allDests.filter { $0.type == "usb" }.map { $0.name })
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private func loadDetail(_ destName: String) async {
        do {
            detail = try await appState.apiClient.getSyncStatusDetail(destName: destName)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func resetTracking(_ destName: String) async {
        do {
            _ = try await appState.apiClient.resetDestinationTracking(name: destName)
            if selectedGroup == destName {
                selectedGroup = nil
                detail = nil
            }
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

    // MARK: - Destination Availability

    private func isDestAvailable(_ destName: String) -> Bool {
        if usbDestNames.contains(destName) { return true }
        return destinations.first(where: { $0.name == destName })?.available == true
    }

    // MARK: - Sync Actions

    private func syncDestination(_ destName: String) async {
        let activeProfile = appState.activeProfile
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.syncToDestination(
                sourceDir: "library",
                destination: destName,
                profile: activeProfile
            )
        }
        await load()
    }

    private func syncPlaylist(_ destName: String, playlist: String) async {
        let activeProfile = appState.activeProfile
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.syncToDestination(
                sourceDir: "library/\(playlist)",
                destination: destName,
                profile: activeProfile
            )
        }
        await load()
    }
}
