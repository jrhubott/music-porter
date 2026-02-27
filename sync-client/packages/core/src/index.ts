// Types
export type {
  AppConfig,
  AuthValidateResponse,
  ClientRecordResponse,
  ConnectionState,
  ConnectionType,
  DiscoveredServer,
  DriveInfo,
  FileInfo,
  FileListResponse,
  OkResponse,
  Playlist,
  ServerConfig,
  ServerInfoResponse,
  SyncDestination,
  SyncDestinationsResponse,
  SyncKeySummary,
  SyncManifest,
  SyncManifestPlaylist,
  SyncPhase,
  SyncPlan,
  SyncPlanPlaylist,
  SyncPlaylistStatus,
  SyncPreferences,
  SyncProgress,
  SyncResult,
  SyncStatusDetail,
} from './types.js';

// Constants
export {
  APP_NAME,
  AUTH_HEADER_PREFIX,
  BONJOUR_BROWSE_TIMEOUT_MS,
  BONJOUR_SERVICE_TYPE,
  DEFAULT_CONCURRENCY,
  DEFAULT_PORT,
  DRIVE_POLL_INTERVAL_MS,
  EXCLUDED_MAC_VOLUMES,
  EXIT_AUTH_FAILED,
  EXIT_CONNECTION_FAILED,
  EXIT_ERROR,
  EXIT_NO_SERVER,
  EXIT_PARTIAL_FAILURE,
  EXIT_SUCCESS,
  LOCAL_TIMEOUT_MS,
  MANIFEST_FILENAME,
  STANDARD_TIMEOUT_MS,
  TEMP_SUFFIX,
  VERSION,
} from './constants.js';

// Errors
export {
  AuthError,
  ConfigError,
  ConnectionError,
  MPorterError,
  NotConfiguredError,
  ServerBusyError,
  ServerError,
  SyncError,
} from './errors.js';

// Platform
export { currentPlatform, getConfigDir, getExcludedVolumes, getUSBMountPaths } from './platform.js';
export type { Platform } from './platform.js';

// Progress
export type { LogCallback, ProgressCallback } from './progress.js';

// Classes
export { APIClient } from './api-client.js';
export { ConfigStore } from './config-store.js';
