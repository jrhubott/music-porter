import { app, Tray, Menu, nativeImage, BrowserWindow } from 'electron';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TRAY_ICON_SIZE = 16;

let tray: Tray | null = null;

function loadTrayIcon(): Electron.NativeImage {
  const candidates = [
    join(__dirname, '..', '..', 'build', 'icon.png'),
    join(__dirname, '..', '..', '..', 'build', 'icon.png'),
  ];
  for (const iconPath of candidates) {
    if (existsSync(iconPath)) {
      return nativeImage.createFromPath(iconPath).resize({ width: TRAY_ICON_SIZE, height: TRAY_ICON_SIZE });
    }
  }
  return nativeImage.createEmpty();
}

/** Create the system tray icon and menu. */
export function createTray(mainWindow: BrowserWindow): void {
  const icon = loadTrayIcon();
  tray = new Tray(icon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Window',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Music Porter Sync');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    mainWindow.show();
    mainWindow.focus();
  });
}

/** Update the tray tooltip with connection info. */
export function updateTrayTooltip(serverName: string, connectionType: string): void {
  if (tray) {
    tray.setToolTip(`Music Porter Sync — ${serverName} (${connectionType})`);
  }
}
