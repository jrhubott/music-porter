import Foundation
import Network

/// Discovers music-porter servers on the local network via Bonjour/mDNS.
@MainActor @Observable
final class ServerDiscovery {
    var discoveredServers: [ServerConnection] = []
    var isSearching = false

    @ObservationIgnored private var browser: NWBrowser?

    func startSearch() {
        isSearching = true
        discoveredServers = []

        let params = NWParameters()
        params.includePeerToPeer = true
        let newBrowser = NWBrowser(for: .bonjour(type: "_music-porter._tcp", domain: nil), using: params)

        newBrowser.browseResultsChangedHandler = { [weak self] results, _ in
            for result in results {
                self?.resolveEndpoint(result)
            }
        }

        newBrowser.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed, .cancelled:
                Task { @MainActor in self?.isSearching = false }
            default:
                break
            }
        }

        newBrowser.start(queue: .global())
        browser = newBrowser

        // Auto-stop after 10 seconds
        Task {
            try? await Task.sleep(for: .seconds(10))
            stopSearch()
        }
    }

    func stopSearch() {
        browser?.cancel()
        browser = nil
        isSearching = false
    }

    private nonisolated func resolveEndpoint(_ result: NWBrowser.Result) {
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

    private nonisolated func extractAddress(from endpoint: NWEndpoint, name: String) {
        guard case .hostPort(let host, let port) = endpoint else { return }

        var hostStr: String
        switch host {
        case .ipv4(let addr):
            hostStr = "\(addr)"
        case .ipv6(let addr):
            let str = "\(addr)"
            // IPv4-mapped IPv6 (::ffff:192.168.1.x) — extract the real IPv4
            if str.hasPrefix("::ffff:") {
                hostStr = String(str.dropFirst(7))
            } else {
                // Skip all other IPv6 addresses (link-local, ULA, etc.)
                return
            }
        case .name(let hostname, _):
            hostStr = hostname
        @unknown default:
            return
        }

        // Strip interface scope ID (e.g. %bridge101, %en0) — not valid in URLs
        if let percentIndex = hostStr.firstIndex(of: "%") {
            hostStr = String(hostStr[..<percentIndex])
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
