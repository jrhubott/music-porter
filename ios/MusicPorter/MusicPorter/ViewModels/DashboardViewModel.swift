import Foundation

@MainActor @Observable
final class DashboardViewModel {
    var status: ServerStatus?
    var summary: SummaryResponse?
    var libraryStats: LibraryStatsResponse?
    var activeTasks: [TaskInfo] = []
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
            status = try await s
            summary = try await sm
            libraryStats = try await ls
            activeTasks = (try? await ts) ?? []
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
