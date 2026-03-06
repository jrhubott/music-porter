import { join } from 'node:path';
import { existsSync, mkdirSync } from 'node:fs';
import { CACHE_DIRNAME, METADATA_CACHE_FILENAME } from './constants.js';
import { loadJsonIndex, saveJsonIndex } from './cache-utils.js';
import type { CachedPlaylistData, MetadataCacheData } from './types.js';
import type { FileInfo } from '../types.js';

/** Current schema version for the metadata cache file. */
const METADATA_CACHE_VERSION = 1;

/**
 * Persistent cache for API response metadata (playlist file lists + ETags).
 *
 * Stores one JSON file per profile at <configDir>/cache/<profile>/metadata-cache.json.
 * Separate from the audio cache index (cache-index.json).
 */
export class MetadataCache {
  private readonly cachePath: string;
  private data: MetadataCacheData;

  constructor(configDir: string, profile: string) {
    const cacheDir = join(configDir, CACHE_DIRNAME, profile);
    if (!existsSync(cacheDir)) {
      mkdirSync(cacheDir, { recursive: true });
    }
    this.cachePath = join(cacheDir, METADATA_CACHE_FILENAME);
    this.data = loadJsonIndex<MetadataCacheData>(
      this.cachePath,
      { profile, version: METADATA_CACHE_VERSION, playlists: {} },
      (d) => d.profile === profile && d.version === METADATA_CACHE_VERSION,
    );
  }

  // ── Read ──

  /** Get cached playlist data, or null if not cached. */
  getPlaylistFiles(playlistKey: string): CachedPlaylistData | null {
    return this.data.playlists[playlistKey] ?? null;
  }

  /** Get list of playlist keys that have cached metadata. */
  getCachedPlaylists(): string[] {
    return Object.keys(this.data.playlists);
  }

  /** Get the cached ETag for a playlist, or null if not cached. */
  getETag(playlistKey: string): string | null {
    return this.data.playlists[playlistKey]?.etag ?? null;
  }

  // ── Write ──

  /** Store a playlist file list with its ETag. */
  storePlaylistFiles(
    playlistKey: string,
    files: FileInfo[],
    etag: string | null,
    name?: string,
  ): void {
    this.data.playlists[playlistKey] = {
      files,
      etag,
      playlistName: name,
      fileCount: files.length,
      cachedAt: new Date().toISOString(),
    };
    this.persist();
  }

  /** Remove cached data for a playlist. */
  removePlaylist(playlistKey: string): void {
    if (this.data.playlists[playlistKey]) {
      delete this.data.playlists[playlistKey];
      this.persist();
    }
  }

  /** Clear all cached metadata. */
  clearAll(): void {
    this.data.playlists = {};
    this.persist();
  }

  // ── Internal ──

  private persist(): void {
    saveJsonIndex(this.cachePath, this.data);
  }
}
