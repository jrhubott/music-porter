import Foundation

@MainActor @Observable
final class DashboardViewModel {
    var status: ServerStatus?
    var summary: SummaryResponse?
    var libraryStats: LibraryStatsResponse?
    var activeTasks: [TaskInfo] = []
    var syncStatus: [SyncStatusSummary] = []
    var usbDestNames: Set<String> = []
    var isLoading = false
    var error: String?

    func load(api: APIClient) async {
        isLoading = true
        error = nil
        do {
            async let s = api.getStatus()
            async let sm = api.getSummary()
            async let ls = api.getLibraryStats()
            async let ts = api.getTasks()
            async let us = api.getSyncStatus()
            async let ds = api.getSyncDestinations()
            status = try await s
            summary = try await sm
            libraryStats = try await ls
            activeTasks = (try? await ts) ?? []
            syncStatus = (try? await us) ?? []
            let destResponse = try? await ds
            usbDestNames = Set((destResponse?.destinations ?? []).filter { $0.type == "usb" }.map { $0.name })
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
