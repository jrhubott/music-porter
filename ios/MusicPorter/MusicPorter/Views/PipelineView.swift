import SwiftUI

struct PipelineView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = OperationViewModel()
    @State private var playlists: [Playlist] = []
    @State private var selectedPlaylist: Playlist?
    @State private var customURL = ""
    @State private var useAuto = false
    @State private var preset = "lossless"
    @State private var syncAfter = false
    @State private var destinations: [SyncDestination] = []
    @State private var selectedDestination: String?

    let presets = ["lossless", "high", "medium", "low"]

    var body: some View {
        NavigationStack {
            Form {
                if !vm.isRunning {
                    Section("Source") {
                        Toggle("Process all playlists", isOn: $useAuto)

                        if !useAuto {
                            Picker("Playlist", selection: $selectedPlaylist) {
                                Text("None").tag(nil as Playlist?)
                                ForEach(playlists) { p in
                                    Text(p.name).tag(p as Playlist?)
                                }
                            }

                            TextField("Or enter Apple Music URL", text: $customURL)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                                .keyboardType(.URL)
                        }
                    }

                    Section("Options") {
                        Picker("Quality Preset", selection: $preset) {
                            ForEach(presets, id: \.self) { Text($0) }
                        }
                        Toggle("Sync after processing", isOn: $syncAfter)
                        if syncAfter && !destinations.isEmpty {
                            Picker("Destination", selection: $selectedDestination) {
                                Text("Select...").tag(nil as String?)
                                ForEach(destinations) { dest in
                                    Text(dest.name).tag(dest.name as String?)
                                }
                            }
                        }
                    }

                    Section {
                        Button {
                            Task { await runPipeline() }
                        } label: {
                            HStack {
                                Spacer()
                                Label("Process", systemImage: "play.fill")
                                    .fontWeight(.semibold)
                                Spacer()
                            }
                        }
                        .disabled(!canRun)
                    }
                }

                if vm.isRunning || !vm.logMessages.isEmpty {
                    ProgressPanel(vm: vm)
                }
            }
            .navigationTitle("Process")
            .task { await loadData() }
        }
    }

    private var canRun: Bool {
        let hasSource = useAuto || selectedPlaylist != nil || !customURL.isEmpty
        if syncAfter && !destinations.isEmpty {
            return hasSource && selectedDestination != nil
        }
        return hasSource
    }

    private func loadData() async {
        async let p = appState.apiClient.getPlaylists()
        async let d = appState.apiClient.getSyncDestinations()
        playlists = (try? await p) ?? []
        let destResponse = try? await d
        destinations = destResponse?.destinations ?? []
    }

    private func runPipeline() async {
        let syncDest = syncAfter ? selectedDestination : nil
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.runPipeline(
                playlist: selectedPlaylist?.key,
                url: customURL.isEmpty ? nil : customURL,
                auto: useAuto,
                preset: preset,
                syncDestination: syncDest
            )
        }
    }
}
