import { create } from 'zustand';
import type {
  BackgroundPrefetchStatus,
  ConnectionState,
  DriveInfo,
  PipelineProgress,
  PlaylistCacheStatus,
  Playlist,
  ProfileInfo,
  SyncProgress,
  SyncResult,
  SyncStatusDetail,
} from '@mporter/core';

interface AppState {
  // Connection
  connection: ConnectionState;
  setConnection: (state: ConnectionState) => void;

  // Offline mode
  isOffline: boolean;
  setIsOffline: (offline: boolean) => void;

  // Playlists
  playlists: Playlist[];
  setPlaylists: (playlists: Playlist[]) => void;
  selectedPlaylists: Set<string>;
  togglePlaylist: (key: string) => void;
  selectAllPlaylists: () => void;
  clearSelection: () => void;

  // Profiles
  serverProfiles: Record<string, ProfileInfo>;
  setServerProfiles: (profiles: Record<string, ProfileInfo>) => void;
  activeProfile: string;
  setActiveProfile: (profile: string) => void;

  // Drives
  drives: DriveInfo[];
  setDrives: (drives: DriveInfo[]) => void;

  // Sync
  syncProgress: SyncProgress | null;
  setSyncProgress: (progress: SyncProgress | null) => void;
  isSyncing: boolean;
  setIsSyncing: (syncing: boolean) => void;
  lastSyncResult: SyncResult | null;
  setLastSyncResult: (result: SyncResult | null) => void;

  // Destination
  selectedDrive: DriveInfo | null;
  setSelectedDrive: (drive: DriveInfo | null) => void;
  destPath: string;
  setDestPath: (path: string) => void;
  destSyncStatus: SyncStatusDetail | null;
  setDestSyncStatus: (status: SyncStatusDetail | null) => void;

  // Cache
  pinnedPlaylists: Set<string>;
  setPinnedPlaylists: (pinned: Set<string>) => void;
  togglePin: (key: string) => void;
  cacheStatuses: Record<string, PlaylistCacheStatus>;
  setCacheStatuses: (statuses: Record<string, PlaylistCacheStatus>) => void;
  cacheTotalSize: number;
  setCacheTotalSize: (size: number) => void;
  cacheMaxBytes: number;
  setCacheMaxBytes: (max: number) => void;
  isPrefetching: boolean;
  setIsPrefetching: (prefetching: boolean) => void;
  prefetchProgress: SyncProgress | null;
  setPrefetchProgress: (progress: SyncProgress | null) => void;
  autoPinNewPlaylists: boolean;
  setAutoPinNewPlaylists: (enabled: boolean) => void;
  backgroundPrefetchStatus: BackgroundPrefetchStatus | null;
  setBackgroundPrefetchStatus: (status: BackgroundPrefetchStatus | null) => void;

  // Pipeline
  isPipelining: boolean;
  setIsPipelining: (pipelining: boolean) => void;
  pipelineTaskId: string | null;
  setPipelineTaskId: (id: string | null) => void;
  pipelineProgress: PipelineProgress | null;
  setPipelineProgress: (progress: PipelineProgress | null) => void;
  pipelineLogs: PipelineProgress[];
  appendPipelineLog: (log: PipelineProgress) => void;
  clearPipelineLogs: () => void;

  // UI
  activePage: string;
  setActivePage: (page: string) => void;
}

export const useAppState = create<AppState>((set) => ({
  // Connection
  connection: { connected: false },
  setConnection: (connection) => set({ connection }),

  // Offline mode
  isOffline: false,
  setIsOffline: (isOffline) => set({ isOffline }),

  // Playlists
  playlists: [],
  setPlaylists: (playlists) => set({ playlists }),
  selectedPlaylists: new Set<string>(),
  togglePlaylist: (key) =>
    set((state) => {
      const next = new Set(state.selectedPlaylists);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return { selectedPlaylists: next };
    }),
  selectAllPlaylists: () =>
    set((state) => ({
      selectedPlaylists: new Set(state.playlists.map((p) => p.key)),
    })),
  clearSelection: () => set({ selectedPlaylists: new Set() }),

  // Profiles
  serverProfiles: {},
  setServerProfiles: (serverProfiles) => set({ serverProfiles }),
  activeProfile: '',
  setActiveProfile: (activeProfile) => set({ activeProfile }),

  // Drives
  drives: [],
  setDrives: (drives) => set({ drives }),

  // Sync
  syncProgress: null,
  setSyncProgress: (syncProgress) => set({ syncProgress }),
  isSyncing: false,
  setIsSyncing: (isSyncing) => set({ isSyncing }),
  lastSyncResult: null,
  setLastSyncResult: (lastSyncResult) => set({ lastSyncResult }),

  // Destination
  selectedDrive: null,
  setSelectedDrive: (selectedDrive) => set({ selectedDrive }),
  destPath: '',
  setDestPath: (destPath) => set({ destPath }),
  destSyncStatus: null,
  setDestSyncStatus: (destSyncStatus) => set({ destSyncStatus }),

  // Cache
  pinnedPlaylists: new Set<string>(),
  setPinnedPlaylists: (pinnedPlaylists) => set({ pinnedPlaylists }),
  togglePin: (key) =>
    set((state) => {
      const next = new Set(state.pinnedPlaylists);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return { pinnedPlaylists: next };
    }),
  cacheStatuses: {},
  setCacheStatuses: (cacheStatuses) => set({ cacheStatuses }),
  cacheTotalSize: 0,
  setCacheTotalSize: (cacheTotalSize) => set({ cacheTotalSize }),
  cacheMaxBytes: 0,
  setCacheMaxBytes: (cacheMaxBytes) => set({ cacheMaxBytes }),
  isPrefetching: false,
  setIsPrefetching: (isPrefetching) => set({ isPrefetching }),
  prefetchProgress: null,
  setPrefetchProgress: (prefetchProgress) => set({ prefetchProgress }),
  autoPinNewPlaylists: false,
  setAutoPinNewPlaylists: (autoPinNewPlaylists) => set({ autoPinNewPlaylists }),
  backgroundPrefetchStatus: null,
  setBackgroundPrefetchStatus: (backgroundPrefetchStatus) => set({ backgroundPrefetchStatus }),

  // Pipeline
  isPipelining: false,
  setIsPipelining: (isPipelining) => set({ isPipelining }),
  pipelineTaskId: null,
  setPipelineTaskId: (pipelineTaskId) => set({ pipelineTaskId }),
  pipelineProgress: null,
  setPipelineProgress: (pipelineProgress) => set({ pipelineProgress }),
  pipelineLogs: [],
  appendPipelineLog: (log) =>
    set((state) => ({ pipelineLogs: [...state.pipelineLogs, log] })),
  clearPipelineLogs: () => set({ pipelineLogs: [] }),

  // UI
  activePage: 'connect',
  setActivePage: (activePage) => set({ activePage }),
}));
