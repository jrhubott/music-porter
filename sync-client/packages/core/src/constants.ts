/** Sync client version — bumped independently from the server. */
export const VERSION = '1.5.2';

/** Manifest filename stored in sync destination root. */
export const MANIFEST_FILENAME = '.music-porter-sync.json';

/** Default number of parallel file downloads. */
export const DEFAULT_CONCURRENCY = 4;

/** Timeout (ms) for local URL connection when external URL is available. */
export const LOCAL_TIMEOUT_MS = 3000;

/** Timeout (ms) for standard connection attempts. */
export const STANDARD_TIMEOUT_MS = 10000;

/** Default server port for music-porter server. */
export const DEFAULT_PORT = 5555;

/** Bonjour/mDNS service type for server discovery. */
export const BONJOUR_SERVICE_TYPE = '_music-porter._tcp';

/** Discovery browse duration (ms) before auto-stop. */
export const BONJOUR_BROWSE_TIMEOUT_MS = 10000;

/** USB drive polling interval (ms) for hotplug detection. */
export const DRIVE_POLL_INTERVAL_MS = 3000;

/** Application name used for config directory. */
export const APP_NAME = 'mporter-sync';

/** macOS volumes to exclude from USB detection. */
export const EXCLUDED_MAC_VOLUMES = ['Macintosh HD', 'Macintosh HD - Data'];

// ── CLI Exit Codes ──

export const EXIT_SUCCESS = 0;
export const EXIT_ERROR = 1;
export const EXIT_CONNECTION_FAILED = 2;
export const EXIT_AUTH_FAILED = 3;
export const EXIT_PARTIAL_FAILURE = 4;
export const EXIT_NO_SERVER = 5;

/** File extension suffix for partial downloads. */
export const TEMP_SUFFIX = '.tmp';

/** Bearer token prefix for Authorization header. */
export const AUTH_HEADER_PREFIX = 'Bearer';

/** Per-file download timeout (ms) — 5 minutes, generous for large files on slow USB. */
export const FILE_DOWNLOAD_TIMEOUT_MS = 300_000;

// ── Cookie Refresh ──

/** Apple Music login URL for embedded browser. */
export const APPLE_MUSIC_URL = 'https://music.apple.com';

/** Cookie domain for Apple Music authentication cookies. */
export const APPLE_COOKIE_DOMAIN = '.music.apple.com';

/** Name of the authentication cookie that proves a valid Apple Music session. */
export const APPLE_AUTH_COOKIE_NAME = 'media-user-token';

/** How often (ms) to poll for the auth cookie in the login window. */
export const COOKIE_POLL_INTERVAL_MS = 1000;

/** Maximum time (ms) to wait for the user to complete login before timeout. */
export const COOKIE_REFRESH_TIMEOUT_MS = 300_000;

/** Width (px) of the cookie refresh BrowserWindow. */
export const COOKIE_WINDOW_WIDTH = 1000;

/** Height (px) of the cookie refresh BrowserWindow. */
export const COOKIE_WINDOW_HEIGHT = 700;

/** Netscape cookie file header line. */
export const NETSCAPE_COOKIE_HEADER = '# Netscape HTTP Cookie File';

/** Domain suffix used to filter only Apple-related cookies. */
export const APPLE_DOMAIN_SUFFIX = 'apple.com';

/** Fallback expiry (seconds) for session cookies that lack an explicit expiration. */
export const SESSION_COOKIE_FALLBACK_S = 86400 * 365;

// ── Connection Health Check ──

/** How often (ms) to ping the server when connected, to detect unexpected disconnection. */
export const CONNECTION_HEALTH_CHECK_INTERVAL_MS = 30_000;

/** How often (ms) to attempt reconnection when the server was lost unexpectedly. */
export const CONNECTION_RECONNECT_INTERVAL_MS = 15_000;

/** Timeout (ms) for a single health-check ping. */
export const HEALTH_CHECK_TIMEOUT_MS = 5_000;

/** Timeout (ms) for the local URL probe during a dual-URL health check. */
export const HEALTH_CHECK_LOCAL_TIMEOUT_MS = 3_000;

/** Number of consecutive health-check failures before declaring the connection lost. */
export const HEALTH_CHECK_FAILURE_THRESHOLD = 2;

/** Maximum number of recent folder destinations to remember. */
export const MAX_RECENT_DESTINATIONS = 5;

// ── Local Cache (re-exported from cache module for backward compatibility) ──

export {
  CACHE_DIRNAME,
  CACHE_INDEX_FILENAME,
  DEFAULT_MAX_CACHE_BYTES,
  BACKGROUND_PREFETCH_INTERVAL_MS,
} from './cache/constants.js';
