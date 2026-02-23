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
            guard let self else { return }
            for result in results {
                self.resolveEndpoint(result)
            }
        }

        browser?.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed, .cancelled:
                Task { @MainActor in self?.isSearching = false }
            default:
                break
            }
        }

        browser?.start(queue: .global())

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

    private func resolveEndpoint(_ result: NWBrowser.Result) {
        // Extract the service name from the result
        let serviceName: String
        if case .service(let name, _, _, _) = result.endpoint {
            serviceName = name
        } else {
            return
        }

        // Create a TCP connection to resolve the Bonjour endpoint to IP + port
        let connection = NWConnection(to: result.endpoint, using: .tcp)
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                if let innerEndpoint = connection.currentPath?.remoteEndpoint {
                    self?.extractAddress(from: innerEndpoint, name: serviceName)
                }
                connection.cancel()
            case .failed, .cancelled:
                connection.cancel()
            default:
                break
            }
        }
        connection.start(queue: .global())

        // Timeout: cancel if not resolved within 5 seconds
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
            if connection.state != .cancelled {
                connection.cancel()
            }
        }
    }

    private func extractAddress(from endpoint: NWEndpoint, name: String) {
        guard case .hostPort(let host, let port) = endpoint else { return }

        let hostStr: String
        switch host {
        case .ipv4(let addr):
            hostStr = "\(addr)"
        case .ipv6(let addr):
            // Skip link-local IPv6 — prefer IPv4
            let str = "\(addr)"
            if str.hasPrefix("fe80") { return }
            hostStr = str
        case .name(let hostname, _):
            hostStr = hostname
        @unknown default:
            return
        }

        let server = ServerConnection(
            host: hostStr,
            port: Int(port.rawValue),
            name: name
        )

        Task { @MainActor [weak self] in
            guard let self else { return }
            if !self.discoveredServers.contains(where: { $0.id == server.id }) {
                self.discoveredServers.append(server)
            }
        }
    }
}
