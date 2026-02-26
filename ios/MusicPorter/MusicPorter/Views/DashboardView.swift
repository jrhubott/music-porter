import SwiftUI

struct DashboardView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = DashboardViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    apiVersionWarningSection
                    serverStatusSection
                    activeOperationsSection
                    sourceLibrarySection
                    exportLibrarySection
                    tagIntegritySection
                    coverArtSection
                    freshnessSection
                    usbSyncSection
                    playlistsSection

                    if let error = vm.error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }
                .padding()
            }
            .navigationTitle("Dashboard")
            .refreshable { await vm.load(api: appState.apiClient) }
            .task { await vm.load(api: appState.apiClient) }
        }
    }

    // MARK: - API Version Warning

    @ViewBuilder
    private var apiVersionWarningSection: some View {
        if let warning = appState.apiVersionWarning {
            GroupBox {
                Label(warning, systemImage: "exclamationmark.triangle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.yellow)
            }
        }
    }

    // MARK: - 1. Server Status

    @ViewBuilder
    private var serverStatusSection: some View {
        if let status = vm.status {
            GroupBox("Server Status") {
                VStack(alignment: .leading, spacing: 8) {
                    LabeledContent("Version", value: status.version)
                    LabeledContent("Profile", value: status.profile)
                    HStack {
                        Text("Cookies")
                        Spacer()
                        StatusBadge(
                            text: status.cookies.valid ? "Valid" : "Invalid",
                            color: status.cookies.valid ? .green : .red)
                        if let days = status.cookies.daysRemaining, status.cookies.valid {
                            Text("\(days)d")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    HStack {
                        Text("Status")
                        Spacer()
                        StatusBadge(
                            text: status.busy ? "Busy" : "Idle",
                            color: status.busy ? .orange : .green)
                    }
                }
            }
        }
    }

    // MARK: - 2. Active Operations

    @ViewBuilder
    private var activeOperationsSection: some View {
        let running = vm.activeTasks.filter { $0.isRunning }
        GroupBox("Active Operations") {
            if running.isEmpty {
                Text("No active operations")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(running) { task in
                        HStack {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 6))
                                .foregroundStyle(.blue)
                            Text(task.description)
                                .font(.subheadline)
                            Spacer()
                            if let elapsed = task.elapsed {
                                Text(formatElapsed(elapsed))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - 3. Source Library

    @ViewBuilder
    private var sourceLibrarySection: some View {
        if let lib = vm.libraryStats {
            GroupBox("Source Library") {
                VStack(spacing: 10) {
                    HStack(spacing: 20) {
                        StatCard(value: "\(lib.totalPlaylists)", label: "Playlists")
                        StatCard(value: "\(lib.totalFiles)", label: "Source Files")
                        StatCard(value: formatBytes(lib.totalSizeBytes), label: "Size")
                    }
                    if lib.totalFiles > 0 {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text("Exported")
                                    .font(.caption)
                                Spacer()
                                Text("\(lib.totalExported) / \(lib.totalFiles)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            ProgressView(value: Double(lib.totalExported), total: Double(lib.totalFiles))
                                .tint(.green)
                        }
                        if lib.totalUnconverted > 0 {
                            HStack {
                                Image(systemName: "exclamationmark.circle")
                                    .foregroundStyle(.yellow)
                                    .font(.caption)
                                Text("\(lib.totalUnconverted) unconverted")
                                    .font(.caption)
                                    .foregroundStyle(.yellow)
                                Spacer()
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - 4. Export Library Stats

    @ViewBuilder
    private var exportLibrarySection: some View {
        if let summary = vm.summary {
            GroupBox("Export Library") {
                HStack(spacing: 12) {
                    StatCard(value: "\(summary.totalFiles)", label: "Files")
                    StatCard(value: formatBytes(summary.totalSizeBytes), label: "Size")
                    StatCard(
                        value: tagIntegrityPercent(summary.tagIntegrity),
                        label: "Tags")
                    StatCard(
                        value: coverArtPercent(summary.coverArt),
                        label: "Cover Art")
                }
            }
        }
    }

    // MARK: - 5. Tag Integrity Breakdown

    @ViewBuilder
    private var tagIntegritySection: some View {
        if let summary = vm.summary, summary.tagIntegrity.checked > 0 {
            let ti = summary.tagIntegrity
            GroupBox("Tag Integrity") {
                VStack(spacing: 8) {
                    barRow(
                        label: "Protected",
                        count: ti.protected,
                        total: ti.checked,
                        color: .green)
                    barRow(
                        label: "Missing",
                        count: ti.missing,
                        total: ti.checked,
                        color: .red)
                }
            }
        }
    }

    // MARK: - 6. Cover Art Breakdown

    @ViewBuilder
    private var coverArtSection: some View {
        if let summary = vm.summary {
            let ca = summary.coverArt
            let total = ca.withArt + ca.withoutArt
            if total > 0 {
                GroupBox("Cover Art") {
                    VStack(spacing: 8) {
                        barRow(label: "With Art", count: ca.withArt, total: total, color: .green)
                        barRow(label: "Without Art", count: ca.withoutArt, total: total, color: .red)
                        if ca.withArt > 0 {
                            HStack {
                                Label("\(ca.original) original", systemImage: "photo")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Label("\(ca.resized) resized", systemImage: "arrow.down.right.and.arrow.up.left")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - 7. Freshness

    @ViewBuilder
    private var freshnessSection: some View {
        if let summary = vm.summary {
            let f = summary.freshness
            let total = f.current + f.recent + f.stale + f.outdated
            if total > 0 {
                GroupBox("Freshness") {
                    HStack(spacing: 12) {
                        freshnessPill(label: "Current", count: f.current, color: .green)
                        freshnessPill(label: "Recent", count: f.recent, color: .blue)
                        freshnessPill(label: "Stale", count: f.stale, color: .yellow)
                        freshnessPill(label: "Outdated", count: f.outdated, color: .red)
                    }
                }
            }
        }
    }

    // MARK: - 8. USB Sync Status

    @ViewBuilder
    private var usbSyncSection: some View {
        if !vm.usbSyncStatus.isEmpty {
            GroupBox("USB Sync Status") {
                VStack(spacing: 8) {
                    ForEach(vm.usbSyncStatus) { key in
                        NavigationLink(destination: SyncStatusView()) {
                            HStack {
                                Image(systemName: "externaldrive.connected.to.line.below")
                                    .foregroundStyle(.secondary)
                                Text(key.keyName)
                                    .font(.subheadline.weight(.medium))
                                Spacer()
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
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    // MARK: - 9. Playlists

    @ViewBuilder
    private var playlistsSection: some View {
        if let summary = vm.summary, !summary.playlists.isEmpty {
            GroupBox("Playlists") {
                VStack(spacing: 0) {
                    ForEach(summary.playlists) { playlist in
                        VStack(spacing: 6) {
                            HStack {
                                Text(playlist.name)
                                    .font(.subheadline.weight(.medium))
                                Spacer()
                                freshnessBadge(playlist.freshness)
                            }
                            HStack(spacing: 12) {
                                Label("\(playlist.fileCount)", systemImage: "music.note")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Label(formatBytes(playlist.sizeBytes), systemImage: "internaldrive")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                if playlist.tagsChecked > 0 {
                                    let pct = Int(Double(playlist.tagsProtected) / Double(playlist.tagsChecked) * 100)
                                    Text("Tags \(pct)%")
                                        .font(.caption)
                                        .foregroundStyle(pct == 100 ? .green : .yellow)
                                }
                                let artTotal = playlist.coverWith + playlist.coverWithout
                                if artTotal > 0 {
                                    let pct = Int(Double(playlist.coverWith) / Double(artTotal) * 100)
                                    Text("Art \(pct)%")
                                        .font(.caption)
                                        .foregroundStyle(pct == 100 ? .green : .yellow)
                                }
                            }
                        }
                        .padding(.vertical, 8)
                        if playlist.id != summary.playlists.last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func formatBytes(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    private func formatElapsed(_ seconds: Double) -> String {
        let mins = Int(seconds) / 60
        let secs = Int(seconds) % 60
        return mins > 0 ? "\(mins)m \(secs)s" : "\(secs)s"
    }

    private func tagIntegrityPercent(_ ti: TagIntegrityStats) -> String {
        guard ti.checked > 0 else { return "N/A" }
        return "\(Int(Double(ti.protected) / Double(ti.checked) * 100))%"
    }

    private func coverArtPercent(_ ca: CoverArtStats) -> String {
        let total = ca.withArt + ca.withoutArt
        guard total > 0 else { return "N/A" }
        return "\(Int(Double(ca.withArt) / Double(total) * 100))%"
    }

    private func barRow(label: String, count: Int, total: Int, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                    .font(.caption)
                Spacer()
                Text("\(count) / \(total)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ProgressView(value: Double(count), total: Double(max(total, 1)))
                .tint(color)
        }
    }

    private func freshnessPill(label: String, count: Int, color: Color) -> some View {
        VStack(spacing: 4) {
            Text("\(count)")
                .font(.title3.bold())
                .foregroundStyle(count > 0 ? color : .secondary)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func freshnessBadge(_ level: String) -> some View {
        let color: Color = switch level {
        case "current": .green
        case "recent": .blue
        case "stale": .yellow
        case "outdated": .red
        default: .secondary
        }
        return StatusBadge(text: level.capitalized, color: color)
    }
}

struct StatCard: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2.bold())
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
