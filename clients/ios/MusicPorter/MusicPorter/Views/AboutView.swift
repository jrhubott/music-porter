import SwiftUI

/// Parsed release version with header and bullet points.
private struct ReleaseVersion: Identifiable {
    let id = UUID()
    let header: String
    let bullets: [String]
}

/// Pattern matching the "Version X.Y.Z (YYYY-MM-DD):" header lines.
private let versionHeaderPattern = /^Version\s+(.+):$/

struct AboutView: View {
    @Environment(AppState.self) private var appState
    @State private var aboutResponse: AboutResponse?
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        List {
            Section("Version") {
                LabeledContent("App Version", value: MusicPorterApp.appVersion)
                if let serverVersion = aboutResponse?.version {
                    LabeledContent("Server Version", value: serverVersion)
                } else if let server = appState.currentServer, let version = server.version {
                    LabeledContent("Server Version", value: version)
                }
            }

            Section("Release Notes") {
                if isLoading {
                    HStack {
                        Spacer()
                        ProgressView("Loading release notes...")
                        Spacer()
                    }
                } else if let error {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                } else if versions.isEmpty {
                    Text("No release notes available.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(Array(versions.enumerated()), id: \.element.id) { index, version in
                        DisclosureGroup(version.header, isExpanded: expandedBinding(for: index)) {
                            ForEach(version.bullets, id: \.self) { bullet in
                                Text(bullet)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .font(.subheadline.weight(.medium))
                        .tint(.cyan)
                    }
                }
            }
        }
        .navigationTitle("Release Notes")
        .task { await fetchAbout() }
        .refreshable { await fetchAbout() }
    }

    // MARK: - Data

    private var versions: [ReleaseVersion] {
        guard let notes = aboutResponse?.releaseNotes else { return [] }
        return Self.parseReleaseNotes(notes)
    }

    @State private var expandedStates: [Int: Bool] = [:]

    private func expandedBinding(for index: Int) -> Binding<Bool> {
        Binding(
            get: { expandedStates[index] ?? (index == 0) },
            set: { expandedStates[index] = $0 }
        )
    }

    private func fetchAbout() async {
        isLoading = true
        error = nil
        do {
            aboutResponse = try await appState.apiClient.getAbout()
        } catch {
            self.error = "Failed to load release notes."
        }
        isLoading = false
    }

    // MARK: - Parsing

    /// Parse release notes text into structured versions, matching the web dashboard logic.
    private static func parseReleaseNotes(_ text: String) -> [ReleaseVersion] {
        let lines = text.components(separatedBy: "\n")
        var versions: [ReleaseVersion] = []
        var currentHeader: String?
        var currentBullets: [String] = []

        for line in lines {
            if let match = line.wholeMatch(of: versionHeaderPattern) {
                // Save previous version if any
                if let header = currentHeader {
                    versions.append(ReleaseVersion(header: header, bullets: currentBullets))
                }
                currentHeader = String(match.1)
                currentBullets = []
            } else if line.hasPrefix("\u{2022} ") {
                currentBullets.append(String(line.dropFirst(2)))
            } else if !line.trimmingCharacters(in: .whitespaces).isEmpty {
                currentBullets.append(line)
            }
        }

        // Save last version
        if let header = currentHeader {
            versions.append(ReleaseVersion(header: header, bullets: currentBullets))
        }

        return versions
    }
}
