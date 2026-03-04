// ── Server Connection ──

export interface ServerConfig {
  name: string;
  localURL: string;
  externalURL?: string;
}

export type ConnectionType = 'local' | 'external';

export interface ConnectionState {
  connected: boolean;
  type?: ConnectionType;
  activeURL?: string;
  serverName?: string;
  serverVersion?: string;
}

export interface HealthCheckResult {
  reachable: boolean;
  type?: ConnectionType;
  typeChanged: boolean;
}

// ── API Responses ──

export interface AuthValidateResponse {
  valid: boolean;
  version: string;
  server_name: string;
  api_version: number;
}

export interface ServerInfoResponse {
  name: string;
  version: string;
  platform: string;
  profiles: string[];
  api_version: number;
  external_url?: string;
}

export type FreshnessLevel = 'current' | 'recent' | 'stale' | 'outdated';

export interface Playlist {
  key: string;
  url: string;
  name: string;
  file_count?: number;
  size_bytes?: number;
  duration_s?: number;
  freshness?: FreshnessLevel;
}

export interface FileInfo {
  filename: string;
  display_filename?: string;
  output_subdir?: string;
  size: number;
  duration: number;
  title: string;
  artist: string;
  album: string;
  uuid: string;
  has_cover_art: boolean;
  synced_to?: string[];
  created_at?: number;
  updated_at?: number;
}

export interface FileListResponse {
  playlist: string;
  name?: string;
  file_count: number;
  files: FileInfo[];
}

export interface RemovedTrack {
  id: number;
  uuid: string;
  playlist: string;
  title: string;
  artist: string;
  album: string;
  display_filename: string;
  removed_at: number;
}

export interface RemovedFilesResponse {
  removed_tracks: RemovedTrack[];
}

export interface SyncPlaylistStatus {
  name: string;
  total_files: number;
  synced_files: number;
  new_files: number;
  is_new_playlist: boolean;                                      // kept for compat — now timestamp-based
  sync_status?: 'synced' | 'new' | 'behind' | 'skipped';        // new in server v2.38.13+
}

export interface SyncStatusDetail {
  destinations: string[];
  last_sync_at: number;
  playlists: SyncPlaylistStatus[];
  total_files: number;
  synced_files: number;
  new_files: number;
  new_playlists: number;
  playlist_prefs: string[] | null;
}

export interface SyncDestination {
  name: string;
  path: string;
  type: string;
  available: boolean;
  linked_destinations: string[];
  playlist_prefs: string[] | null;
}

export interface ResolveDestinationResponse {
  destination: SyncDestination;
  created: boolean;
  sync_status: SyncStatusDetail | null;
}

export interface SyncDestinationsResponse {
  destinations: SyncDestination[];
}

export interface ClientRecordResponse {
  ok: boolean;
  recorded: number;
}

export interface AboutResponse {
  version: string;
  release_notes: string;
}

export interface OkResponse {
  ok: boolean;
  error?: string;
}

export interface LinkDestinationResponse {
  ok: boolean;
  merge_stats?: { records_moved: number; records_merged: number; source_deleted: boolean };
  created?: boolean;
}

export interface ResetTrackingResponse {
  reset: boolean;
  files_cleared: number;
}

export interface SyncStatusSummary {
  destinations: string[];
  last_sync_at: number;
  total_files: number;
  synced_files: number;
  new_files: number;
  new_playlists: number;
  playlist_prefs?: string[] | null;
}

// ── Sync Manifest ──

export interface SyncManifestPlaylist {
  files: Record<string, number>;
}

export interface SyncManifest {
  destination_name: string;
  server_origin: string;
  last_sync_at: string;
  playlists: Record<string, SyncManifestPlaylist>;
}

// ── Drive Detection ──

export interface DriveInfo {
  name: string;
  path: string;
  freeSpace?: number;
}

// ── Sync Engine ──

export type SyncPhase = 'discovering' | 'syncing' | 'complete' | 'aborted';

export interface SyncProgress {
  phase: SyncPhase;
  playlist?: string;
  file?: string;
  subdir?: string;
  processed: number;
  total: number;
  copied: number;
  skipped: number;
  failed: number;
}

export interface SyncPlan {
  destinationName: string;
  playlists: SyncPlanPlaylist[];
  totalFiles: number;
}

export interface SyncPlanPlaylist {
  key: string;
  files: FileInfo[];
  toDownload: number;
  toSkip: number;
}

export interface SyncResult {
  destinationName: string;
  copied: number;
  skipped: number;
  failed: number;
  aborted: boolean;
  durationMs: number;
  destError?: string;
}

// ── Discovery ──

export interface DiscoveredServer {
  name: string;
  host: string;
  port: number;
  version?: string;
  platform?: string;
  apiVersion?: number;
}

// ── Profile ──

export interface ProfileInfo {
  description: string;
  id3_title: string;
  id3_artist: string;
  id3_album: string;
  id3_genre: string;
  id3_extra: Record<string, string>;
  filename: string;
  directory: string;
  id3_versions: string[];
  artwork_size: number;
  usb_dir: string;
}

export interface SettingsResponse {
  settings: Record<string, unknown>;
  profiles: Record<string, ProfileInfo>;
  quality_presets: string[];
}

// ── Cookies ──

export interface CookieStatus {
  valid: boolean;
  exists: boolean;
  reason: string;
  days_remaining: number | null;
}

export interface CookieUploadResponse {
  valid: boolean;
  reason: string;
  days_remaining: number | null;
}

// ── Cache (re-exported from cache module for backward compatibility) ──

export type {
  CacheEntry,
  CacheIndex,
  PrefetchResult,
  PlaylistCacheStatus,
  BackgroundPrefetchStatus,
} from './cache/types.js';

// ── Pipeline ──

export type PipelineEventType = 'log' | 'progress' | 'overall_progress' | 'done' | 'heartbeat';

export interface PipelineProgress {
  type: PipelineEventType;
  // log events
  level?: string;    // INFO, OK, WARN, ERROR, SKIP
  message?: string;
  // progress events
  current?: number;
  total?: number;
  percent?: number;
  stage?: string;
  // done events
  status?: string;   // completed, failed, cancelled
  result?: Record<string, unknown>;
  error?: string;
}

export interface PipelineStartResult {
  task_id: string;
}

// ── Window State ──

export interface WindowState {
  x: number;
  y: number;
  width: number;
  height: number;
  isMaximized: boolean;
}

// ── Config ──

export interface SyncPreferences {
  concurrency: number;
  autoSyncDrives: string[];
  ejectAfterSync: boolean;
  notifications: boolean;
  pinnedPlaylists: string[];
  maxCacheBytes: number;
  autoPinNewPlaylists: boolean;
  unpinnedPlaylists: string[];
  recentDestinations: string[];
  cleanDestination: boolean;
}

export interface AppConfig {
  server: ServerConfig | null;
  preferences: SyncPreferences;
  profile?: string;
  windowState?: WindowState;
}
