/** Sync client version — bumped independently from the server. */
export const VERSION = '1.1.0';

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

/** Sync key prefix for USB drive destinations. */
export const USB_SYNC_KEY_PREFIX = 'usbkey-';

/** Sync key prefix for generic client destinations. */
export const CLIENT_SYNC_KEY_PREFIX = 'client-';

/** Per-file download timeout (ms) — 5 minutes, generous for large files on slow USB. */
export const FILE_DOWNLOAD_TIMEOUT_MS = 300_000;
