import { BrowserWindow } from 'electron';
import { DriveManager } from '@mporter/core';

let driveManager: DriveManager | null = null;

/** Start watching for USB drive changes and notify the renderer. */
export function startDriveWatcher(mainWindow: BrowserWindow): void {
  driveManager = new DriveManager();
  driveManager.startWatching((added, removed) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('drives:change', { added, removed });
    }
  });
}

/** Stop the drive watcher. */
export function stopDriveWatcher(): void {
  driveManager?.stopWatching();
  driveManager = null;
}
