import { contextBridge, ipcRenderer } from 'electron';
import type {
  ConnectionState,
  DiscoveredServer,
  DriveInfo,
  FileListResponse,
  Playlist,
  ServerConfig,
  SettingsResponse,
  SyncDestinationsResponse,
  SyncKeySummary,
  SyncPreferences,
  SyncProgress,
  SyncResult,
  SyncStatusDetail,
} from '@mporter/core';

/** Typed API surface exposed to the renderer via contextBridge. */
const electronAPI = {
  // Server
  getServerConfig: (): Promise<ServerConfig | null> => ipcRenderer.invoke('server:getConfig'),
  updateServerConfig: (config: ServerConfig): Promise<void> =>
    ipcRenderer.invoke('server:updateConfig', config),
  connect: (): Promise<ConnectionState> => ipcRenderer.invoke('server:connect'),
  getConnectionStatus: (): Promise<ConnectionState> =>
    ipcRenderer.invoke('server:getConnectionStatus'),
  setApiKey: (key: string): Promise<void> => ipcRenderer.invoke('server:setApiKey', key),
  discoverServers: (): Promise<DiscoveredServer[]> => ipcRenderer.invoke('server:discover'),

  // Data
  getPlaylists: (): Promise<Playlist[]> => ipcRenderer.invoke('data:getPlaylists'),
  getSettings: (): Promise<SettingsResponse> => ipcRenderer.invoke('data:getSettings'),
  getFiles: (playlistKey: string): Promise<FileListResponse> =>
    ipcRenderer.invoke('data:getFiles', playlistKey),
  getSyncStatus: (key: string): Promise<SyncStatusDetail> =>
    ipcRenderer.invoke('data:getSyncStatus', key),
  getSyncKeys: (): Promise<SyncKeySummary[]> => ipcRenderer.invoke('data:getSyncKeys'),
  getSyncDestinations: (): Promise<SyncDestinationsResponse> =>
    ipcRenderer.invoke('data:getSyncDestinations'),

  // Sync
  startSync: (opts: {
    dest: string;
    playlists?: string[];
    syncKey?: string;
    concurrency?: number;
    usbDriveName?: string;
    profile?: string;
    force?: boolean;
  }): Promise<SyncResult> => ipcRenderer.invoke('sync:start', opts),
  cancelSync: (): Promise<void> => ipcRenderer.invoke('sync:cancel'),

  // Drives
  listDrives: (): Promise<DriveInfo[]> => ipcRenderer.invoke('drives:list'),
  ejectDrive: (path: string): Promise<boolean> => ipcRenderer.invoke('drives:eject', path),
  selectFolder: (): Promise<string | null> => ipcRenderer.invoke('drives:selectFolder'),

  // Preferences
  getPreferences: (): Promise<SyncPreferences> => ipcRenderer.invoke('prefs:get'),
  updatePreferences: (updates: Partial<SyncPreferences>): Promise<void> =>
    ipcRenderer.invoke('prefs:update', updates),
  getProfile: (): Promise<string | undefined> => ipcRenderer.invoke('prefs:getProfile'),
  setProfile: (name: string): Promise<void> => ipcRenderer.invoke('prefs:setProfile', name),

  // Events (main -> renderer)
  onSyncProgress: (callback: (progress: SyncProgress) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, progress: SyncProgress) =>
      callback(progress);
    ipcRenderer.on('sync:progress', handler);
    return () => ipcRenderer.removeListener('sync:progress', handler);
  },
  onDriveChange: (callback: (data: { added: DriveInfo[]; removed: DriveInfo[] }) => void) => {
    const handler = (
      _event: Electron.IpcRendererEvent,
      data: { added: DriveInfo[]; removed: DriveInfo[] },
    ) => callback(data);
    ipcRenderer.on('drives:change', handler);
    return () => ipcRenderer.removeListener('drives:change', handler);
  },
  onAutoSync: (callback: (data: { drive: DriveInfo }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: { drive: DriveInfo }) =>
      callback(data);
    ipcRenderer.on('drives:autoSync', handler);
    return () => ipcRenderer.removeListener('drives:autoSync', handler);
  },

  // App info
  getVersion: (): Promise<string> => ipcRenderer.invoke('app:getVersion'),
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);

export type ElectronAPI = typeof electronAPI;
