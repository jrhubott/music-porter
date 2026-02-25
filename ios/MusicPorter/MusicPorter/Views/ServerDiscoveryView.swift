import SwiftUI

/// Server discovery and manual connection entry.
struct ServerDiscoveryView: View {
    @Environment(AppState.self) private var appState
    @State private var manualHost = ""
    @State private var manualPort = "5555"
    @State private var selectedServer: ServerConnection?
    @State private var showScanner = false
    @State private var scanError: String?
    @State private var isConnectingFromScan = false
    @State private var scannedApiKey: String?
    @FocusState private var isManualFieldFocused: Bool

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

                Section("Scan QR Code") {
                    if isConnectingFromScan {
                        HStack {
                            ProgressView()
                            Text("Connecting...")
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Button {
                            scanError = nil
                            showScanner = true
                        } label: {
                            HStack {
                                Image(systemName: "qrcode.viewfinder")
                                    .font(.title2)
                                    .foregroundStyle(.blue)
                                VStack(alignment: .leading) {
                                    Text("Scan QR Code")
                                        .font(.headline)
                                    Text("Scan the QR code from the server or web dashboard")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if let scanError {
                        Label(scanError, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }

                Section("Manual Connection") {
                    TextField("Server Address", text: $manualHost)
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .focused($isManualFieldFocused)

                    TextField("Port", text: $manualPort)
                        .keyboardType(.numberPad)
                        .focused($isManualFieldFocused)

                    Button("Connect") {
                        isManualFieldFocused = false
                        let host = manualHost.trimmingCharacters(in: .whitespaces)
                        let port = Int(manualPort) ?? 5555
                        selectedServer = ServerConnection(
                            host: host, port: port, name: host)
                    }
                    .disabled(manualHost.trimmingCharacters(in: .whitespaces).isEmpty)
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
            .sheet(item: $selectedServer) { server in
                PairingView(server: server, initialApiKey: scannedApiKey)
            }
            .onChange(of: selectedServer) {
                if selectedServer == nil {
                    scannedApiKey = nil
                }
            }
            .fullScreenCover(isPresented: $showScanner) {
                QRScannerView(
                    onScan: { payload in
                        showScanner = false
                        connectFromScan(payload)
                    },
                    onError: { error in
                        showScanner = false
                        scanError = error
                    },
                    onCancel: {
                        showScanner = false
                    }
                )
                .ignoresSafeArea()
            }
            .onAppear {
                appState.discovery.startSearch()
            }
        }
    }

    private func connectFromScan(_ payload: QRPairingPayload) {
        isConnectingFromScan = true
        scanError = nil
        let server = ServerConnection(
            host: payload.host, port: payload.port, name: payload.host,
            url: payload.url)
        Task {
            // Try 1: connect using full QR payload (may use external URL)
            do {
                try await appState.connect(server: server, apiKey: payload.key)
                isConnectingFromScan = false
                return
            } catch {}

            // Try 2: if payload had a URL, retry with direct host:port only
            if payload.url != nil {
                let directServer = ServerConnection(
                    host: payload.host, port: payload.port, name: payload.host)
                do {
                    try await appState.connect(server: directServer, apiKey: payload.key)
                    isConnectingFromScan = false
                    return
                } catch {}
            }

            // Fallback: open PairingView with pre-filled API key
            isConnectingFromScan = false
            scannedApiKey = payload.key
            selectedServer = ServerConnection(
                host: payload.host, port: payload.port, name: payload.host)
        }
    }
}
