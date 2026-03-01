import Foundation
import os

/// Monitors server connection health and manages automatic offline transitions.
///
/// When connected, periodically pings the server. After consecutive failures,
/// transitions to offline mode and begins reconnection attempts.
/// Manual offline (user-initiated) disables auto-reconnect.
@MainActor @Observable
final class ConnectionMonitor {
    // MARK: - Private State

    private weak var appState: AppState?
    @ObservationIgnored private var healthCheckTimer: Timer?
    @ObservationIgnored private var reconnectTimer: Timer?
    @ObservationIgnored private var consecutiveFailures = 0
    @ObservationIgnored private var isManualOffline = false
    @ObservationIgnored private let logger = Logger(subsystem: "com.musicporter", category: "ConnectionMonitor")

    // MARK: - Init

    init(appState: AppState) {
        self.appState = appState
    }

    // MARK: - Lifecycle

    /// Called after a successful connection. Starts health check timer.
    func notifyConnected() {
        stopAllTimers()
        consecutiveFailures = 0
        isManualOffline = false
        startHealthCheckTimer()
        logger.info("Connection monitor started (health check every \(ConnectionConstants.healthCheckIntervalSeconds)s)")
    }

    /// Called when the user manually goes offline (Go Offline button or Use Offline from ReconnectingView).
    /// Stops all timers — no auto-reconnect.
    func notifyManualOffline() {
        stopAllTimers()
        consecutiveFailures = 0
        isManualOffline = true
        logger.info("Manual offline — auto-reconnect disabled")
    }

    /// Called on explicit disconnect. Stops everything.
    func notifyDisconnected() {
        stopAllTimers()
        consecutiveFailures = 0
        isManualOffline = false
        logger.info("Connection monitor stopped (disconnected)")
    }

    // MARK: - Health Check

    private func startHealthCheckTimer() {
        healthCheckTimer?.invalidate()
        healthCheckTimer = Timer.scheduledTimer(
            withTimeInterval: ConnectionConstants.healthCheckIntervalSeconds,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.performHealthCheck()
            }
        }
    }

    private func performHealthCheck() async {
        guard let appState, appState.apiClient.isConnected else { return }

        let success = await appState.apiClient.ping(
            timeoutSeconds: ConnectionConstants.healthCheckTimeoutSeconds
        )

        if success {
            consecutiveFailures = 0
        } else {
            consecutiveFailures += 1
            logger.warning("Health check failed (\(self.consecutiveFailures)/\(ConnectionConstants.healthCheckFailureThreshold))")

            if consecutiveFailures >= ConnectionConstants.healthCheckFailureThreshold {
                await transitionToOffline()
            }
        }
    }

    // MARK: - Offline Transition

    private func transitionToOffline() async {
        guard let appState else { return }
        logger.warning("Server unreachable — transitioning to offline mode")

        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        consecutiveFailures = 0

        // Set disconnected state so views stop making server calls
        appState.apiClient.isConnected = false
        appState.backgroundPrefetchService?.stop()

        // Enter offline mode if cache is available
        await appState.checkAndEnterOfflineMode()

        // Start auto-reconnect (not manual offline)
        startReconnectTimer()
    }

    // MARK: - Reconnect

    private func startReconnectTimer() {
        reconnectTimer?.invalidate()
        reconnectTimer = Timer.scheduledTimer(
            withTimeInterval: ConnectionConstants.reconnectIntervalSeconds,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.attemptReconnect()
            }
        }
        logger.info("Auto-reconnect started (every \(ConnectionConstants.reconnectIntervalSeconds)s)")
    }

    private func attemptReconnect() async {
        guard let appState else { return }
        guard let server = appState.savedServer,
              let apiKey = KeychainService.load() else { return }

        logger.info("Attempting reconnection...")

        do {
            try await appState.connect(server: server, apiKey: apiKey)
            // connect() calls notifyConnected() via AppState wiring,
            // which stops reconnect timer and starts health checks
            appState.isOfflineMode = false
            logger.info("Reconnected successfully")
        } catch {
            logger.info("Reconnection failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Helpers

    private func stopAllTimers() {
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        reconnectTimer?.invalidate()
        reconnectTimer = nil
    }
}
