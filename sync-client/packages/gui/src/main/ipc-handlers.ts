import { ipcMain, dialog, safeStorage } from 'electron';
import {
  APIClient,
  ConfigStore,
  SyncEngine,
  DriveManager,
  ServerDiscovery,
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
      if (server.name !== response.server_name) {
        server.name = response.server_name;
        configStore.serverConfig = server;
      }
      return apiClient.connectionState;
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
      const DISCOVERY_TIMEOUT_MS = 10000;
      discovery.startSearch(() => {});
      setTimeout(() => {
        discovery.stopSearch();
        resolve(discovery.discoveredServers);
      }, DISCOVERY_TIMEOUT_MS);
    });
  });

  // ── Data ──

  ipcMain.handle('data:getPlaylists', async () => {
    return apiClient.getPlaylists();
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
      opts: { dest: string; playlists?: string[]; syncKey?: string; concurrency?: number },
    ): Promise<SyncResult> => {
      activeSyncAbort = new AbortController();
      const engine = new SyncEngine(apiClient);

      return engine.sync(opts.dest, {
        playlists: opts.playlists,
        syncKey: opts.syncKey,
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
