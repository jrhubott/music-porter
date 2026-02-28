import { BrowserWindow } from 'electron';
import {
  APIClient,
  CONNECTION_HEALTH_CHECK_INTERVAL_MS,
  CONNECTION_RECONNECT_INTERVAL_MS,
  HEALTH_CHECK_FAILURE_THRESHOLD,
  HEALTH_CHECK_TIMEOUT_MS,
} from '@mporter/core';
import type { ConnectionState } from '@mporter/core';

/** Callback that attempts to reconnect to the server and returns the new connection state. */
type ReconnectCallback = () => Promise<ConnectionState>;

/**
 * Monitors the server connection from the Electron main process.
 *
 * When connected: pings the server periodically. After consecutive failures
 * exceed the threshold, notifies the renderer to switch to offline mode and
 * begins automatic reconnection attempts.
 *
 * When in auto-offline mode: periodically calls the reconnect callback.
 * On success, notifies the renderer to go back online.
 *
 * When the user manually goes offline via "Go Offline": all timers stop.
 * No automatic reconnection is attempted until the user explicitly reconnects.
 */
export class ConnectionMonitor {
  private readonly apiClient: APIClient;
  private mainWindow: BrowserWindow | null = null;
  private reconnectCallback: ReconnectCallback | null = null;
  private healthCheckTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setInterval> | null = null;
  private consecutiveFailures = 0;

  constructor(apiClient: APIClient) {
    this.apiClient = apiClient;
  }

  /** Start monitoring with the given window and reconnect callback. */
  start(mainWindow: BrowserWindow, reconnectCallback: ReconnectCallback): void {
    this.mainWindow = mainWindow;
    this.reconnectCallback = reconnectCallback;
  }

  /** Called after a successful connection. Starts health-check polling. */
  notifyConnected(): void {
    this.stopAllTimers();
    this.consecutiveFailures = 0;
    this.startHealthCheck();
  }

  /**
   * Called when the user manually chooses "Go Offline".
   * Stops all timers — no reconnection attempts will be made.
   */
  notifyManualOffline(): void {
    this.stopAllTimers();
    this.consecutiveFailures = 0;
  }

  /**
   * Called on full disconnect (server config cleared).
   * Stops all timers completely.
   */
  notifyDisconnected(): void {
    this.stopAllTimers();
    this.consecutiveFailures = 0;
  }

  /** Stop all monitoring. */
  stop(): void {
    this.stopAllTimers();
  }

  private startHealthCheck(): void {
    this.stopAllTimers();
    this.healthCheckTimer = setInterval(
      () => this.performHealthCheck(),
      CONNECTION_HEALTH_CHECK_INTERVAL_MS,
    );
  }

  private startReconnect(): void {
    this.stopAllTimers();
    this.reconnectTimer = setInterval(
      () => this.attemptReconnect(),
      CONNECTION_RECONNECT_INTERVAL_MS,
    );
  }

  private stopAllTimers(): void {
    if (this.healthCheckTimer !== null) {
      clearInterval(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }
    if (this.reconnectTimer !== null) {
      clearInterval(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private async performHealthCheck(): Promise<void> {
    const ok = await this.apiClient.ping(HEALTH_CHECK_TIMEOUT_MS);
    if (ok) {
      this.consecutiveFailures = 0;
      return;
    }

    this.consecutiveFailures++;
    console.log(
      '[connection-monitor] Health check failed (%d/%d)',
      this.consecutiveFailures,
      HEALTH_CHECK_FAILURE_THRESHOLD,
    );

    if (this.consecutiveFailures >= HEALTH_CHECK_FAILURE_THRESHOLD) {
      console.log('[connection-monitor] Threshold reached — switching to offline mode');
      this.sendToRenderer('connection:statusChange', { offline: true });
      this.startReconnect();
    }
  }

  private async attemptReconnect(): Promise<void> {
    if (!this.reconnectCallback) return;

    try {
      const state = await this.reconnectCallback();
      if (state.connected) {
        console.log('[connection-monitor] Reconnected successfully');
        this.consecutiveFailures = 0;
        this.sendToRenderer('connection:statusChange', { offline: false, connection: state });
        this.startHealthCheck();
      }
    } catch {
      // Reconnect failed — will retry on next interval
    }
  }

  private sendToRenderer(channel: string, data: unknown): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, data);
    }
  }
}
