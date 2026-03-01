import { contextBridge, ipcRenderer } from 'electron';
import type {
  AboutResponse,
  BackgroundPrefetchStatus,
  ConnectionState,
  CookieStatus,
  DiscoveredServer,
  DriveInfo,
  FileListResponse,
  OkResponse,
  PipelineProgress,
  PipelineStartResult,
  Playlist,
  PlaylistCacheStatus,
  PrefetchResult,
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
  getAbout: (): Promise<AboutResponse> => ipcRenderer.invoke('data:getAbout'),
  addPlaylist: (key: string, url: string, name: string): Promise<OkResponse> =>
    ipcRenderer.invoke('data:addPlaylist', key, url, name),
  updatePlaylist: (key: string, url?: string, name?: string): Promise<OkResponse> =>
    ipcRenderer.invoke('data:updatePlaylist', key, url, name),

  // Pipeline
  startPipeline: (opts?: {
    playlist?: string;
    auto?: boolean;
    preset?: string;
  }): Promise<PipelineStartResult> => ipcRenderer.invoke('pipeline:start', opts),
  cancelPipeline: (taskId?: string): Promise<void> =>
    ipcRenderer.invoke('pipeline:cancel', taskId),

  // Sync
  startSync: (opts: {
    dest: string;
    playlists?: string[];
    syncKey?: string;
    concurrency?: number;
    usbDriveName?: string;
    profile?: string;
    force?: boolean;
    offlineOnly?: boolean;
  }): Promise<SyncResult> => ipcRenderer.invoke('sync:start', opts),
  cancelSync: (): Promise<void> => ipcRenderer.invoke('sync:cancel'),
  resolveSyncKey: (destPath: string, usbDriveName?: string): Promise<string | null> =>
    ipcRenderer.invoke('sync:resolveSyncKey', destPath, usbDriveName),

  // Drives
  listDrives: (): Promise<DriveInfo[]> => ipcRenderer.invoke('drives:list'),
  ejectDrive: (path: string): Promise<boolean> => ipcRenderer.invoke('drives:eject', path),
  selectFolder: (): Promise<string | null> => ipcRenderer.invoke('drives:selectFolder'),

  // Cookies
  getCookieStatus: (): Promise<CookieStatus> => ipcRenderer.invoke('cookies:getStatus'),
  refreshCookies: (): Promise<{
    success: boolean;
    valid?: boolean;
    reason?: string;
    days_remaining?: number | null;
    error?: string;
  }> => ipcRenderer.invoke('cookies:refresh'),
  cancelCookieRefresh: (): Promise<void> => ipcRenderer.invoke('cookies:cancelRefresh'),

  // Preferences
  getPreferences: (): Promise<SyncPreferences> => ipcRenderer.invoke('prefs:get'),
  updatePreferences: (updates: Partial<SyncPreferences>): Promise<void> =>
    ipcRenderer.invoke('prefs:update', updates),
  addRecentDestination: (path: string): Promise<void> =>
    ipcRenderer.invoke('prefs:addRecentDestination', path),
  getProfile: (): Promise<string | undefined> => ipcRenderer.invoke('prefs:getProfile'),
  setProfile: (name: string): Promise<void> => ipcRenderer.invoke('prefs:setProfile', name),

  // Cache
  cachePin: (playlist: string): Promise<void> => ipcRenderer.invoke('cache:pin', playlist),
  cacheUnpin: (playlist: string): Promise<void> => ipcRenderer.invoke('cache:unpin', playlist),
  cacheGetPinnedPlaylists: (): Promise<string[]> => ipcRenderer.invoke('cache:getPinnedPlaylists'),
  cacheGetStatus: (): Promise<{ totalSize: number; maxCacheBytes: number; playlists: PlaylistCacheStatus[] }> =>
    ipcRenderer.invoke('cache:getStatus'),
  cacheHasData: (): Promise<boolean> => ipcRenderer.invoke('cache:hasData'),
  cacheGetCachedPlaylists: (): Promise<{ key: string; fileCount: number }[]> =>
    ipcRenderer.invoke('cache:getCachedPlaylists'),
  cachePrefetch: (): Promise<PrefetchResult> => ipcRenderer.invoke('cache:prefetch'),
  cacheCancelPrefetch: (): Promise<void> => ipcRenderer.invoke('cache:cancelPrefetch'),
  cacheClearPlaylist: (playlist: string): Promise<void> =>
    ipcRenderer.invoke('cache:clearPlaylist', playlist),
  cacheClearAll: (): Promise<void> => ipcRenderer.invoke('cache:clearAll'),
  cacheSetMaxSize: (maxBytes: number): Promise<void> =>
    ipcRenderer.invoke('cache:setMaxSize', maxBytes),
  cacheGetAutoPinNewPlaylists: (): Promise<boolean> =>
    ipcRenderer.invoke('cache:getAutoPinNewPlaylists'),
  cacheSetAutoPinNewPlaylists: (enabled: boolean): Promise<string[]> =>
    ipcRenderer.invoke('cache:setAutoPinNewPlaylists', enabled),
  cacheSyncPins: (playlistKeys: string[]): Promise<string[]> =>
    ipcRenderer.invoke('cache:syncPins', playlistKeys),
  cacheGetBackgroundPrefetchStatus: (): Promise<BackgroundPrefetchStatus> =>
    ipcRenderer.invoke('cache:getBackgroundPrefetchStatus'),
  cacheTriggerPrefetch: (): Promise<void> =>
    ipcRenderer.invoke('cache:triggerPrefetch'),

  // Connection monitor
  goOffline: (): Promise<void> => ipcRenderer.invoke('server:goOffline'),

  // System
  getDiskSpace: (): Promise<number | null> => ipcRenderer.invoke('system:getDiskSpace'),

  // Events (main -> renderer)
  onConnectionStatusChange: (
    callback: (data: { offline: boolean; connection?: ConnectionState }) => void,
  ) => {
    const handler = (
      _event: Electron.IpcRendererEvent,
      data: { offline: boolean; connection?: ConnectionState },
    ) => callback(data);
    ipcRenderer.on('connection:statusChange', handler);
    return () => ipcRenderer.removeListener('connection:statusChange', handler);
  },
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
  onPrefetchProgress: (callback: (progress: SyncProgress) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, progress: SyncProgress) =>
      callback(progress);
    ipcRenderer.on('cache:prefetchProgress', handler);
    return () => ipcRenderer.removeListener('cache:prefetchProgress', handler);
  },
  onAutoSync: (callback: (data: { drive: DriveInfo }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, data: { drive: DriveInfo }) =>
      callback(data);
    ipcRenderer.on('drives:autoSync', handler);
    return () => ipcRenderer.removeListener('drives:autoSync', handler);
  },
  onPipelineProgress: (callback: (progress: PipelineProgress) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, progress: PipelineProgress) =>
      callback(progress);
    ipcRenderer.on('pipeline:progress', handler);
    return () => ipcRenderer.removeListener('pipeline:progress', handler);
  },
  onBackgroundPrefetchStatus: (callback: (status: BackgroundPrefetchStatus) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, status: BackgroundPrefetchStatus) =>
      callback(status);
    ipcRenderer.on('cache:backgroundPrefetchStatus', handler);
    return () => ipcRenderer.removeListener('cache:backgroundPrefetchStatus', handler);
  },

  // App info
  getVersion: (): Promise<string> => ipcRenderer.invoke('app:getVersion'),
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);

export type ElectronAPI = typeof electronAPI;
