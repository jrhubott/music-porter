import { BrowserWindow } from 'electron';
import { ConfigStore, DriveManager } from '@mporter/core';

let driveManager: DriveManager | null = null;

/** Start watching for USB drive changes and notify the renderer. */
export function startDriveWatcher(mainWindow: BrowserWindow): void {
  driveManager = new DriveManager();
  driveManager.startWatching((added, removed) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('drives:change', { added, removed });

      // Check for per-drive auto-sync triggers
      if (added.length > 0) {
        const configStore = new ConfigStore();
        const autoSyncDrives = configStore.preferences.autoSyncDrives;
        for (const drive of added) {
          if (autoSyncDrives.includes(drive.name)) {
            mainWindow.webContents.send('drives:autoSync', { drive });
          }
        }
      }
    }
  });
}

/** Stop the drive watcher. */
export function stopDriveWatcher(): void {
  driveManager?.stopWatching();
  driveManager = null;
}
