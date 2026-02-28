import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
  unlinkSync,
  rmSync,
  statSync,
  readdirSync,
  copyFileSync,
  createWriteStream,
} from 'node:fs';
import { join, dirname } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { CACHE_DIRNAME, CACHE_INDEX_FILENAME, TEMP_SUFFIX } from './constants.js';
import type { CacheEntry, CacheIndex, FileInfo, PlaylistCacheStatus } from './types.js';

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
    this.index = this.loadIndex();
  }

  // ── Cache Hit ──

  /** Returns cached file path if the file is cached, null otherwise. */
  isCached(uuid: string): string | null {
    const entry = this.index.entries[uuid];
    if (!entry) return null;
    const filePath = this.entryPath(entry);
    if (!existsSync(filePath)) {
      delete this.index.entries[uuid];
      this.saveIndex();
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
    if (!existsSync(fileDir)) {
      mkdirSync(fileDir, { recursive: true });
    }
    const filePath = join(fileDir, displayName);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      const nodeStream = Readable.fromWeb(body as import('node:stream/web').ReadableStream);
      const writeStream = createWriteStream(tmpPath);
      await pipeline(nodeStream, writeStream);
      renameSync(tmpPath, filePath);

      const stat = statSync(filePath);
      const entry: CacheEntry = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: stat.size,
        cached_at: new Date().toISOString(),
      };
      if (serverCreatedAt !== undefined) {
        entry.server_created_at = new Date(serverCreatedAt * 1000).toISOString();
      }
      if (serverUpdatedAt !== undefined) {
        entry.server_updated_at = new Date(serverUpdatedAt * 1000).toISOString();
      }
      this.index.entries[file.uuid] = entry;
      this.saveIndex();
    } catch {
      try {
        if (existsSync(tmpPath)) unlinkSync(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
      // Non-fatal — cache write failures don't break sync
    }
  }

  /** Copy an existing file into cache and update the index. */
  storeFromFile(
    file: FileInfo,
    playlistKey: string,
    sourcePath: string,
    serverCreatedAt?: number,
    serverUpdatedAt?: number,
  ): void {
    const displayName = file.display_filename || file.filename;
    const fileDir = join(this.cacheDir, playlistKey);
    if (!existsSync(fileDir)) {
      mkdirSync(fileDir, { recursive: true });
    }
    const filePath = join(fileDir, displayName);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      copyFileSync(sourcePath, tmpPath);
      renameSync(tmpPath, filePath);

      const stat = statSync(filePath);
      const entry: CacheEntry = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: stat.size,
        cached_at: new Date().toISOString(),
      };
      if (serverCreatedAt !== undefined) {
        entry.server_created_at = new Date(serverCreatedAt * 1000).toISOString();
      }
      if (serverUpdatedAt !== undefined) {
        entry.server_updated_at = new Date(serverUpdatedAt * 1000).toISOString();
      }
      this.index.entries[file.uuid] = entry;
      this.saveIndex();
    } catch {
      try {
        if (existsSync(tmpPath)) unlinkSync(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  // ── Copy Out ──

  /** Copy a cached file to a destination path. Returns true on success. */
  copyToDestination(uuid: string, destPath: string): boolean {
    const cachedPath = this.isCached(uuid);
    if (!cachedPath) return false;

    try {
      const destDir = dirname(destPath);
      if (!existsSync(destDir)) {
        mkdirSync(destDir, { recursive: true });
      }
      const tmpPath = destPath + TEMP_SUFFIX;
      copyFileSync(cachedPath, tmpPath);
      renameSync(tmpPath, destPath);
      return true;
    } catch {
      return false;
    }
  }

  /** Add an index entry for a file that already exists in cache (no copy). */
  recordEntry(file: FileInfo, playlistKey: string): void {
    const displayName = file.display_filename || file.filename;
    const filePath = join(this.cacheDir, playlistKey, displayName);
    if (!existsSync(filePath)) return;

    try {
      const stat = statSync(filePath);
      this.index.entries[file.uuid] = {
        uuid: file.uuid,
        playlist: playlistKey,
        display_filename: displayName,
        size: stat.size,
        cached_at: new Date().toISOString(),
      };
      this.saveIndex();
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
    if (removed > 0) this.saveIndex();
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

    this.saveIndex();
    this.removeEmptyDirs();
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
      this.saveIndex();
      this.removeEmptyDirs();
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
      this.saveIndex();
      this.removeEmptyDirs();
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
    this.saveIndex();
    this.removeEmptyDirs();
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
    // Recreate the cache dir so saveIndex doesn't fail
    mkdirSync(this.cacheDir, { recursive: true });
    this.saveIndex();
  }

  // ── Internal ──

  private entryPath(entry: CacheEntry): string {
    return join(this.cacheDir, entry.playlist, entry.display_filename);
  }

  private loadIndex(): CacheIndex {
    try {
      if (!existsSync(this.indexPath)) {
        return { profile: this.profile, entries: {} };
      }
      const raw = readFileSync(this.indexPath, 'utf-8');
      const parsed = JSON.parse(raw) as CacheIndex;
      if (parsed.profile !== this.profile) {
        return { profile: this.profile, entries: {} };
      }
      return parsed;
    } catch {
      // Corrupt index — start fresh
      return { profile: this.profile, entries: {} };
    }
  }

  private saveIndex(): void {
    try {
      if (!existsSync(this.cacheDir)) {
        mkdirSync(this.cacheDir, { recursive: true });
      }
      const tmpPath = this.indexPath + TEMP_SUFFIX;
      writeFileSync(tmpPath, JSON.stringify(this.index, null, 2), 'utf-8');
      renameSync(tmpPath, this.indexPath);
    } catch {
      // Non-fatal — cache metadata loss is recoverable via pruneStaleEntries
    }
  }

  /** Remove empty playlist directories under the cache dir. */
  private removeEmptyDirs(): void {
    try {
      const entries = readdirSync(this.cacheDir, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        const dirPath = join(this.cacheDir, entry.name);
        try {
          const contents = readdirSync(dirPath);
          if (contents.length === 0) {
            rmSync(dirPath, { recursive: true });
          }
        } catch {
          // Ignore
        }
      }
    } catch {
      // Ignore
    }
  }
}
