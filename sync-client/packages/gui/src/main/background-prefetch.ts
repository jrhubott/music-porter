import { BrowserWindow } from 'electron';
import {
  APIClient,
  CacheManager,
  ConfigStore,
  MetadataCache,
  PrefetchEngine,
  BACKGROUND_PREFETCH_INTERVAL_MS,
  getConfigDir,
} from '@mporter/core';
import type { BackgroundPrefetchStatus, PrefetchResult, SyncProgress } from '@mporter/core';

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
  if (bytes >= BYTES_PER_KB) return `${(bytes / BYTES_PER_KB).toFixed(1)} KB`;
  return `${bytes} B`;
}

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
  private runType: 'periodic' | 'pin-change' | null = null;
  private activeAbort: AbortController | null = null;
  private pendingPinChange = false;
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

  /**
   * Trigger a prefetch in response to a pin/unpin change.
   * - If idle: starts a pin-change prefetch immediately.
   * - If a pin-change run is active: aborts it and starts a fresh one.
   * - If a periodic run is active: sets pendingPinChange so a pin-change run
   *   starts automatically after the periodic run completes.
   */
  triggerPinChange(): void {
    if (!this.running) {
      // Idle — start immediately
      this.runOnce('pin-change');
      return;
    }

    if (this.runType === 'pin-change') {
      // Abort the in-flight pin-change run; the cleanup in runOnce will
      // detect pendingPinChange and start a fresh run.
      this.pendingPinChange = true;
      this.activeAbort?.abort();
      return;
    }

    // Periodic run in progress — queue a pin-change run for after it finishes
    this.pendingPinChange = true;
  }

  /** Run a single prefetch cycle. Skips if already running, offline, or no pinned playlists. */
  async runOnce(type: 'periodic' | 'pin-change' = 'periodic'): Promise<PrefetchResult | null> {
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
    this.runType = type;
    this.activeAbort = new AbortController();
    this.updateStatus({ running: true });
    console.log('[prefetch] Starting %s prefetch cycle (profile: %s)', type, profile);

    const result = await this.executeRunOnce(profile);

    // Cleanup
    this.running = false;
    this.runType = null;
    this.activeAbort = null;

    // If a pin change arrived while we were running, start a fresh pin-change cycle
    if (this.pendingPinChange) {
      this.pendingPinChange = false;
      this.runOnce('pin-change');
    }

    return result;
  }

  /** Internal: execute the prefetch logic (separated for cleanup handling). */
  private async executeRunOnce(profile: string): Promise<PrefetchResult | null> {
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
        this.updateStatus({ running: false });
        return null;
      }

      // Step 2: Prefetch files
      const cacheManager = new CacheManager(getConfigDir(), profile);
      const metadataCache = new MetadataCache(getConfigDir(), profile);
      const engine = new PrefetchEngine(this.apiClient, cacheManager);
      const pinnedSet = new Set(pinned);

      const result = await engine.prefetch({
        playlists: pinned,
        profile,
        maxCacheBytes: this.configStore.preferences.maxCacheBytes,
        pinnedPlaylists: pinnedSet,
        metadataCache,
        signal: this.activeAbort!.signal,
        onProgress: (progress: SyncProgress) => {
          this.updateStatus({
            running: true,
            playlist: progress.playlist,
            progress: { current: progress.processed, total: progress.total },
          });
          // Also forward to renderer for real-time display
          this.sendToRenderer('cache:prefetchProgress', progress);
        },
        onLog: (_level, message) => {
          console.log('[prefetch] %s', message);
        },
      });

      this.status.lastRunAt = new Date().toISOString();
      this.status.lastResult = result;
      this.updateStatus({ running: false, lastRunAt: this.status.lastRunAt, lastResult: result });

      const totalSize = cacheManager.getTotalSize();
      const maxBytes = this.configStore.preferences.maxCacheBytes;
      console.log(
        '[prefetch] Complete — downloaded: %d, skipped: %d, capped: %d, failed: %d (%dms)',
        result.downloaded, result.skipped, result.capacityCapped, result.failed, result.durationMs,
      );
      const cachedPlaylists = cacheManager.getCachedPlaylists();
      let totalFiles = 0;
      for (const key of cachedPlaylists) {
        totalFiles += cacheManager.getCachedFileInfos(key).length;
      }
      console.log(
        '[prefetch] Cache: %s%s (%d files)',
        formatBytes(totalSize),
        maxBytes > 0 ? ` / ${formatBytes(maxBytes)}` : ' (unlimited)',
        totalFiles,
      );
      return result;
    } catch (err) {
      // Aborted runs are expected — don't log as errors
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('[prefetch] Run aborted (%s)', this.runType);
      } else {
        console.error('[prefetch] Error during prefetch cycle:', err);
      }
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
