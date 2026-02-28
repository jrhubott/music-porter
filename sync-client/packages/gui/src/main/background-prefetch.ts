import { BrowserWindow } from 'electron';
import {
  APIClient,
  CacheManager,
  ConfigStore,
  PrefetchEngine,
  BACKGROUND_PREFETCH_INTERVAL_MS,
  getConfigDir,
} from '@mporter/core';
import type { BackgroundPrefetchStatus, PrefetchResult, SyncProgress } from '@mporter/core';

/**
 * Background prefetch service — runs on a timer in the Electron main process.
 * Automatically discovers new playlists, auto-pins them (when enabled), and
 * downloads missing/stale files to the local cache.
 */
export class BackgroundPrefetchService {
  private readonly apiClient: APIClient;
  private readonly configStore: ConfigStore;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private running = false;
  private status: BackgroundPrefetchStatus = { running: false };
  private mainWindow: BrowserWindow | null = null;

  constructor(apiClient: APIClient, configStore: ConfigStore) {
    this.apiClient = apiClient;
    this.configStore = configStore;
  }

  /** Start the background prefetch interval timer. Does NOT run immediately — call notifyConnected() after connection. */
  start(mainWindow: BrowserWindow): void {
    this.mainWindow = mainWindow;
    this.intervalId = setInterval(() => this.runOnce(), BACKGROUND_PREFETCH_INTERVAL_MS);
  }

  /** Called after the API client connects to the server. Triggers the first prefetch cycle. */
  notifyConnected(): void {
    console.log('[prefetch] notifyConnected — triggering first prefetch cycle');
    this.runOnce();
  }

  /** Stop the background prefetch interval. */
  stop(): void {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  /** Get the current prefetch status. */
  getStatus(): BackgroundPrefetchStatus {
    return { ...this.status };
  }

  /** Run a single prefetch cycle. Skips if already running, offline, or no pinned playlists. */
  async runOnce(): Promise<PrefetchResult | null> {
    if (this.running) {
      console.log('[prefetch] Skipped — already running');
      return null;
    }

    // Check if connected
    const connState = this.apiClient.connectionState;
    if (!connState.connected) {
      console.log('[prefetch] Skipped — not connected to server');
      return null;
    }

    const profile = this.configStore.profile;
    if (!profile) {
      console.log('[prefetch] Skipped — no output profile configured');
      return null;
    }

    this.running = true;
    this.updateStatus({ running: true });
    console.log('[prefetch] Starting prefetch cycle (profile: %s)', profile);

    try {
      // Step 1: Discover and auto-pin new playlists
      if (this.configStore.autoPinNewPlaylists) {
        try {
          const playlists = await this.apiClient.getPlaylists();
          const serverKeys = playlists.map((p) => p.key);
          this.configStore.syncPinsWithServer(serverKeys);
        } catch {
          // Non-critical — continue with existing pins
        }
      }

      const pinned = this.configStore.preferences.pinnedPlaylists;
      if (pinned.length === 0) {
        console.log('[prefetch] Skipped — no pinned playlists');
        this.running = false;
        this.updateStatus({ running: false });
        return null;
      }

      // Step 2: Prefetch files
      const cacheManager = new CacheManager(getConfigDir(), profile);
      const engine = new PrefetchEngine(this.apiClient, cacheManager);

      const result = await engine.prefetch({
        playlists: pinned,
        profile,
        maxCacheBytes: this.configStore.preferences.maxCacheBytes,
        onProgress: (progress: SyncProgress) => {
          this.updateStatus({
            running: true,
            playlist: progress.playlist,
            progress: { current: progress.processed, total: progress.total },
          });
          // Also forward to renderer for real-time display
          this.sendToRenderer('cache:prefetchProgress', progress);
        },
        onLog: () => {
          // Suppress background prefetch logs
        },
      });

      this.status.lastRunAt = new Date().toISOString();
      this.status.lastResult = result;
      this.running = false;
      this.updateStatus({ running: false, lastRunAt: this.status.lastRunAt, lastResult: result });
      console.log(
        '[prefetch] Complete — downloaded: %d, skipped: %d, failed: %d (%dms)',
        result.downloaded, result.skipped, result.failed, result.durationMs,
      );
      return result;
    } catch (err) {
      console.error('[prefetch] Error during prefetch cycle:', err);
      this.running = false;
      this.updateStatus({ running: false });
      return null;
    }
  }

  private updateStatus(partial: Partial<BackgroundPrefetchStatus>): void {
    this.status = { ...this.status, ...partial };
    this.sendToRenderer('cache:backgroundPrefetchStatus', this.status);
  }

  private sendToRenderer(channel: string, data: unknown): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, data);
    }
  }
}
