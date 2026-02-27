import { create } from 'zustand';
import type {
  ConnectionState,
  DriveInfo,
  Playlist,
  SyncProgress,
  SyncResult,
} from '@mporter/core';

interface AppState {
  // Connection
  connection: ConnectionState;
  setConnection: (state: ConnectionState) => void;

  // Playlists
  playlists: Playlist[];
  setPlaylists: (playlists: Playlist[]) => void;
  selectedPlaylists: Set<string>;
  togglePlaylist: (key: string) => void;
  selectAllPlaylists: () => void;
  clearSelection: () => void;

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

  // UI
  activePage: string;
  setActivePage: (page: string) => void;
}

export const useAppState = create<AppState>((set, get) => ({
  // Connection
  connection: { connected: false },
  setConnection: (connection) => set({ connection }),

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

  // UI
  activePage: 'connect',
  setActivePage: (activePage) => set({ activePage }),
}));
