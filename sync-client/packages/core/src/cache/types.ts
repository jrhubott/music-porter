// ── Cache Types ──

export interface CacheEntry {
  uuid: string;
  playlist: string;
  display_filename: string;
  size: number;
  cached_at: string;
  server_created_at?: string;
  server_updated_at?: string;
}

export interface CacheIndex {
  profile: string;
  entries: Record<string, CacheEntry>;
}

export interface PrefetchResult {
  downloaded: number;
  skipped: number;
  failed: number;
  capacityCapped: number;
  aborted: boolean;
  durationMs: number;
}

export interface PlaylistCacheStatus {
  playlistKey: string;
  total: number;
  cached: number;
  pinned: boolean;
}

// ── Metadata Cache ──

import type { FileInfo } from '../types.js';

export interface MetadataCacheData {
  profile: string;
  version: number;
  playlists: Record<string, CachedPlaylistData>;
}

export interface CachedPlaylistData {
  files: FileInfo[];
  etag: string | null;
  playlistName?: string;
  fileCount: number;
  cachedAt: string;
}

// ── Background Prefetch ──

export interface BackgroundPrefetchStatus {
  running: boolean;
  playlist?: string;
  progress?: { current: number; total: number };
  lastRunAt?: string;
  lastResult?: PrefetchResult;
}
