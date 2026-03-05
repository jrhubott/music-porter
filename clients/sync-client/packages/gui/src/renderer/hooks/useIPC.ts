import type { ElectronAPI } from '../../preload/index.js';

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}

/** Access the typed Electron IPC API. */
export function useIPC(): ElectronAPI {
  return window.electronAPI;
}
