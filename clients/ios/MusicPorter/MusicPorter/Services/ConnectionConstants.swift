import Foundation

/// Constants for connection health monitoring.
/// Values match the sync client's connection-monitor.ts.
enum ConnectionConstants {
    /// Interval between health check pings when connected (seconds).
    static let healthCheckIntervalSeconds: TimeInterval = 30

    /// Interval between reconnection attempts when auto-offline (seconds).
    static let reconnectIntervalSeconds: TimeInterval = 15

    /// Timeout for each health check ping (seconds).
    static let healthCheckTimeoutSeconds = 5

    /// Consecutive health check failures before transitioning to offline.
    static let healthCheckFailureThreshold = 2
}
