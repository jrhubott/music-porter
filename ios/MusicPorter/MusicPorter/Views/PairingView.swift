import SwiftUI

/// API key entry and validation for server pairing.
struct PairingView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss

    let server: ServerConnection
    @State private var apiKey = ""
    @State private var isValidating = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Image(systemName: "desktopcomputer")
                            .font(.title2)
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

                Section("API Key") {
                    SecureField("Enter API key", text: $apiKey)
                        .textContentType(.password)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)

                    Text("Find the API key in the server startup output or web dashboard.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        Task { await pair() }
                    } label: {
                        HStack {
                            Spacer()
                            if isValidating {
                                ProgressView()
                            } else {
                                Text("Connect")
                                    .fontWeight(.semibold)
                            }
                            Spacer()
                        }
                    }
                    .disabled(apiKey.isEmpty || isValidating)
                }
            }
            .navigationTitle("Pair Server")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func pair() async {
        isValidating = true
        error = nil
        do {
            try await appState.connect(server: server, apiKey: apiKey)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        isValidating = false
    }
}
