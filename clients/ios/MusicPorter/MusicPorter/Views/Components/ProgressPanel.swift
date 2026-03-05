import SwiftUI

/// Reusable progress panel for operations with SSE streaming.
struct ProgressPanel: View {
    let vm: OperationViewModel

    var body: some View {
        Section("Progress") {
            if vm.isRunning {
                VStack(alignment: .leading, spacing: 8) {
                    ProgressView(value: vm.progress) {
                        HStack {
                            Text(vm.progressStage)
                                .font(.caption)
                            Spacer()
                            Text("\(Int(vm.progress * 100))%")
                                .font(.caption.monospacedDigit())
                        }
                    }
                }
            }

            if let error = vm.error {
                Label(error, systemImage: "xmark.circle")
                    .foregroundStyle(.red)
            }

            if vm.status == "completed" {
                Label("Completed", systemImage: "checkmark.circle")
                    .foregroundStyle(.green)
            }
        }

        if !vm.logMessages.isEmpty {
            Section("Log") {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(vm.logMessages) { entry in
                            Text(entry.message)
                                .font(.caption.monospaced())
                                .foregroundStyle(logColor(entry.level))
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
        }
    }

    private func logColor(_ level: String) -> Color {
        switch level {
        case "ERROR": return .red
        case "WARN": return .orange
        case "OK": return .green
        case "SKIP": return .yellow
        default: return .primary
        }
    }
}
