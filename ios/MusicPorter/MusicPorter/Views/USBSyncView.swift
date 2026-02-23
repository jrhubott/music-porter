import SwiftUI

struct USBSyncView: View {
    @Environment(AppState.self) private var appState
    @State private var localPlaylists: [String] = []
    @State private var selectedPlaylists: Set<String> = []
    @State private var error: String?

    var body: some View {
        List {
            Section("Downloaded Playlists") {
                ForEach(localPlaylists, id: \.self) { name in
                    HStack {
                        Image(systemName: selectedPlaylists.contains(name) ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(selectedPlaylists.contains(name) ? .blue : .secondary)
                        Text(name)
                        Spacer()
                        let count = appState.downloadManager.localFiles(playlist: name).count
                        Text("\(count) files")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if selectedPlaylists.contains(name) {
                            selectedPlaylists.remove(name)
                        } else {
                            selectedPlaylists.insert(name)
                        }
                    }
                }
            }

            if !selectedPlaylists.isEmpty {
                Section {
                    Button {
                        // USB export requires UIKit presenter - simplified here
                        error = "USB export requires selecting a destination folder. Use the Share sheet on individual files."
                    } label: {
                        Label("Export to USB (\(selectedPlaylists.count) playlists)", systemImage: "externaldrive")
                    }
                }
            }

            if appState.usbExport.isExporting {
                Section {
                    ProgressView(value: appState.usbExport.exportProgress)
                    Text("Exporting...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let result = appState.usbExport.lastExportResult {
                Section {
                    Label(result.message, systemImage: result.success ? "checkmark.circle" : "xmark.circle")
                        .foregroundStyle(result.success ? .green : .red)
                }
            }

            if let error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("USB Export")
        .onAppear { scanLocalPlaylists() }
    }

    private func scanLocalPlaylists() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let base = docs.appendingPathComponent("MusicPorter")
        guard let contents = try? FileManager.default.contentsOfDirectory(
            at: base, includingPropertiesForKeys: nil, options: .skipsHiddenFiles) else { return }
        localPlaylists = contents
            .filter { $0.hasDirectoryPath }
            .map { $0.lastPathComponent }
            .sorted()
    }
}
