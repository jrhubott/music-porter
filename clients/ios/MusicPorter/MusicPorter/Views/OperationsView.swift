import SwiftUI

struct OperationsView: View {
    @Environment(AppState.self) private var appState
    @State private var tasks: [TaskInfo] = []
    @State private var isLoading = false

    var body: some View {
        List {
            if isLoading {
                ProgressView()
            }
            ForEach(tasks) { task in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(task.operation)
                            .font(.headline)
                        Spacer()
                        StatusBadge(
                            text: task.status,
                            color: statusColor(task.status))
                    }
                    Text(task.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let elapsed = task.elapsed {
                        Text(String(format: "%.1fs", elapsed))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Operations")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        tasks = (try? await appState.apiClient.getTasks()) ?? []
        isLoading = false
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        case "cancelled": return .orange
        default: return .gray
        }
    }
}
