import { DEFAULT_CONCURRENCY, FILE_DOWNLOAD_TIMEOUT_MS } from './constants.js';
import type { APIClient } from './api-client.js';
import type { CacheManager } from './cache-manager.js';
import type { FileInfo, PrefetchResult } from './types.js';
import type { LogCallback, ProgressCallback } from './progress.js';

export interface PrefetchOptions {
  /** Playlist keys to prefetch. If empty, uses all pinned playlists. */
  playlists: string[];
  /** Output profile name for server-tagged downloads. */
  profile?: string;
  /** Number of parallel downloads. */
  concurrency?: number;
  /** Maximum cache size in bytes — runs eviction at end. */
  maxCacheBytes?: number;
  /** AbortSignal for cancellation. */
  signal?: AbortSignal;
  /** Progress callback. */
  onProgress?: ProgressCallback;
  /** Log callback. */
  onLog?: LogCallback;
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
        const response = await this.client.getFiles(key, false, options.profile);
        playlistFileList.push({ key, files: response.files });
        grandTotal += response.files.length;
      } catch (err) {
        log('warn', `Skipping playlist "${key}": ${err}`);
      }
    }

    // Filter out already-cached files
    const toDownload: { key: string; file: FileInfo }[] = [];
    let totalSkipped = 0;

    for (const { key, files } of playlistFileList) {
      for (const file of files) {
        if (this.cacheManager.isCached(file.uuid, file.size)) {
          totalSkipped++;
        } else {
          toDownload.push({ key, file });
        }
      }
    }

    log('info', `Prefetch: ${toDownload.length} to download, ${totalSkipped} already cached`);

    onProgress({
      phase: 'syncing',
      processed: totalSkipped,
      total: grandTotal,
      copied: 0,
      skipped: totalSkipped,
      failed: 0,
    });

    // Download with concurrency limit
    let downloaded = 0;
    let failed = 0;
    let processed = totalSkipped;
    let aborted = false;
    let index = 0;

    const worker = async () => {
      while (index < toDownload.length) {
        if (options.signal?.aborted) {
          aborted = true;
          return;
        }
        const item = toDownload[index++]!;
        const success = await this.downloadToCache(item.key, item.file, options.profile, options.signal, log);
        processed++;
        if (success) {
          downloaded++;
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

    // Evict if over limit
    if (options.maxCacheBytes !== undefined) {
      const evicted = this.cacheManager.evictToLimit(options.maxCacheBytes);
      if (evicted > 0) {
        log('info', `Evicted ${formatBytes(evicted)} to stay within cache limit`);
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
      await this.cacheManager.storeStream(file, playlistKey, body);
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
