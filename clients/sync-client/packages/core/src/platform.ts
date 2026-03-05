import { homedir, platform } from 'node:os';
import { join } from 'node:path';
import { APP_NAME, EXCLUDED_MAC_VOLUMES } from './constants.js';

export type Platform = 'darwin' | 'linux' | 'win32';

/** Get the current OS platform. */
export function currentPlatform(): Platform {
  const p = platform();
  if (p === 'darwin' || p === 'linux' || p === 'win32') {
    return p;
  }
  // Fallback for unsupported platforms — treat as Linux
  return 'linux';
}

/** Get the platform-appropriate config directory for the app. */
export function getConfigDir(): string {
  const p = currentPlatform();
  switch (p) {
    case 'darwin':
      return join(homedir(), 'Library', 'Application Support', APP_NAME);
    case 'win32':
      return join(process.env['APPDATA'] ?? join(homedir(), 'AppData', 'Roaming'), APP_NAME);
    case 'linux':
      return join(process.env['XDG_CONFIG_HOME'] ?? join(homedir(), '.config'), APP_NAME);
  }
}

/** Get macOS volume exclusions for USB detection. */
export function getExcludedVolumes(): string[] {
  return EXCLUDED_MAC_VOLUMES;
}

/** Get the default USB mount directories for the current platform. */
export function getUSBMountPaths(): string[] {
  const p = currentPlatform();
  switch (p) {
    case 'darwin':
      return ['/Volumes'];
    case 'linux': {
      const user = process.env['USER'] ?? 'root';
      return [`/media/${user}`, '/mnt'];
    }
    case 'win32':
      // Windows uses drive letters, handled separately in drive-manager
      return [];
  }
}
