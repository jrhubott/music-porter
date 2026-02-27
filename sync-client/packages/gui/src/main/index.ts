import { app, BrowserWindow, nativeTheme } from 'electron';
import { join } from 'node:path';
import { registerIPCHandlers } from './ipc-handlers.js';
import { createTray } from './tray.js';
import { startDriveWatcher } from './drive-watcher.js';

let mainWindow: BrowserWindow | null = null;

const WINDOW_WIDTH = 1100;
const WINDOW_HEIGHT = 750;
const MIN_WIDTH = 800;
const MIN_HEIGHT = 600;

function createWindow(): void {
  nativeTheme.themeSource = 'dark';

  mainWindow = new BrowserWindow({
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,
    title: 'Music Porter Sync',
    backgroundColor: '#212529',
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // In development, load from Vite dev server
  if (process.env['VITE_DEV_SERVER_URL']) {
    mainWindow.loadURL(process.env['VITE_DEV_SERVER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '..', 'renderer', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  registerIPCHandlers();
  createWindow();
  createTray(mainWindow!);
  startDriveWatcher(mainWindow!);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
