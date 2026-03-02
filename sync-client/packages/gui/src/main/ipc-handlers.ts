import { ipcMain, dialog, safeStorage, BrowserWindow } from 'electron';
import { statfsSync } from 'node:fs';
import {
  APIClient,
  CacheManager,
  ConfigStore,
  MetadataCache,
  PrefetchEngine,
  SyncEngine,
  DriveManager,
  ServerDiscovery,
  VERSION,
  getConfigDir,
  readManifest,
} from '@mporter/core';
import type {
  BackgroundPrefetchStatus,
  ConnectionState,
  CookieStatus,
  CookieUploadResponse,
  DiscoveredServer,
  DriveInfo,
  OkResponse,
  PipelineProgress,
  PipelineStartResult,
  PlaylistCacheStatus,
  PrefetchResult,
  ServerConfig,
  SyncPreferences,
  SyncProgress,
  SyncResult,
} from '@mporter/core';
import { openCookieRefreshWindow, cancelCookieRefresh } from './cookie-refresh.js';
import type { BackgroundPrefetchService } from './background-prefetch.js';
import type { ConnectionMonitor } from './connection-monitor.js';

/** Result returned to renderer from the cookies:refresh handler. */
interface CookieRefreshIPCResult {
  success: boolean;
  valid?: boolean;
  reason?: string;
  days_remaining?: number | null;
  error?: string;
}

export const configStore = new ConfigStore();
export const apiClient = new APIClient();
const driveManager = new DriveManager();
let activeSyncAbort: AbortController | null = null;
let activePrefetchAbort: AbortController | null = null;
let activePipelineAbort: AbortController | null = null;
let bgPrefetchService: BackgroundPrefetchService | null = null;
let connectionMonitor: ConnectionMonitor | null = null;

/** Set the background prefetch service reference for IPC handlers. */
export function setBackgroundPrefetchService(service: BackgroundPrefetchService): void {
  bgPrefetchService = service;
}

/** Set the connection monitor reference for IPC handlers. */
export function setConnectionMonitor(monitor: ConnectionMonitor): void {
  connectionMonitor = monitor;
}

/** Get a CacheManager for the current profile, or null if no profile set. */
function getCacheManager(): CacheManager | null {
  const profile = configStore.profile;
  if (!profile) return null;
  return new CacheManager(getConfigDir(), profile);
}

/** Get a MetadataCache for the current profile, or null if no profile set. */
function getMetadataCache(): MetadataCache | null {
  const profile = configStore.profile;
  if (!profile) return null;
  return new MetadataCache(getConfigDir(), profile);
}

/**
 * Perform the full connect sequence: configure API client, resolve connection,
 * fetch external URL, update stored config, and notify services.
 * Extracted so it can be called from both IPC handler and ConnectionMonitor.
 */
export async function performConnect(): Promise<ConnectionState> {
  const server = configStore.serverConfig;
  if (!server) return { connected: false };

  const apiKey = getApiKey();
  apiClient.configure(server.localURL, server.externalURL, apiKey ?? undefined);

  try {
    const response = await apiClient.resolveConnection();
    // Update stored server name
    let configChanged = false;
    if (server.name !== response.server_name) {
      server.name = response.server_name;
      configChanged = true;
    }

    // Fetch external URL from server-info (same as iOS fetchExternalURL)
    try {
      const info = await apiClient.getServerInfo();
      if (info.external_url && server.externalURL !== info.external_url) {
        server.externalURL = info.external_url;
        apiClient.configure(server.localURL, server.externalURL, apiKey ?? undefined);
        configChanged = true;
      }
    } catch {
      // Non-critical — external URL is optional
    }

    if (configChanged) {
      configStore.serverConfig = server;
    }

    const state = apiClient.connectionState;
    state.serverName = response.server_name;
    state.serverVersion = response.version;

    // Notify services that connection is ready
    bgPrefetchService?.notifyConnected();
    connectionMonitor?.notifyConnected();

    return state;
  } catch {
    return { connected: false };
  }
}

/** Register all IPC handlers for renderer communication. */
export function registerIPCHandlers(): void {
  // ── Server Connection ──

  ipcMain.handle('server:getConfig', (): ServerConfig | null => {
    return configStore.serverConfig;
  });

  ipcMain.handle('server:updateConfig', (_event, config: ServerConfig): void => {
    configStore.serverConfig = config;
    // If clearing server config (disconnect), stop connection monitoring
    if (!config.name && !config.localURL) {
      connectionMonitor?.notifyDisconnected();
    }
  });

  ipcMain.handle('server:connect', async (): Promise<ConnectionState> => {
    return performConnect();
  });

  ipcMain.handle('server:getConnectionStatus', (): ConnectionState => {
    return apiClient.connectionState;
  });

  ipcMain.handle('server:setApiKey', (_event, key: string): void => {
    if (safeStorage.isEncryptionAvailable()) {
      const encrypted = safeStorage.encryptString(key);
      configStore.setApiKey(encrypted.toString('base64'));
    } else {
      configStore.setApiKey(key);
    }
  });

  ipcMain.handle('server:discover', async (): Promise<DiscoveredServer[]> => {
    return new Promise((resolve) => {
      const discovery = new ServerDiscovery();
      const DISCOVERY_TIMEOUT_MS = 8000;
      const EARLY_RESOLVE_DELAY_MS = 2000;
      let resolved = false;

      discovery.startSearch((servers) => {
        // Resolve early after a short delay once we find servers
        // (wait a bit for additional servers on the network)
        if (servers.length > 0 && !resolved) {
          setTimeout(() => {
            if (!resolved) {
              resolved = true;
              discovery.stopSearch();
              resolve(servers);
            }
          }, EARLY_RESOLVE_DELAY_MS);
        }
      });

      // Final timeout — resolve with whatever we have
      setTimeout(() => {
        if (!resolved) {
          resolved = true;
          discovery.stopSearch();
          resolve(discovery.discoveredServers);
        }
      }, DISCOVERY_TIMEOUT_MS);
    });
  });

  // ── Data ──

  ipcMain.handle('data:getPlaylists', async () => {
    return apiClient.getPlaylists();
  });

  ipcMain.handle('data:getSettings', async () => {
    return apiClient.getSettings();
  });

  ipcMain.handle('data:getFiles', async (_event, playlistKey: string) => {
    return apiClient.getFiles(playlistKey, true);
  });

  ipcMain.handle('data:getSyncStatus', async (_event, key: string) => {
    return apiClient.getSyncStatus(key);
  });

  ipcMain.handle('data:getSyncKeys', async () => {
    return apiClient.getSyncKeys();
  });

  ipcMain.handle('data:getSyncDestinations', async () => {
    return apiClient.getSyncDestinations();
  });

  ipcMain.handle('data:getAbout', async () => {
    return apiClient.getAbout();
  });

  ipcMain.handle('data:getSyncStatusSummary', async () => {
    return apiClient.getSyncStatusSummary();
  });

  ipcMain.handle(
    'data:linkDestination',
    async (_event, name: string, syncKey: string | null, path?: string) => {
      return apiClient.linkDestination(name, syncKey, path);
    },
  );

  ipcMain.handle('data:pruneSyncKey', async (_event, key: string) => {
    return apiClient.pruneSyncKey(key);
  });

  ipcMain.handle('data:renameSyncKey', async (_event, key: string, newKey: string) => {
    return apiClient.renameSyncKey(key, newKey);
  });

  ipcMain.handle(
    'data:addPlaylist',
    async (_event, key: string, url: string, name: string): Promise<OkResponse> => {
      return apiClient.addPlaylist(key, url, name);
    },
  );

  ipcMain.handle(
    'data:updatePlaylist',
    async (_event, key: string, url?: string, name?: string): Promise<OkResponse> => {
      return apiClient.updatePlaylist(key, url, name);
    },
  );

  // ── Pipeline ──

  ipcMain.handle(
    'pipeline:start',
    async (
      event,
      opts?: { playlist?: string; auto?: boolean; preset?: string },
    ): Promise<PipelineStartResult> => {
      const result = await apiClient.startPipeline(opts);
      if (!result) {
        throw new Error('Server is busy with another operation');
      }

      activePipelineAbort = new AbortController();
      const { signal } = activePipelineAbort;

      // Stream SSE events in the background, relaying to renderer
      (async () => {
        try {
          for await (const progress of apiClient.streamTask(result.task_id, signal)) {
            event.sender.send('pipeline:progress', progress);
            if ((progress as PipelineProgress).type === 'done') break;
          }
        } catch {
          // Aborted or connection lost — renderer handles cleanup
        } finally {
          activePipelineAbort = null;
        }
      })();

      return result;
    },
  );

  ipcMain.handle('pipeline:cancel', async (_event, taskId?: string): Promise<void> => {
    activePipelineAbort?.abort();
    activePipelineAbort = null;
    // Also cancel on the server side if we have a task ID
    if (taskId) {
      try {
        await apiClient.cancelTask(taskId);
      } catch {
        // Best-effort server-side cancel
      }
    }
  });

  // ── Sync ──

  ipcMain.handle(
    'sync:start',
    async (
      event,
      opts: {
        dest: string;
        playlists?: string[];
        syncKey?: string;
        concurrency?: number;
        usbDriveName?: string;
        profile?: string;
        force?: boolean;
        offlineOnly?: boolean;
      },
    ): Promise<SyncResult> => {
      activeSyncAbort = new AbortController();
      const engine = new SyncEngine(apiClient);
      const cacheManager = getCacheManager() ?? undefined;
      const metadataCache = getMetadataCache() ?? undefined;

      return engine.sync(opts.dest, {
        playlists: opts.playlists,
        syncKey: opts.syncKey,
        usbDriveName: opts.usbDriveName,
        profile: opts.profile,
        force: opts.force,
        concurrency: opts.concurrency,
        signal: activeSyncAbort.signal,
        cacheManager,
        metadataCache,
        offlineOnly: opts.offlineOnly,
        onProgress: (progress: SyncProgress) => {
          event.sender.send('sync:progress', progress);
        },
        onLog: (level, message) => {
          event.sender.send('sync:log', { level, message });
        },
      });
    },
  );

  ipcMain.handle('sync:cancel', (): void => {
    activeSyncAbort?.abort();
    activeSyncAbort = null;
  });

  ipcMain.handle(
    'sync:resolveSyncKey',
    async (_event, destPath: string, usbDriveName?: string): Promise<string | null> => {
      try {
        // Use server-side resolution when connected
        if (apiClient.connectionState.connected) {
          const scheme = usbDriveName ? 'usb://' : 'folder://';
          const resolved = await apiClient.resolveDestination({
            path: `${scheme}${destPath}`,
            driveName: usbDriveName,
          });
          return resolved.destination.sync_key;
        }
        // Offline fallback: read from manifest
        const manifest = readManifest(destPath);
        return manifest?.sync_key ?? null;
      } catch {
        return null;
      }
    },
  );

  // ── Drives ──

  ipcMain.handle('drives:list', (): DriveInfo[] => {
    return driveManager.listDrives();
  });

  ipcMain.handle('drives:eject', (_event, path: string): boolean => {
    return driveManager.ejectDrive(path);
  });

  ipcMain.handle('drives:selectFolder', async (): Promise<string | null> => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory', 'createDirectory'],
      title: 'Select sync destination',
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0] ?? null;
  });

  // ── Preferences ──

  ipcMain.handle('prefs:get', (): SyncPreferences => {
    return configStore.preferences;
  });

  ipcMain.handle('prefs:update', (_event, updates: Partial<SyncPreferences>): void => {
    configStore.updatePreferences(updates);
  });

  ipcMain.handle('prefs:addRecentDestination', (_event, path: string): void => {
    configStore.addRecentDestination(path);
  });

  ipcMain.handle('prefs:getProfile', (): string | undefined => {
    return configStore.profile;
  });

  ipcMain.handle('prefs:setProfile', (_event, name: string): void => {
    configStore.profile = name;
  });

  // ── Cookies ──

  ipcMain.handle('cookies:getStatus', async (): Promise<CookieStatus> => {
    return apiClient.getCookieStatus();
  });

  ipcMain.handle('cookies:refresh', async (event): Promise<CookieRefreshIPCResult> => {
    const parentWindow = BrowserWindow.fromWebContents(event.sender);
    if (!parentWindow) {
      return { success: false, error: 'No parent window' };
    }

    const result = await openCookieRefreshWindow(parentWindow);
    if (!result.success || !result.cookieText) {
      return { success: false, error: result.error ?? 'Login failed' };
    }

    // Upload extracted cookies to the server
    let uploadResult: CookieUploadResponse;
    try {
      uploadResult = await apiClient.uploadCookies(result.cookieText);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { success: false, error: `Upload failed: ${message}` };
    }

    return {
      success: uploadResult.valid,
      valid: uploadResult.valid,
      reason: uploadResult.reason,
      days_remaining: uploadResult.days_remaining,
      error: uploadResult.valid ? undefined : uploadResult.reason,
    };
  });

  ipcMain.handle('cookies:cancelRefresh', (): void => {
    cancelCookieRefresh();
  });

  // ── Cache ──

  ipcMain.handle('cache:pin', (_event, playlist: string): void => {
    configStore.pinPlaylist(playlist);
    bgPrefetchService?.triggerPinChange();
  });

  ipcMain.handle('cache:unpin', (_event, playlist: string): void => {
    configStore.unpinPlaylist(playlist);
    bgPrefetchService?.triggerPinChange();
  });

  ipcMain.handle('cache:getPinnedPlaylists', (): string[] => {
    return configStore.preferences.pinnedPlaylists;
  });

  ipcMain.handle('cache:getStatus', (): { totalSize: number; maxCacheBytes: number; playlists: PlaylistCacheStatus[] } => {
    const cm = getCacheManager();
    if (!cm) return { totalSize: 0, maxCacheBytes: 0, playlists: [] };

    const pinned = configStore.preferences.pinnedPlaylists;
    const cachedPlaylists = cm.getCachedPlaylists();
    const allKeys = [...new Set([...pinned, ...cachedPlaylists])];

    const playlists = allKeys.map((key) => {
      const entries = cm.getCachedFileInfos(key);
      return {
        playlistKey: key,
        total: 0, // Unknown without server — will be enriched by renderer
        cached: entries.length,
        pinned: pinned.includes(key),
      };
    });

    return { totalSize: cm.getTotalSize(), maxCacheBytes: configStore.preferences.maxCacheBytes, playlists };
  });

  ipcMain.handle('cache:hasData', (): boolean => {
    const cm = getCacheManager();
    return cm ? cm.hasData() : false;
  });

  ipcMain.handle('cache:getCachedPlaylists', (): { key: string; fileCount: number }[] => {
    const cm = getCacheManager();
    if (!cm) return [];
    return cm.getCachedPlaylists().map((key) => ({
      key,
      fileCount: cm.getCachedFileInfos(key).length,
    }));
  });

  ipcMain.handle('cache:prefetch', async (event): Promise<PrefetchResult> => {
    const cm = getCacheManager();
    if (!cm) return { downloaded: 0, skipped: 0, failed: 0, capacityCapped: 0, aborted: true, durationMs: 0 };

    const pinned = configStore.preferences.pinnedPlaylists;
    if (pinned.length === 0) {
      return { downloaded: 0, skipped: 0, failed: 0, capacityCapped: 0, aborted: false, durationMs: 0 };
    }

    activePrefetchAbort = new AbortController();
    const engine = new PrefetchEngine(apiClient, cm);
    const mc = getMetadataCache() ?? undefined;

    return engine.prefetch({
      playlists: pinned,
      profile: configStore.profile || undefined,
      maxCacheBytes: configStore.preferences.maxCacheBytes,
      pinnedPlaylists: new Set(pinned),
      signal: activePrefetchAbort.signal,
      metadataCache: mc,
      onProgress: (progress: SyncProgress) => {
        event.sender.send('cache:prefetchProgress', progress);
      },
      onLog: (level, message) => {
        event.sender.send('cache:prefetchLog', { level, message });
      },
    });
  });

  ipcMain.handle('cache:cancelPrefetch', (): void => {
    activePrefetchAbort?.abort();
    activePrefetchAbort = null;
  });

  ipcMain.handle('cache:clearPlaylist', (_event, playlist: string): void => {
    const cm = getCacheManager();
    if (cm) cm.clearPlaylist(playlist);
  });

  ipcMain.handle('cache:clearAll', (): void => {
    const cm = getCacheManager();
    if (cm) cm.clearAll();
  });

  ipcMain.handle('cache:setMaxSize', (_event, maxBytes: number): void => {
    configStore.updatePreferences({ maxCacheBytes: maxBytes });
    if (maxBytes > 0) {
      const cm = getCacheManager();
      if (cm) {
        const pinnedSet = new Set(configStore.preferences.pinnedPlaylists);
        cm.evictToLimit(maxBytes, pinnedSet);
      }
    }
    // Trigger a prefetch so the cache adjusts to the new limit
    if (bgPrefetchService) {
      bgPrefetchService.runOnce();
    }
  });

  // ── Auto-Pin ──

  ipcMain.handle('cache:getAutoPinNewPlaylists', (): boolean => {
    return configStore.autoPinNewPlaylists;
  });

  ipcMain.handle('cache:setAutoPinNewPlaylists', async (_event, enabled: boolean): Promise<string[]> => {
    configStore.setAutoPinNewPlaylists(enabled);
    if (enabled) {
      // Exclude all currently-unpinned playlists so they won't be auto-pinned.
      // Only truly NEW playlists (appearing after this point) will be auto-pinned.
      try {
        const playlists = await apiClient.getPlaylists();
        const serverKeys = playlists.map((p) => p.key);
        configStore.excludeUnpinnedPlaylists(serverKeys);
      } catch {
        // Non-critical — exclusion list may be incomplete
      }
    }
    return [];
  });

  ipcMain.handle('cache:syncPins', async (_event, playlistKeys: string[]): Promise<string[]> => {
    return configStore.syncPinsWithServer(playlistKeys);
  });

  ipcMain.handle('cache:getBackgroundPrefetchStatus', (): BackgroundPrefetchStatus => {
    if (bgPrefetchService) return bgPrefetchService.getStatus();
    return { running: false };
  });

  ipcMain.handle('cache:triggerPrefetch', async (): Promise<void> => {
    if (bgPrefetchService) {
      await bgPrefetchService.runOnce();
    }
  });

  // ── Connection Monitor ──

  ipcMain.handle('server:goOffline', (): void => {
    connectionMonitor?.notifyManualOffline();
  });

  // ── System ──

  ipcMain.handle('system:getDiskSpace', (): number | null => {
    try {
      const stat = statfsSync(getConfigDir());
      return stat.bfree * stat.bsize;
    } catch {
      return null;
    }
  });

  // ── App Info ──

  ipcMain.handle('app:getVersion', (): string => {
    return VERSION;
  });
}

/** Get decrypted API key. */
function getApiKey(): string | null {
  const stored = configStore.getApiKey();
  if (!stored) return null;

  if (safeStorage.isEncryptionAvailable()) {
    try {
      const buffer = Buffer.from(stored, 'base64');
      return safeStorage.decryptString(buffer);
    } catch {
      // Not encrypted or corrupted — return as-is
      return stored;
    }
  }
  return stored;
}
