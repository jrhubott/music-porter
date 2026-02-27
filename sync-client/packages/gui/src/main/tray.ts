import { Tray, Menu, nativeImage, BrowserWindow } from 'electron';

let tray: Tray | null = null;

/** Create the system tray icon and menu. */
export function createTray(mainWindow: BrowserWindow): void {
  // Use a small icon (will be replaced with a real icon in production)
  const icon = nativeImage.createEmpty();
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
        mainWindow.destroy();
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
