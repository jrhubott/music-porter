import SwiftUI

struct PipelineView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = OperationViewModel()
    @State private var playlists: [Playlist] = []
    @State private var selectedPlaylist: Playlist?
    @State private var customURL = ""
    @State private var useAuto = false
    @State private var preset = "lossless"
    @State private var copyToUsb = false

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
                        Toggle("Copy to USB after", isOn: $copyToUsb)
                    }

                    Section {
                        Button {
                            Task { await runPipeline() }
                        } label: {
                            HStack {
                                Spacer()
                                Label("Run Pipeline", systemImage: "play.fill")
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
            .navigationTitle("Pipeline")
            .task { await loadPlaylists() }
        }
    }

    private var canRun: Bool {
        useAuto || selectedPlaylist != nil || !customURL.isEmpty
    }

    private func loadPlaylists() async {
        playlists = (try? await appState.apiClient.getPlaylists()) ?? []
    }

    private func runPipeline() async {
        await vm.run(api: appState.apiClient) {
            try await appState.apiClient.runPipeline(
                playlist: selectedPlaylist?.key,
                url: customURL.isEmpty ? nil : customURL,
                auto: useAuto,
                preset: preset,
                copyToUsb: copyToUsb
            )
        }
    }
}
