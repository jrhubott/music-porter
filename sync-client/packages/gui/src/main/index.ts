import { app, BrowserWindow, nativeImage, nativeTheme } from 'electron';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { registerIPCHandlers, configStore, apiClient, setBackgroundPrefetchService } from './ipc-handlers.js';
import { createTray } from './tray.js';
import { startDriveWatcher } from './drive-watcher.js';
import { BackgroundPrefetchService } from './background-prefetch.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const DEBUG = process.argv.includes('--devtools');

let mainWindow: BrowserWindow | null = null;

const WINDOW_WIDTH = 1100;
const WINDOW_HEIGHT = 750;
const MIN_WIDTH = 800;
const MIN_HEIGHT = 600;

function getAppIcon(): Electron.NativeImage | undefined {
  // In production, icon is next to the app binary via electron-builder's buildResources.
  // In development, resolve from the source build/ dir.
  const candidates = [
    join(__dirname, '..', '..', 'build', 'icon.png'),
    join(__dirname, '..', '..', '..', 'build', 'icon.png'),
  ];
  for (const iconPath of candidates) {
    if (existsSync(iconPath)) {
      return nativeImage.createFromPath(iconPath);
    }
  }
  return undefined;
}

function createWindow(): void {
  nativeTheme.themeSource = 'dark';

  const icon = getAppIcon();
  mainWindow = new BrowserWindow({
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,
    title: 'Music Porter Sync',
    backgroundColor: '#212529',
    ...(icon ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (process.env['VITE_DEV_SERVER_URL']) {
    mainWindow.loadURL(process.env['VITE_DEV_SERVER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '..', 'renderer', 'index.html'));
  }

  if (DEBUG) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

let bgPrefetch: BackgroundPrefetchService | null = null;

app.whenReady().then(() => {
  registerIPCHandlers();
  createWindow();
  createTray(mainWindow!);
  startDriveWatcher(mainWindow!);

  // macOS: Set the dock icon at runtime (BrowserWindow.icon is ignored on macOS)
  if (process.platform === 'darwin') {
    const dockIcon = getAppIcon();
    if (dockIcon) {
      app.dock.setIcon(dockIcon);
    }
  }

  // Start background prefetch service
  bgPrefetch = new BackgroundPrefetchService(apiClient, configStore);
  setBackgroundPrefetchService(bgPrefetch);
  bgPrefetch.start(mainWindow!);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  bgPrefetch?.stop();
});

app.on('window-all-closed', () => {
  app.quit();
});
