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

export interface Playlist {
  key: string;
  url: string;
  name: string;
  file_count?: number;
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
}

export interface FileListResponse {
  playlist: string;
  name?: string;
  file_count: number;
  files: FileInfo[];
}

export interface SyncPlaylistStatus {
  name: string;
  total_files: number;
  synced_files: number;
  new_files: number;
  is_new_playlist: boolean;
}

export interface SyncStatusDetail {
  sync_key: string;
  last_sync_at: number;
  playlists: SyncPlaylistStatus[];
  total_files: number;
  synced_files: number;
  new_files: number;
  new_playlists: number;
}

export interface SyncKeySummary {
  key_name: string;
  last_sync_at: number;
  file_count: number;
  playlist_count: number;
}

export interface SyncDestination {
  name: string;
  path: string;
  scheme: string;
  sync_key: string | null;
}

export interface SyncDestinationsResponse {
  destinations: SyncDestination[];
}

export interface ClientRecordResponse {
  ok: boolean;
  recorded: number;
}

export interface OkResponse {
  ok: boolean;
  error?: string;
}

// ── Sync Manifest ──

export interface SyncManifestPlaylist {
  files: Record<string, number>;
}

export interface SyncManifest {
  sync_key: string;
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
  syncKey: string;
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
  syncKey: string;
  copied: number;
  skipped: number;
  failed: number;
  aborted: boolean;
  durationMs: number;
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

// ── Config ──

export interface SyncPreferences {
  concurrency: number;
  autoSyncDrives: string[];
  ejectAfterSync: boolean;
  notifications: boolean;
}

export interface AppConfig {
  server: ServerConfig | null;
  preferences: SyncPreferences;
  profile?: string;
}
