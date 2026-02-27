import { ipcMain, dialog, safeStorage } from 'electron';
import {
  APIClient,
  ConfigStore,
  SyncEngine,
  DriveManager,
  ServerDiscovery,
  VERSION,
} from '@mporter/core';
import type {
  ConnectionState,
  DiscoveredServer,
  DriveInfo,
  ServerConfig,
  SyncPreferences,
  SyncProgress,
  SyncResult,
} from '@mporter/core';

const configStore = new ConfigStore();
const apiClient = new APIClient();
const driveManager = new DriveManager();
let activeSyncAbort: AbortController | null = null;

/** Register all IPC handlers for renderer communication. */
export function registerIPCHandlers(): void {
  // ── Server Connection ──

  ipcMain.handle('server:getConfig', (): ServerConfig | null => {
    return configStore.serverConfig;
  });

  ipcMain.handle('server:updateConfig', (_event, config: ServerConfig): void => {
    configStore.serverConfig = config;
  });

  ipcMain.handle('server:connect', async (): Promise<ConnectionState> => {
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
      return state;
    } catch {
      return { connected: false };
    }
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
      },
    ): Promise<SyncResult> => {
      activeSyncAbort = new AbortController();
      const engine = new SyncEngine(apiClient);

      return engine.sync(opts.dest, {
        playlists: opts.playlists,
        syncKey: opts.syncKey,
        usbDriveName: opts.usbDriveName,
        concurrency: opts.concurrency,
        signal: activeSyncAbort.signal,
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

  ipcMain.handle('prefs:getProfile', (): string | undefined => {
    return configStore.profile;
  });

  ipcMain.handle('prefs:setProfile', (_event, name: string): void => {
    configStore.profile = name;
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
