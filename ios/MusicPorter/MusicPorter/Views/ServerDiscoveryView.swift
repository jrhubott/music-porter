import SwiftUI

/// Server discovery and manual connection entry.
struct ServerDiscoveryView: View {
    @Environment(AppState.self) private var appState
    @State private var manualHost = ""
    @State private var manualPort = "5555"
    @State private var showPairing = false
    @State private var selectedServer: ServerConnection?

    var body: some View {
        NavigationStack {
            List {
                Section("Discovered Servers") {
                    if appState.discovery.isSearching {
                        HStack {
                            ProgressView()
                            Text("Searching network...")
                                .foregroundStyle(.secondary)
                        }
                    }

                    if appState.discovery.discoveredServers.isEmpty && !appState.discovery.isSearching {
                        Text("No servers found")
                            .foregroundStyle(.secondary)
                    }

                    ForEach(appState.discovery.discoveredServers) { server in
                        Button {
                            selectedServer = server
                            showPairing = true
                        } label: {
                            HStack {
                                Image(systemName: "desktopcomputer")
                                    .foregroundStyle(.blue)
                                VStack(alignment: .leading) {
                                    Text(server.name)
                                        .font(.headline)
                                    Text("\(server.host):\(server.port)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                Section("Manual Connection") {
                    TextField("Server Address", text: $manualHost)
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)

                    TextField("Port", text: $manualPort)
                        .keyboardType(.numberPad)

                    Button("Connect") {
                        let port = Int(manualPort) ?? 5555
                        selectedServer = ServerConnection(
                            host: manualHost, port: port, name: manualHost)
                        showPairing = true
                    }
                    .disabled(manualHost.isEmpty)
                }
            }
            .navigationTitle("Music Porter")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        appState.discovery.startSearch()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .sheet(isPresented: $showPairing) {
                if let server = selectedServer {
                    PairingView(server: server)
                }
            }
            .onAppear {
                appState.discovery.startSearch()
            }
        }
    }
}
