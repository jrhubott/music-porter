import {
  existsSync,
  mkdirSync,
  unlinkSync,
  rmSync,
  createWriteStream,
} from 'node:fs';
import { copyFile, rename, stat, mkdir, unlink } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { CACHE_DIRNAME, CACHE_INDEX_FILENAME } from './constants.js';
import { loadJsonIndex, saveJsonIndex, removeEmptyDirs } from './cache-utils.js';
import type { CacheEntry, CacheIndex, PlaylistCacheStatus } from './types.js';
import type { FileInfo } from '../types.js';

const TEMP_SUFFIX = '.tmp';

/**
 * Local audio file cache — stores server-tagged files by profile.
 *
 * Layout: <configDir>/cache/<profile>/<playlist>/<display_filename>
 * Index:  <configDir>/cache/<profile>/cache-index.json
 */
export class CacheManager {
  private readonly cacheDir: string;
  private readonly indexPath: string;
  private readonly profile: string;
  private index: CacheIndex;

  constructor(configDir: string, profile: string) {
    this.profile = profile;
    this.cacheDir = join(configDir, CACHE_DIRNAME, profile);
    this.indexPath = join(this.cacheDir, CACHE_INDEX_FILENAME);
    this.index = loadJsonIndex<CacheIndex>(
      this.indexPath,
      { profile: this.profile, entries: {} },
      (data) => data.profile === this.profile,
    );
  }

  // ── Cache Hit ──

  /** Returns cached file path if the file is cached, null otherwise. */
  isCached(uuid: string): string | null {
    const entry = this.index.entries[uuid];
    if (!entry) return null;
    const filePath = this.entryPath(entry);
    if (!existsSync(filePath)) {
      delete this.index.entries[uuid];
      this.persistIndex();
      return null;
    }
    return filePath;
  }

  // ── Store ──

  /** Write a ReadableStream to cache and update the index. */
  async storeStream(
    file: FileInfo,
    playlistKey: string,
    body: ReadableStream,
    serverCreatedAt?: number,
    serverUpdatedAt?: number,
  ): Promise<void> {
    const displayName = file.display_filename || file.filename;
    const fileDir = join(this.cacheDir, playlistKey);
    await mkdir(fileDir, { recursive: true });
    const filePath = join(fileDir, displayName);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      const nodeStream = Readable.fromWeb(body as import('node:stream/web').ReadableStream);
      const writeStream = createWriteStream(tmpPath);
      await pipeline(nodeStream, writeStream);
      await rename(tmpPath, filePath);

      const st = await stat(filePath);
      const entry: CacheEntry = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: st.size,
        cached_at: new Date().toISOString(),
      };
      if (serverCreatedAt !== undefined) {
        entry.server_created_at = new Date(serverCreatedAt * 1000).toISOString();
      }
      if (serverUpdatedAt !== undefined) {
        entry.server_updated_at = new Date(serverUpdatedAt * 1000).toISOString();
      }
      this.index.entries[file.uuid] = entry;
      this.persistIndex();
    } catch {
      try {
        await unlink(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
      // Non-fatal — cache write failures don't break sync
    }
  }

  /** Copy an existing file into cache and update the index. */
  async storeFromFile(
    file: FileInfo,
    playlistKey: string,
    sourcePath: string,
    serverCreatedAt?: number,
    serverUpdatedAt?: number,
  ): Promise<void> {
    const displayName = file.display_filename || file.filename;
    const fileDir = join(this.cacheDir, playlistKey);
    await mkdir(fileDir, { recursive: true });
    const filePath = join(fileDir, displayName);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      await copyFile(sourcePath, tmpPath);
      await rename(tmpPath, filePath);

      const st = await stat(filePath);
      const entry: CacheEntry = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: st.size,
        cached_at: new Date().toISOString(),
      };
      if (serverCreatedAt !== undefined) {
        entry.server_created_at = new Date(serverCreatedAt * 1000).toISOString();
      }
      if (serverUpdatedAt !== undefined) {
        entry.server_updated_at = new Date(serverUpdatedAt * 1000).toISOString();
      }
      this.index.entries[file.uuid] = entry;
      this.persistIndex();
    } catch {
      try {
        await unlink(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  // ── Copy Out ──

  /** Copy a cached file to a destination path. Returns true on success. */
  async copyToDestination(uuid: string, destPath: string): Promise<boolean> {
    const cachedPath = this.isCached(uuid);
    if (!cachedPath) return false;

    try {
      const destDir = dirname(destPath);
      await mkdir(destDir, { recursive: true });
      const tmpPath = destPath + TEMP_SUFFIX;
      await copyFile(cachedPath, tmpPath);
      await rename(tmpPath, destPath);
      return true;
    } catch {
      return false;
    }
  }

  /** Add an index entry for a file that already exists in cache (no copy). */
  async recordEntry(file: FileInfo, playlistKey: string): Promise<void> {
    const displayName = file.display_filename || file.filename;
    const filePath = join(this.cacheDir, playlistKey, displayName);
    if (!existsSync(filePath)) return;

    try {
      const st = await stat(filePath);
      this.index.entries[file.uuid] = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: st.size,
        cached_at: new Date().toISOString(),
      };
      this.persistIndex();
    } catch {
      // Non-fatal
    }
  }

  // ── Status ──

  /** Total size of all cached files in bytes. */
  getTotalSize(): number {
    let total = 0;
    for (const entry of Object.values(this.index.entries)) {
      total += entry.size;
    }
    return total;
  }

  /** Returns true if the cache has any entries. */
  hasData(): boolean {
    return Object.keys(this.index.entries).length > 0;
  }

  /** Returns list of playlist keys that have cached entries. */
  getCachedPlaylists(): string[] {
    const playlists = new Set<string>();
    for (const entry of Object.values(this.index.entries)) {
      playlists.add(entry.playlist);
    }
    return [...playlists];
  }

  /** Returns all cached entries for a playlist. */
  getCachedFileInfos(playlistKey: string): CacheEntry[] {
    return Object.values(this.index.entries).filter((e) => e.playlist === playlistKey);
  }

  /** Build cache status for a playlist. */
  getPlaylistCacheStatus(key: string, totalFiles: number, pinned: boolean): PlaylistCacheStatus {
    const cached = Object.values(this.index.entries).filter((e) => e.playlist === key).length;
    return { playlistKey: key, total: totalFiles, cached, pinned };
  }

  // ── Removal ──

  /**
   * Remove a cached entry by UUID — deletes the audio file from disk and removes
   * the index entry. Returns true if the entry existed, false if not found.
   */
  removeEntry(uuid: string): boolean {
    const entry = this.index.entries[uuid];
    if (!entry) return false;
    const filePath = this.entryPath(entry);
    try {
      if (existsSync(filePath)) {
        unlinkSync(filePath);
      }
    } catch {
      // Best-effort deletion
    }
    delete this.index.entries[uuid];
    this.persistIndex();
    removeEmptyDirs(this.cacheDir);
    return true;
  }

  // ── Staleness ──

  /**
   * Returns true if the cached file is stale — i.e. the server's updated_at
   * is newer than what we have cached. This means the file was re-converted
   * or metadata changed and needs re-downloading.
   */
  isStale(uuid: string, serverUpdatedAt?: number): boolean {
    if (serverUpdatedAt === undefined) return false;
    const entry = this.index.entries[uuid];
    if (!entry || !entry.server_updated_at) return false;
    const cachedUpdatedAt = new Date(entry.server_updated_at).getTime();
    const serverTime = Math.floor(serverUpdatedAt * 1000);
    return serverTime > cachedUpdatedAt;
  }

  // ── Eviction ──

  /** Remove index entries whose files are missing from disk. Returns count removed. */
  pruneStaleEntries(): number {
    let removed = 0;
    for (const [uuid, entry] of Object.entries(this.index.entries)) {
      const filePath = this.entryPath(entry);
      if (!existsSync(filePath)) {
        delete this.index.entries[uuid];
        removed++;
      }
    }
    if (removed > 0) this.persistIndex();
    return removed;
  }

  /** Evict oldest server files until total size is under maxBytes. Returns bytes freed.
   *  When pinnedPlaylists is provided, unpinned playlists are evicted first. */
  evictToLimit(maxBytes: number, pinnedPlaylists?: Set<string>): number {
    let totalSize = this.getTotalSize();
    if (totalSize <= maxBytes) return 0;

    // Sort: unpinned before pinned (when set provided), then oldest first.
    // Fall back to cached_at for entries without server timestamps (backward compat).
    const sorted = Object.values(this.index.entries).sort((a, b) => {
      if (pinnedPlaylists) {
        const aPinned = pinnedPlaylists.has(a.playlist) ? 1 : 0;
        const bPinned = pinnedPlaylists.has(b.playlist) ? 1 : 0;
        if (aPinned !== bPinned) return aPinned - bPinned;
      }
      const aTime = a.server_created_at
        ? new Date(a.server_created_at).getTime()
        : new Date(a.cached_at).getTime();
      const bTime = b.server_created_at
        ? new Date(b.server_created_at).getTime()
        : new Date(b.cached_at).getTime();
      return aTime - bTime;
    });

    let freed = 0;
    for (const entry of sorted) {
      if (totalSize <= maxBytes) break;
      const filePath = this.entryPath(entry);
      try {
        if (existsSync(filePath)) {
          unlinkSync(filePath);
          freed += entry.size;
          totalSize -= entry.size;
        }
      } catch {
        // Best-effort eviction
      }
      delete this.index.entries[entry.uuid];
    }

    this.persistIndex();
    removeEmptyDirs(this.cacheDir);
    return freed;
  }

  /**
   * Evict only unpinned files until targetBytes have been freed (or no unpinned
   * files remain). Returns bytes actually freed. Used mid-prefetch to make room
   * for pinned content without waiting for the post-download eviction pass.
   */
  evictUnpinnedBytes(targetBytes: number, pinnedPlaylists: Set<string>): number {
    // Only consider entries from unpinned playlists
    const unpinned = Object.values(this.index.entries).filter(
      (e) => !pinnedPlaylists.has(e.playlist),
    );
    if (unpinned.length === 0) return 0;

    // Sort oldest first (same timestamp logic as evictToLimit)
    unpinned.sort((a, b) => {
      const aTime = a.server_created_at
        ? new Date(a.server_created_at).getTime()
        : new Date(a.cached_at).getTime();
      const bTime = b.server_created_at
        ? new Date(b.server_created_at).getTime()
        : new Date(b.cached_at).getTime();
      return aTime - bTime;
    });

    let freed = 0;
    for (const entry of unpinned) {
      if (freed >= targetBytes) break;
      const filePath = this.entryPath(entry);
      try {
        if (existsSync(filePath)) {
          unlinkSync(filePath);
          freed += entry.size;
        }
      } catch {
        // Best-effort eviction
      }
      delete this.index.entries[entry.uuid];
    }

    if (freed > 0) {
      this.persistIndex();
      removeEmptyDirs(this.cacheDir);
    }
    return freed;
  }

  /**
   * Evict oldest files regardless of pin status until targetBytes have been
   * freed. Skips protectedUuids (files downloaded this session) to prevent a
   * download-evict-redownload cycle. Returns bytes actually freed.
   */
  evictOldestBytes(targetBytes: number, protectedUuids: Set<string>): number {
    const evictable = Object.values(this.index.entries).filter(
      (e) => !protectedUuids.has(e.uuid),
    );
    if (evictable.length === 0) return 0;

    // Sort oldest first
    evictable.sort((a, b) => {
      const aTime = a.server_created_at
        ? new Date(a.server_created_at).getTime()
        : new Date(a.cached_at).getTime();
      const bTime = b.server_created_at
        ? new Date(b.server_created_at).getTime()
        : new Date(b.cached_at).getTime();
      return aTime - bTime;
    });

    let freed = 0;
    for (const entry of evictable) {
      if (freed >= targetBytes) break;
      const filePath = this.entryPath(entry);
      try {
        if (existsSync(filePath)) {
          unlinkSync(filePath);
          freed += entry.size;
        }
      } catch {
        // Best-effort eviction
      }
      delete this.index.entries[entry.uuid];
    }

    if (freed > 0) {
      this.persistIndex();
      removeEmptyDirs(this.cacheDir);
    }
    return freed;
  }

  /** Delete all cached files for a playlist. */
  clearPlaylist(playlistKey: string): void {
    const uuids = Object.entries(this.index.entries)
      .filter(([, e]) => e.playlist === playlistKey)
      .map(([uuid]) => uuid);

    for (const uuid of uuids) {
      const entry = this.index.entries[uuid]!;
      const filePath = this.entryPath(entry);
      try {
        if (existsSync(filePath)) unlinkSync(filePath);
      } catch {
        // Best-effort
      }
      delete this.index.entries[uuid];
    }
    this.persistIndex();
    removeEmptyDirs(this.cacheDir);
  }

  /** Delete entire profile cache. */
  clearAll(): void {
    try {
      if (existsSync(this.cacheDir)) {
        rmSync(this.cacheDir, { recursive: true, force: true });
      }
    } catch {
      // Best-effort
    }
    this.index = { profile: this.profile, entries: {} };
    // Recreate the cache dir so persistIndex doesn't fail
    mkdirSync(this.cacheDir, { recursive: true });
    this.persistIndex();
  }

  // ── Internal ──

  private entryPath(entry: CacheEntry): string {
    return join(this.cacheDir, entry.playlist, entry.display_filename);
  }

  private persistIndex(): void {
    saveJsonIndex(this.indexPath, this.index);
  }
}
