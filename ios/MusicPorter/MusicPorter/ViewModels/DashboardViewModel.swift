import Foundation

@Observable
final class DashboardViewModel {
    var status: ServerStatus?
    var summary: SummaryResponse?
    var isLoading = false
    var error: String?

    func load(api: APIClient) async {
        isLoading = true
        error = nil
        do {
            async let s = api.getStatus()
            async let sm = api.getSummary()
            status = try await s
            summary = try await sm
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
