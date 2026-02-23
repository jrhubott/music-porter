import Foundation
import Network

/// Discovers music-porter servers on the local network via Bonjour/mDNS.
@Observable
final class ServerDiscovery {
    var discoveredServers: [ServerConnection] = []
    var isSearching = false

    private var browser: NWBrowser?

    func startSearch() {
        isSearching = true
        discoveredServers = []

        let params = NWParameters()
        params.includePeerToPeer = true
        browser = NWBrowser(for: .bonjour(type: "_music-porter._tcp", domain: nil), using: params)

        browser?.browseResultsChangedHandler = { [weak self] results, _ in
            Task { @MainActor in
                self?.handleResults(results)
            }
        }

        browser?.stateUpdateHandler = { [weak self] state in
            if case .failed = state {
                Task { @MainActor in
                    self?.isSearching = false
                }
            }
        }

        browser?.start(queue: .main)

        // Auto-stop after 10 seconds
        Task {
            try? await Task.sleep(for: .seconds(10))
            await MainActor.run { self.stopSearch() }
        }
    }

    func stopSearch() {
        browser?.cancel()
        browser = nil
        isSearching = false
    }

    @MainActor
    private func handleResults(_ results: Set<NWBrowser.Result>) {
        for result in results {
            if case .service(let name, _, _, _) = result.endpoint {
                // Resolve the service to get host and port
                resolveService(result: result, name: name)
            }
        }
    }

    private func resolveService(result: NWBrowser.Result, name: String) {
        let connection = NWConnection(to: result.endpoint, using: .tcp)
        connection.stateUpdateHandler = { [weak self] state in
            if case .ready = state {
                if let endpoint = connection.currentPath?.remoteEndpoint,
                   case .hostPort(let host, let port) = endpoint {
                    let hostStr: String
                    switch host {
                    case .ipv4(let addr):
                        hostStr = "\(addr)"
                    case .ipv6(let addr):
                        hostStr = "\(addr)"
                    case .name(let hostname, _):
                        hostStr = hostname
                    @unknown default:
                        hostStr = "unknown"
                    }
                    let server = ServerConnection(
                        host: hostStr,
                        port: Int(port.rawValue),
                        name: name
                    )
                    Task { @MainActor in
                        if self?.discoveredServers.contains(where: { $0.id == server.id }) == false {
                            self?.discoveredServers.append(server)
                        }
                    }
                }
                connection.cancel()
            }
        }
        connection.start(queue: .global())
    }
}
