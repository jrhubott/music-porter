import { BrowserWindow, session } from 'electron';
import type { Cookie } from 'electron';
import {
  APPLE_AUTH_COOKIE_NAME,
  APPLE_COOKIE_DOMAIN,
  APPLE_DOMAIN_SUFFIX,
  APPLE_MUSIC_URL,
  COOKIE_POLL_INTERVAL_MS,
  COOKIE_REFRESH_TIMEOUT_MS,
  COOKIE_WINDOW_HEIGHT,
  COOKIE_WINDOW_WIDTH,
  NETSCAPE_COOKIE_HEADER,
  SESSION_COOKIE_FALLBACK_S,
} from '@mporter/core';

/** Partition name for the Apple Music login session (persists across restarts). */
const LOGIN_PARTITION = 'persist:apple-music-login';

/** Boolean flag component of a Netscape cookie line. */
const NETSCAPE_TRUE = 'TRUE';
const NETSCAPE_FALSE = 'FALSE';

export interface CookieRefreshResult {
  success: boolean;
  cookieText?: string;
  error?: string;
}

/** Active cookie refresh window (at most one at a time). */
let activeCookieWindow: BrowserWindow | null = null;

/** Cancel an in-progress cookie refresh by closing its window. */
export function cancelCookieRefresh(): void {
  if (activeCookieWindow && !activeCookieWindow.isDestroyed()) {
    activeCookieWindow.close();
  }
}

/**
 * Open a BrowserWindow pointed at Apple Music, wait for the user to sign in,
 * then extract all Apple cookies in Netscape format.
 */
export function openCookieRefreshWindow(
  parentWindow: BrowserWindow,
): Promise<CookieRefreshResult> {
  return new Promise((resolve) => {
    let resolved = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let timeoutTimer: ReturnType<typeof setTimeout> | null = null;

    const loginSession = session.fromPartition(LOGIN_PARTITION);

    const win = new BrowserWindow({
      width: COOKIE_WINDOW_WIDTH,
      height: COOKIE_WINDOW_HEIGHT,
      parent: parentWindow,
      title: 'Sign In to Apple Music',
      show: false,
      webPreferences: {
        partition: LOGIN_PARTITION,
        nodeIntegration: false,
        contextIsolation: true,
      },
    });

    function cleanup(): void {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
        timeoutTimer = null;
      }
    }

    function finish(result: CookieRefreshResult): void {
      if (resolved) return;
      resolved = true;
      cleanup();
      if (!win.isDestroyed()) win.close();
      resolve(result);
    }

    // Poll for the auth cookie
    pollTimer = setInterval(async () => {
      if (resolved) return;
      try {
        const cookies = await loginSession.cookies.get({
          domain: APPLE_COOKIE_DOMAIN,
          name: APPLE_AUTH_COOKIE_NAME,
        });
        if (cookies.length > 0) {
          const allAppleCookies = await loginSession.cookies.get({});
          const filtered = allAppleCookies.filter((c) =>
            c.domain?.includes(APPLE_DOMAIN_SUFFIX),
          );
          const cookieText = convertToNetscape(filtered);
          finish({ success: true, cookieText });
        }
      } catch {
        // Ignore polling errors — window may be closing
      }
    }, COOKIE_POLL_INTERVAL_MS);

    // Timeout
    timeoutTimer = setTimeout(() => {
      finish({ success: false, error: 'Login timed out' });
    }, COOKIE_REFRESH_TIMEOUT_MS);

    activeCookieWindow = win;

    // Prevent the loaded page from overriding our window title
    win.on('page-title-updated', (e) => e.preventDefault());

    // User closed window before completing login
    win.on('closed', () => {
      activeCookieWindow = null;
      finish({ success: false, error: 'Login window closed' });
    });

    win.once('ready-to-show', () => win.show());
    win.loadURL(APPLE_MUSIC_URL);
  });
}

/** Convert Electron Cookie[] to Netscape HTTP Cookie File format. */
export function convertToNetscape(cookies: Cookie[]): string {
  const lines: string[] = [NETSCAPE_COOKIE_HEADER];

  for (const c of cookies) {
    const domain = c.domain ?? '';
    const subdomainFlag = domain.startsWith('.') ? NETSCAPE_TRUE : NETSCAPE_FALSE;
    const path = c.path ?? '/';
    const secure = c.secure ? NETSCAPE_TRUE : NETSCAPE_FALSE;
    const expires = c.expirationDate
      ? Math.round(c.expirationDate)
      : Math.round(Date.now() / 1000) + SESSION_COOKIE_FALLBACK_S;
    lines.push(`${domain}\t${subdomainFlag}\t${path}\t${secure}\t${expires}\t${c.name}\t${c.value}`);
  }

  return lines.join('\n') + '\n';
}

/** Clear the persisted Apple Music login session (for switching accounts). */
export async function clearCookieSession(): Promise<void> {
  const loginSession = session.fromPartition(LOGIN_PARTITION);
  await loginSession.clearStorageData();
}
