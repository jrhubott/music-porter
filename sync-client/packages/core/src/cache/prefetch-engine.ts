import { DEFAULT_CONCURRENCY, FILE_DOWNLOAD_TIMEOUT_MS } from '../constants.js';
import type { APIClient } from '../api-client.js';
import type { CacheManager } from './cache-manager.js';
import type { MetadataCache } from './metadata-cache.js';
import type { FileInfo } from '../types.js';
import type { PrefetchResult } from './types.js';
import type { LogCallback, ProgressCallback } from '../progress.js';

export interface PrefetchOptions {
  /** Playlist keys to prefetch. If empty, uses all pinned playlists. */
  playlists: string[];
  /** Output profile name for server-tagged downloads. */
  profile?: string;
  /** Number of parallel downloads. */
  concurrency?: number;
  /** Maximum cache size in bytes — runs eviction at end. 0 = unlimited. */
  maxCacheBytes?: number;
  /** Set of pinned playlist keys — used for eviction priority (unpinned evicted first). */
  pinnedPlaylists?: Set<string>;
  /** AbortSignal for cancellation. */
  signal?: AbortSignal;
  /** Progress callback. */
  onProgress?: ProgressCallback;
  /** Log callback. */
  onLog?: LogCallback;
  /** Optional metadata cache for ETag-based conditional requests. */
  metadataCache?: MetadataCache;
}

/**
 * Downloads pinned playlist files to the local cache (not to a destination).
 * Uses the same worker-pool concurrency pattern as SyncEngine.
 */
export class PrefetchEngine {
  private readonly client: APIClient;
  private readonly cacheManager: CacheManager;

  constructor(client: APIClient, cacheManager: CacheManager) {
    this.client = client;
    this.cacheManager = cacheManager;
  }

  async prefetch(options: PrefetchOptions): Promise<PrefetchResult> {
    const startTime = Date.now();
    const concurrency = options.concurrency ?? DEFAULT_CONCURRENCY;
    const log = options.onLog ?? (() => {});
    const onProgress = options.onProgress ?? (() => {});

    // Prune stale entries before starting
    const pruned = this.cacheManager.pruneStaleEntries();
    if (pruned > 0) {
      log('info', `Pruned ${pruned} stale cache entries`);
    }

    // Discover files for all playlists
    interface PlaylistFiles {
      key: string;
      files: FileInfo[];
    }
    const playlistFileList: PlaylistFiles[] = [];
    let grandTotal = 0;

    for (const key of options.playlists) {
      if (options.signal?.aborted) break;
      try {
        const response = await this.client.getFiles(key, false, options.profile, options.metadataCache);
        playlistFileList.push({ key, files: response.files });
        grandTotal += response.files.length;
      } catch (err) {
        log('warn', `Skipping playlist "${key}": ${err}`);
      }
    }

    const hasLimit = options.maxCacheBytes !== undefined && options.maxCacheBytes > 0;
    const maxCacheBytes = options.maxCacheBytes ?? 0;

    // Pre-filter: determine which files would be evicted anyway due to capacity
    const capacityExcluded = new Set<string>();

    if (hasLimit) {
      // Deduplicate server files by UUID (a file may appear in multiple playlists)
      const seenUuids = new Set<string>();
      const allFiles: { uuid: string; size: number; createdAt: number }[] = [];
      for (const { files } of playlistFileList) {
        for (const file of files) {
          if (!seenUuids.has(file.uuid)) {
            seenUuids.add(file.uuid);
            allFiles.push({
              uuid: file.uuid,
              size: file.size,
              createdAt: file.created_at ?? 0,
            });
          }
        }
      }

      // Sort newest first (inverse of eviction order)
      allFiles.sort((a, b) => b.createdAt - a.createdAt);

      // Files whose cumulative size exceeds the limit would be evicted anyway
      let cumulative = 0;
      for (const f of allFiles) {
        cumulative += f.size;
        if (cumulative > maxCacheBytes) {
          capacityExcluded.add(f.uuid);
        }
      }
    }

    // Filter out already-cached files and capacity-excluded files
    const toDownload: { key: string; file: FileInfo }[] = [];
    let totalSkipped = 0;
    let capacityCapped = 0;

    for (const { key, files } of playlistFileList) {
      for (const file of files) {
        if (capacityExcluded.has(file.uuid)) {
          capacityCapped++;
          continue;
        }
        const cached = this.cacheManager.isCached(file.uuid);
        const stale = cached && this.cacheManager.isStale(file.uuid, file.updated_at);
        if (cached && !stale) {
          totalSkipped++;
        } else {
          toDownload.push({ key, file });
        }
      }
    }

    if (hasLimit) {
      const currentSize = this.cacheManager.getTotalSize();
      const available = maxCacheBytes - currentSize;
      log('info', `Cache: ${formatBytes(currentSize)} used / ${formatBytes(maxCacheBytes)} limit (${formatBytes(Math.max(0, available))} available)`);
    }

    log('info', `Prefetch: ${toDownload.length} to download, ${totalSkipped} already cached` + (capacityCapped > 0 ? `, ${capacityCapped} exceeded cache capacity` : ''));

    onProgress({
      phase: 'syncing',
      processed: totalSkipped + capacityCapped,
      total: grandTotal,
      copied: 0,
      skipped: totalSkipped,
      failed: 0,
    });

    // Download with concurrency limit — stop when cache is full
    let downloaded = 0;
    let failed = 0;
    let processed = totalSkipped + capacityCapped;
    let aborted = false;
    let capacityReached = false;
    let index = 0;
    const downloadedUuids = new Set<string>();

    const worker = async () => {
      while (index < toDownload.length) {
        if (options.signal?.aborted) {
          aborted = true;
          return;
        }
        if (capacityReached) {
          return;
        }
        const item = toDownload[index++]!;
        const success = await this.downloadToCache(item.key, item.file, options.profile, options.signal, log);
        processed++;
        if (success) {
          downloaded++;
          downloadedUuids.add(item.file.uuid);
          // Check if cache is now full — try eviction to make room
          if (hasLimit && this.cacheManager.getTotalSize() >= maxCacheBytes) {
            // Step 1: evict unpinned files first (cheapest to lose)
            if (options.pinnedPlaylists && options.pinnedPlaylists.size > 0) {
              let overage = this.cacheManager.getTotalSize() - maxCacheBytes;
              const freed = this.cacheManager.evictUnpinnedBytes(overage, options.pinnedPlaylists);
              if (freed > 0) {
                log('info', `Evicted ${formatBytes(freed)} of unpinned cache to make room`);
              }
            }
            // Step 2: if still over, evict oldest files (skip this session's downloads)
            if (this.cacheManager.getTotalSize() >= maxCacheBytes) {
              const overage = this.cacheManager.getTotalSize() - maxCacheBytes;
              const freed = this.cacheManager.evictOldestBytes(overage, downloadedUuids);
              if (freed > 0) {
                log('info', `Evicted ${formatBytes(freed)} of oldest cache to make room`);
              }
            }
            // After all eviction attempts, check if still over limit
            if (this.cacheManager.getTotalSize() >= maxCacheBytes) {
              capacityReached = true;
              const remaining = toDownload.length - index;
              if (remaining > 0) {
                capacityCapped += remaining;
                processed += remaining;
                log('info', `Cache limit reached — skipping ${remaining} remaining files`);
              }
            }
          }
        } else {
          failed++;
        }
        onProgress({
          phase: 'syncing',
          playlist: item.key,
          file: item.file.display_filename || item.file.filename,
          processed,
          total: grandTotal,
          copied: downloaded,
          skipped: totalSkipped,
          failed,
        });
      }
    };

    const workers = Array.from(
      { length: Math.min(concurrency, toDownload.length) },
      () => worker(),
    );
    await Promise.all(workers);

    // Evict if over limit (skip if all downloads were capacity-capped — nothing to evict)
    let evictedBytes = 0;
    if (hasLimit && !capacityReached) {
      evictedBytes = this.cacheManager.evictToLimit(maxCacheBytes, options.pinnedPlaylists);
      if (evictedBytes > 0) {
        log('info', `Evicted ${formatBytes(evictedBytes)} to stay within cache limit`);
      }
    }

    onProgress({
      phase: aborted ? 'aborted' : 'complete',
      processed,
      total: grandTotal,
      copied: downloaded,
      skipped: totalSkipped,
      failed,
    });

    return {
      downloaded,
      skipped: totalSkipped,
      failed,
      capacityCapped,
      aborted,
      durationMs: Date.now() - startTime,
    };
  }

  private async downloadToCache(
    playlistKey: string,
    file: FileInfo,
    profile: string | undefined,
    signal: AbortSignal | undefined,
    log: LogCallback,
  ): Promise<boolean> {
    try {
      const timeoutSignal = AbortSignal.timeout(FILE_DOWNLOAD_TIMEOUT_MS);
      const combinedSignal = signal
        ? AbortSignal.any([signal, timeoutSignal])
        : timeoutSignal;
      const { body } = await this.client.downloadFile(playlistKey, file.filename, profile, combinedSignal);
      await this.cacheManager.storeStream(file, playlistKey, body, file.created_at, file.updated_at);
      return true;
    } catch (err) {
      if (signal?.aborted) return false;
      const isTimeout = err instanceof DOMException && err.name === 'TimeoutError';
      if (isTimeout) {
        log('warn', `Prefetch timed out for ${playlistKey}/${file.filename}`);
      } else {
        log('error', `Prefetch failed for ${playlistKey}/${file.filename}: ${err}`);
      }
      return false;
    }
  }
}

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
  if (bytes >= BYTES_PER_KB) return `${(bytes / BYTES_PER_KB).toFixed(1)} KB`;
  return `${bytes} B`;
}
