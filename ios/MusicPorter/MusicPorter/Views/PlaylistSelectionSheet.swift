import SwiftUI

/// Reusable sheet for selecting which playlists to include in a sync operation.
struct PlaylistSelectionSheet: View {
    let destName: String
    let allPlaylists: [String]
    let onSync: (Set<String>) -> Void

    @State private var selection: Set<String>
    @Environment(\.dismiss) private var dismiss

    init(destName: String, allPlaylists: [String], initialSelection: Set<String>, onSync: @escaping (Set<String>) -> Void) {
        self.destName = destName
        self.allPlaylists = allPlaylists
        self.onSync = onSync
        _selection = State(initialValue: initialSelection)
    }

    var body: some View {
        NavigationStack {
            List {
                if allPlaylists.isEmpty {
                    Text("No playlists available")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                } else {
                    Section {
                        ForEach(allPlaylists, id: \.self) { playlist in
                            HStack {
                                Image(systemName: selection.contains(playlist) ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(selection.contains(playlist) ? .blue : .secondary)
                                Text(playlist)
                                    .font(.subheadline)
                            }
                            .contentShape(Rectangle())
                            .onTapGesture {
                                if selection.contains(playlist) {
                                    selection.remove(playlist)
                                } else {
                                    selection.insert(playlist)
                                }
                            }
                        }
                    } header: {
                        HStack {
                            Text("Playlists")
                            Spacer()
                            Button("Select All") {
                                selection = Set(allPlaylists)
                            }
                            .font(.caption)
                            Text("·")
                                .foregroundStyle(.secondary)
                            Button("Clear") {
                                selection = []
                            }
                            .font(.caption)
                        }
                    }
                }
            }
            .navigationTitle("Sync to \(destName)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(syncButtonTitle) {
                        onSync(selection)
                    }
                    .bold()
                }
            }
        }
    }

    /// "Sync All" when nothing is selected (means all), otherwise shows count.
    private var syncButtonTitle: String {
        selection.isEmpty ? "Sync All" : "Sync \(selection.count)"
    }
}
