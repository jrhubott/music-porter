import { app, BrowserWindow, nativeImage, nativeTheme, screen } from 'electron';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { registerIPCHandlers, configStore, apiClient, setBackgroundPrefetchService, setConnectionMonitor, performConnect } from './ipc-handlers.js';
import { ConnectionMonitor } from './connection-monitor.js';
import { createTray } from './tray.js';
import { startDriveWatcher } from './drive-watcher.js';
import { BackgroundPrefetchService } from './background-prefetch.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const DEBUG = process.argv.includes('--devtools');

/** Display name shown in macOS dock, menu bar, and window title. */
const APP_DISPLAY_NAME = 'Music Porter Sync';

// Set app name early so macOS dock/menu bar show the correct name during development
app.name = APP_DISPLAY_NAME;

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

/** Check whether saved window bounds overlap a visible display. */
function isOnScreen(x: number, y: number, width: number, height: number): boolean {
  const rect = { x, y, width, height };
  const display = screen.getDisplayMatching(rect);
  const { x: dx, y: dy, width: dw, height: dh } = display.workArea;
  // At least some portion of the window must be within the display work area
  return x + width > dx && x < dx + dw && y + height > dy && y < dy + dh;
}

function createWindow(): void {
  nativeTheme.themeSource = 'dark';

  const saved = configStore.windowState;
  const useSaved = saved && isOnScreen(saved.x, saved.y, saved.width, saved.height);

  const icon = getAppIcon();
  mainWindow = new BrowserWindow({
    width: useSaved ? saved.width : WINDOW_WIDTH,
    height: useSaved ? saved.height : WINDOW_HEIGHT,
    ...(useSaved ? { x: saved.x, y: saved.y } : {}),
    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,
    title: APP_DISPLAY_NAME,
    backgroundColor: '#212529',
    ...(icon ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (useSaved && saved.isMaximized) {
    mainWindow.maximize();
  }

  if (process.env['VITE_DEV_SERVER_URL']) {
    mainWindow.loadURL(process.env['VITE_DEV_SERVER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '..', 'renderer', 'index.html'));
  }

  if (DEBUG) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('close', () => {
    if (!mainWindow) return;
    const isMaximized = mainWindow.isMaximized();
    const { x, y, width, height } = mainWindow.getNormalBounds();
    configStore.windowState = { x, y, width, height, isMaximized };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

let bgPrefetch: BackgroundPrefetchService | null = null;
let connMonitor: ConnectionMonitor | null = null;

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

  // Start connection monitor
  connMonitor = new ConnectionMonitor(apiClient);
  setConnectionMonitor(connMonitor);
  connMonitor.start(mainWindow!, performConnect);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  bgPrefetch?.stop();
  connMonitor?.stop();
});

app.on('window-all-closed', () => {
  app.quit();
});
