// Types
export type {
  AboutResponse,
  AppConfig,
  AuthValidateResponse,
  ClientRecordResponse,
  ConnectionState,
  ConnectionType,
  HealthCheckResult,
  CookieStatus,
  CookieUploadResponse,
  DiscoveredServer,
  DriveInfo,
  FileInfo,
  FileListResponse,
  FreshnessLevel,
  LinkDestinationResponse,
  OkResponse,
  PipelineEventType,
  PipelineProgress,
  PipelineStartResult,
  Playlist,
  ProfileInfo,
  PruneResponse,
  ResolveDestinationResponse,
  ServerConfig,
  ServerInfoResponse,
  SettingsResponse,
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
  SyncStatusSummary,
  WindowState,
} from './types.js';

// Cache module (types, constants, classes)
export type {
  CacheEntry,
  CacheIndex,
  CachedPlaylistData,
  MetadataCacheData,
  PrefetchResult,
  PlaylistCacheStatus,
  BackgroundPrefetchStatus,
} from './cache/index.js';
export {
  CACHE_DIRNAME,
  CACHE_INDEX_FILENAME,
  DEFAULT_MAX_CACHE_BYTES,
  BACKGROUND_PREFETCH_INTERVAL_MS,
  METADATA_CACHE_FILENAME,
  CacheManager,
  MetadataCache,
  PrefetchEngine,
  loadJsonIndex,
  saveJsonIndex,
  removeEmptyDirs,
  atomicCopyFile,
} from './cache/index.js';
export type { PrefetchOptions } from './cache/index.js';

// Constants
export {
  APP_NAME,
  APPLE_AUTH_COOKIE_NAME,
  APPLE_COOKIE_DOMAIN,
  APPLE_DOMAIN_SUFFIX,
  APPLE_MUSIC_URL,
  AUTH_HEADER_PREFIX,
  BONJOUR_BROWSE_TIMEOUT_MS,
  BONJOUR_SERVICE_TYPE,
  CONNECTION_HEALTH_CHECK_INTERVAL_MS,
  CONNECTION_RECONNECT_INTERVAL_MS,
  COOKIE_POLL_INTERVAL_MS,
  COOKIE_REFRESH_TIMEOUT_MS,
  COOKIE_WINDOW_HEIGHT,
  COOKIE_WINDOW_WIDTH,
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
  HEALTH_CHECK_FAILURE_THRESHOLD,
  HEALTH_CHECK_LOCAL_TIMEOUT_MS,
  HEALTH_CHECK_TIMEOUT_MS,
  LOCAL_TIMEOUT_MS,
  MANIFEST_FILENAME,
  MAX_RECENT_DESTINATIONS,
  NETSCAPE_COOKIE_HEADER,
  SESSION_COOKIE_FALLBACK_S,
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
export { SyncEngine } from './sync-engine.js';
export type { SyncOptions } from './sync-engine.js';
export { DriveManager } from './drive-manager.js';
export type { DriveChangeCallback } from './drive-manager.js';
export { ServerDiscovery } from './discovery.js';
export type { DiscoveryCallback } from './discovery.js';

// Manifest utilities
export {
  readManifest,
  writeManifest,
  getManifestFiles,
  createManifest,
  updateManifestPlaylist,
} from './manifest.js';
