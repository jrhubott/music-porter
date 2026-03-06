import SwiftUI

/// Sheet for confirming server-side data deletion with options.
struct DeleteServerDataSheet: View {
    let key: String
    @Binding var deleteSource: Bool
    @Binding var deleteExport: Bool
    @Binding var removeConfig: Bool
    let onConfirm: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Delete server data for \"\(key)\"?")
                        .font(.subheadline)
                }

                Section("Options") {
                    Toggle("Delete source files", isOn: $deleteSource)
                    Toggle("Delete exported files", isOn: $deleteExport)
                    Toggle("Remove from config", isOn: $removeConfig)
                }

                Section {
                    Button(role: .destructive) {
                        onConfirm()
                    } label: {
                        HStack {
                            Spacer()
                            Text("Delete")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .disabled(!deleteSource && !deleteExport && !removeConfig)
                }
            }
            .navigationTitle("Delete Server Data")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
