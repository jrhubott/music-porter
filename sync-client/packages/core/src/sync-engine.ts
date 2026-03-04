import { existsSync, mkdirSync, createWriteStream } from 'node:fs';
import { access, readdir, rename, rmdir, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { DEFAULT_CONCURRENCY, FILE_DOWNLOAD_TIMEOUT_MS, TEMP_SUFFIX } from './constants.js';
import { SyncError } from './errors.js';
import type { APIClient } from './api-client.js';
import type { CacheManager } from './cache/cache-manager.js';
import type { MetadataCache } from './cache/metadata-cache.js';
import type { FileInfo, SyncResult } from './types.js';
import type { LogCallback, ProgressCallback } from './progress.js';
import {
  readManifest,
  writeManifest,
  getManifestFiles,
  createManifest,
  updateManifestPlaylist,
} from './manifest.js';

export interface SyncOptions {
  /** Specific playlist keys to sync. If empty, sync all. */
  playlists?: string[];
  /** Override the destination name. */
  destinationName?: string;
  /** USB drive name — triggers USB-type destination resolution. */
  usbDriveName?: string;
  /** Output profile name — when set, server applies profile-specific tags to downloads. */
  profile?: string;
  /** Number of parallel downloads. */
  concurrency?: number;
  /** AbortSignal for cancellation. */
  signal?: AbortSignal;
  /** Preview only — don't download files. */
  dryRun?: boolean;
  /** Force re-download all files (ignore manifest and disk cache). */
  force?: boolean;
  /** Progress callback. */
  onProgress?: ProgressCallback;
  /** Log callback. */
  onLog?: LogCallback;
  /** Optional local cache for read/write-through. */
  cacheManager?: CacheManager;
  /** Optional metadata cache for ETag-based conditional requests. */
  metadataCache?: MetadataCache;
  /** When true, sync exclusively from local cache (no server calls). */
  offlineOnly?: boolean;
  /** Remove destination files and update manifest for tracks removed from the server. */
  cleanDestination?: boolean;
}

/**
 * Sync engine — downloads files from music-porter server to a local destination.
 *
 * Replicates the browser sync flow from templates/sync.html:
 * 1. Read manifest from destination
 * 2. Resolve destination via server
 * 3. Write manifest immediately (survives interruptions)
 * 4. For each playlist: fetch file list, check manifest/disk, download new files
 * 5. Record synced files to server
 * 6. Update manifest after each playlist
 */
export class SyncEngine {
  private readonly client: APIClient;

  constructor(client: APIClient) {
    this.client = client;
  }

  /**
   * Run a full sync to a destination directory.
   */
  async sync(destDir: string, options: SyncOptions = {}): Promise<SyncResult> {
    if (options.offlineOnly && options.cacheManager) {
      return this.syncOffline(destDir, options);
    }
    return this.syncOnline(destDir, options);
  }

  /** Online sync — fetches file lists from server, uses cache for read/write-through. */
  private async syncOnline(destDir: string, options: SyncOptions): Promise<SyncResult> {
    const startTime = Date.now();
    const concurrency = options.concurrency ?? DEFAULT_CONCURRENCY;
    const log = options.onLog ?? (() => {});
    const onProgress = options.onProgress ?? (() => {});
    const cache = options.cacheManager;

    if (!existsSync(destDir)) {
      mkdirSync(destDir, { recursive: true });
    }

    // Phase 1: Read existing manifest
    const manifest = readManifest(destDir);

    // Phase 2: Resolve destination via server
    const destType = options.usbDriveName ? 'usb' : 'folder';
    const scheme = destType === 'usb' ? 'usb://' : 'folder://';
    const resolved = await this.client.resolveDestination({
      path: `${scheme}${destDir}`,
      driveName: options.usbDriveName,
      name: options.destinationName,
    });
    const destName = resolved.destination.name;
    log('info', `Destination: ${destName}`);

    // Phase 3: Determine which playlists to sync
    let playlistKeys = options.playlists ?? [];
    if (playlistKeys.length === 0) {
      const playlists = await this.client.getPlaylists();
      playlistKeys = playlists.map((p) => p.key);
    }

    // Phase 3b: Register sync run with server (required — enforced server-side)
    let syncTaskId: string | undefined;
    if (!options.dryRun) {
      const wasAllPlaylists = !options.playlists || options.playlists.length === 0;
      const id = await this.client.startSyncRun(
        destName,
        wasAllPlaylists ? null : playlistKeys,
        startTime / 1000,
      );
      if (!id) {
        throw new SyncError('Failed to start sync run on server — cannot proceed');
      }
      syncTaskId = id;
    }

    // Phase 4: Write initial manifest (persists destination_name across interruptions)
    const activeURL = this.client.connectionState.activeURL ?? '';
    const newManifest = manifest ?? createManifest(destName, activeURL);
    newManifest.destination_name = destName;
    if (!options.dryRun) {
      writeManifest(destDir, newManifest);
    }

    // Phase 5: Discover files for all playlists
    onProgress({
      phase: 'discovering',
      processed: 0,
      total: 0,
      copied: 0,
      skipped: 0,
      failed: 0,
    });

    interface PlaylistFiles {
      key: string;
      files: FileInfo[];
    }
    const playlistFileList: PlaylistFiles[] = [];
    let grandTotal = 0;

    for (const key of playlistKeys) {
      if (options.signal?.aborted) break;
      try {
        const response = await this.client.getFiles(key, false, options.profile, options.metadataCache);
        playlistFileList.push({ key, files: response.files });
        grandTotal += response.files.length;
      } catch (err) {
        log('warn', `Skipping playlist "${key}": ${err}`);
      }
    }

    log('info', `Found ${grandTotal} files across ${playlistFileList.length} playlists`);
    if (options.force) {
      log('info', 'Force mode: all files will be re-downloaded');
    }

    // Phase 6: Sync each playlist
    let totalCopied = 0;
    let totalSkipped = 0;
    let totalFailed = 0;
    let totalCleaned = 0;
    let processed = 0;
    let aborted = false;
    let destConflict: string | undefined;

    for (const { key, files } of playlistFileList) {
      if (options.signal?.aborted) {
        aborted = true;
        break;
      }

      const manifestFiles = getManifestFiles(manifest, key);
      const syncedFiles: Record<string, number> = {};
      const filesToDownload: FileInfo[] = [];

      // Check which files need downloading
      for (const file of files) {
        if (options.signal?.aborted) {
          aborted = true;
          break;
        }

        // Use display_filename for disk/manifest keys (human-readable on disk)
        const diskName = file.display_filename || file.filename;
        // Build subdirectory: prefer server-provided output_subdir, fall back to playlist key
        const subdir = file.output_subdir ?? key;
        const manifestKey = subdir ? `${subdir}/${diskName}` : diskName;
        const fileDir = subdir ? join(destDir, subdir) : destDir;
        const filePath = join(fileDir, diskName);

        if (!options.force) {
          const manifestSize = manifestFiles[manifestKey];
          if (manifestSize !== undefined && manifestSize === file.size
              && await access(filePath).then(() => true).catch(() => false)) {
            // Skip — manifest says this file is current and file exists on disk
            totalSkipped++;
            processed++;
            syncedFiles[manifestKey] = file.size;
            onProgress({
              phase: 'syncing',
              playlist: key,
              file: diskName,
              subdir,
              processed,
              total: grandTotal,
              copied: totalCopied,
              skipped: totalSkipped,
              failed: totalFailed,
            });
            continue;
          }

          // Check disk — file exists at final path; atomic writes guarantee completeness
          if (await access(filePath).then(() => true).catch(() => false)) {
            totalSkipped++;
            processed++;
            syncedFiles[manifestKey] = file.size;
            onProgress({
              phase: 'syncing',
              playlist: key,
              file: diskName,
              subdir,
              processed,
              total: grandTotal,
              copied: totalCopied,
              skipped: totalSkipped,
              failed: totalFailed,
            });
            continue;
          }

          // Cache hit check — copy from local cache instead of downloading
          if (cache && await cache.copyToDestination(file.uuid, filePath)) {
            totalCopied++;
            processed++;
            syncedFiles[manifestKey] = file.size;
            log('info', `Cache hit: ${diskName}`);
            onProgress({
              phase: 'syncing',
              playlist: key,
              file: diskName,
              subdir,
              processed,
              total: grandTotal,
              copied: totalCopied,
              skipped: totalSkipped,
              failed: totalFailed,
            });
            continue;
          }
        }

        filesToDownload.push(file);
      }

      if (!aborted) {
        // Download files with concurrency limit
        if (!options.dryRun) {
          const results = await this.downloadBatch(
            key,
            filesToDownload,
            destDir,
            concurrency,
            options.profile,
            options.signal,
            cache,
            (file, success) => {
              const dn = file.display_filename || file.filename;
              const fileSubdir = file.output_subdir ?? key;
              const fileManifestKey = fileSubdir ? `${fileSubdir}/${dn}` : dn;
              processed++;
              if (success) {
                totalCopied++;
                syncedFiles[fileManifestKey] = file.size;
              } else {
                totalFailed++;
              }
              onProgress({
                phase: 'syncing',
                playlist: key,
                file: dn,
                subdir: fileSubdir,
                processed,
                total: grandTotal,
                copied: totalCopied,
                skipped: totalSkipped,
                failed: totalFailed,
              });
            },
            log,
          );

          if (results.aborted) {
            aborted = true;
          }
        } else {
          // Dry run — count as would-be copies
          for (const file of filesToDownload) {
            const dn = file.display_filename || file.filename;
            const drySubdir = file.output_subdir ?? key;
            processed++;
            totalCopied++;
            log('info', `[dry-run] Would download: ${drySubdir ? drySubdir + '/' : ''}${dn}`);
            onProgress({
              phase: 'syncing',
              playlist: key,
              file: dn,
              subdir: drySubdir,
              processed,
              total: grandTotal,
              copied: totalCopied,
              skipped: totalSkipped,
              failed: totalFailed,
            });
          }
        }
      }

      // Record all synced files (skipped + downloaded) to server in one batch
      if (!aborted && !options.dryRun && Object.keys(syncedFiles).length > 0) {
        try {
          const recordDestType = options.usbDriveName ? 'usb' : 'folder';
          await this.client.recordSync(
            destName, key, Object.keys(syncedFiles), destDir, recordDestType, syncTaskId,
          );
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          log('error', `Failed to record sync for "${key}": ${message}`);
          if (!destConflict && err instanceof SyncError) {
            destConflict = message;
          }
        }
      }

      // Update manifest after each playlist (always, even if aborted mid-check-loop)
      if (!options.dryRun) {
        updateManifestPlaylist(newManifest, key, syncedFiles);
        writeManifest(destDir, newManifest);
      }

      if (aborted) break;
    }

    // Scan-based destination cleanup (mirror mode)
    // expectedPaths is built from only the synced playlists — files from other playlists
    // are treated as orphans and removed. This makes the destination an exact mirror of
    // the selected playlists.
    if (options.cleanDestination && !aborted && !options.dryRun && existsSync(destDir)) {
      try {
        const expectedPaths = new Set<string>();
        for (const { key } of playlistFileList) {
          const playlist = newManifest.playlists[key];
          if (!playlist) continue;
          for (const relPath of Object.keys(playlist.files)) {
            expectedPaths.add(join(destDir, relPath));
          }
        }
        const mp3s = await findMp3s(destDir);
        for (const absPath of mp3s) {
          if (!expectedPaths.has(absPath)) {
            try {
              await unlink(absPath);
              totalCleaned++;
              log('info', `Removed orphan: ${absPath.slice(destDir.length + 1)}`);
            } catch { /* ignore */ }
          }
        }
        await pruneEmptyDirs(destDir);
      } catch {
        // Non-fatal — cleanup failure does not abort the sync
      }
    }

    const phase = aborted ? 'aborted' : 'complete';
    onProgress({
      phase,
      processed,
      total: grandTotal,
      copied: totalCopied,
      skipped: totalSkipped,
      failed: totalFailed,
    });

    // Notify server of sync completion (best-effort — non-fatal)
    if (syncTaskId) {
      const finalStatus = aborted ? 'cancelled' : 'completed';
      try {
        await this.client.completeSyncRun(
          syncTaskId, finalStatus, totalCopied, totalSkipped, totalFailed, totalCleaned,
        );
      } catch {
        log('warn', 'Failed to complete sync run record on server');
      }
    }

    return {
      destinationName: destName,
      copied: totalCopied,
      skipped: totalSkipped,
      failed: totalFailed,
      cleaned: totalCleaned,
      aborted,
      durationMs: Date.now() - startTime,
      destError: destConflict,
    };
  }

  /** Offline sync — copies files from local cache to destination without server contact. */
  private async syncOffline(destDir: string, options: SyncOptions): Promise<SyncResult> {
    const startTime = Date.now();
    const cache = options.cacheManager!;
    const log = options.onLog ?? (() => {});
    const onProgress = options.onProgress ?? (() => {});

    if (!existsSync(destDir)) {
      mkdirSync(destDir, { recursive: true });
    }

    // Read existing manifest — offline uses manifest destination name or explicit name
    const manifest = readManifest(destDir);
    const destName = options.destinationName ?? manifest?.destination_name ?? 'offline-sync';
    log('info', `Offline sync — destination: ${destName}`);

    // Use cached playlists as the source of truth
    const requestedPlaylists = options.playlists ?? [];
    const cachedPlaylists = cache.getCachedPlaylists();
    const playlistKeys = requestedPlaylists.length > 0
      ? requestedPlaylists.filter((k) => cachedPlaylists.includes(k))
      : cachedPlaylists;

    // Write initial manifest
    const newManifest = manifest ?? createManifest(destName, 'offline');
    newManifest.destination_name = destName;
    writeManifest(destDir, newManifest);

    // Build file list from cache
    let grandTotal = 0;
    const playlistFileList: { key: string; entries: { uuid: string; display_filename: string; size: number }[] }[] = [];
    for (const key of playlistKeys) {
      const entries = cache.getCachedFileInfos(key);
      playlistFileList.push({ key, entries });
      grandTotal += entries.length;
    }

    log('info', `Offline: ${grandTotal} cached files across ${playlistFileList.length} playlists`);

    onProgress({
      phase: 'discovering',
      processed: 0,
      total: grandTotal,
      copied: 0,
      skipped: 0,
      failed: 0,
    });

    let totalCopied = 0;
    let totalSkipped = 0;
    let totalFailed = 0;
    let processed = 0;
    let aborted = false;

    for (const { key, entries } of playlistFileList) {
      if (options.signal?.aborted) {
        aborted = true;
        break;
      }

      const manifestFiles = getManifestFiles(manifest, key);
      const syncedFiles: Record<string, number> = {};

      for (const entry of entries) {
        if (options.signal?.aborted) {
          aborted = true;
          break;
        }

        const diskName = entry.display_filename;
        // Offline mode uses playlist key as subdir (no server to provide output_subdir)
        const subdir = key;
        const manifestKey = `${subdir}/${diskName}`;
        const fileDir = join(destDir, subdir);
        const filePath = join(fileDir, diskName);

        // Skip if already on disk with matching size
        const manifestSize = manifestFiles[manifestKey];
        if (manifestSize !== undefined && manifestSize === entry.size && await access(filePath).then(() => true).catch(() => false)) {
          totalSkipped++;
          processed++;
          syncedFiles[manifestKey] = entry.size;
          onProgress({
            phase: 'syncing',
            playlist: key,
            file: diskName,
            subdir,
            processed,
            total: grandTotal,
            copied: totalCopied,
            skipped: totalSkipped,
            failed: totalFailed,
          });
          continue;
        }

        // Copy from cache
        if (await cache.copyToDestination(entry.uuid, filePath)) {
          totalCopied++;
          syncedFiles[manifestKey] = entry.size;
        } else {
          totalFailed++;
          log('warn', `Failed to copy cached file: ${diskName}`);
        }
        processed++;
        onProgress({
          phase: 'syncing',
          playlist: key,
          file: diskName,
          subdir,
          processed,
          total: grandTotal,
          copied: totalCopied,
          skipped: totalSkipped,
          failed: totalFailed,
        });
      }

      // Update manifest (skip server recordSync — offline)
      updateManifestPlaylist(newManifest, key, syncedFiles);
      writeManifest(destDir, newManifest);

      if (aborted) break;
    }

    const phase = aborted ? 'aborted' : 'complete';
    onProgress({
      phase,
      processed,
      total: grandTotal,
      copied: totalCopied,
      skipped: totalSkipped,
      failed: totalFailed,
    });

    return {
      destinationName: destName,
      copied: totalCopied,
      skipped: totalSkipped,
      failed: totalFailed,
      cleaned: 0,
      aborted,
      durationMs: Date.now() - startTime,
    };
  }

  /** Download a batch of files with concurrency limit. */
  private async downloadBatch(
    playlistKey: string,
    files: FileInfo[],
    destDir: string,
    concurrency: number,
    profile: string | undefined,
    signal: AbortSignal | undefined,
    cache: CacheManager | undefined,
    onFile: (file: FileInfo, success: boolean) => void,
    log: LogCallback,
  ): Promise<{ aborted: boolean }> {
    let aborted = false;
    let index = 0;

    const worker = async () => {
      while (index < files.length) {
        if (signal?.aborted) {
          aborted = true;
          return;
        }
        const file = files[index++]!;
        const success = await this.downloadFile(playlistKey, file, destDir, profile, signal, cache, log);
        onFile(file, success);
      }
    };

    const workers = Array.from({ length: Math.min(concurrency, files.length) }, () => worker());
    await Promise.all(workers);
    return { aborted };
  }

  /** Download a single file to disk with atomic write (.tmp + rename). */
  private async downloadFile(
    playlistKey: string,
    file: FileInfo,
    destDir: string,
    profile: string | undefined,
    signal: AbortSignal | undefined,
    cache: CacheManager | undefined,
    log: LogCallback,
  ): Promise<boolean> {
    // Use display_filename for disk (human-readable), filename (UUID) for API
    const diskName = file.display_filename || file.filename;
    // Build subdirectory: prefer server-provided output_subdir, fall back to playlist key
    const subdir = file.output_subdir ?? playlistKey;
    const fileDir = subdir ? join(destDir, subdir) : destDir;
    if (!existsSync(fileDir)) {
      mkdirSync(fileDir, { recursive: true });
    }
    const filePath = join(fileDir, diskName);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      const timeoutSignal = AbortSignal.timeout(FILE_DOWNLOAD_TIMEOUT_MS);
      const combinedSignal = signal
        ? AbortSignal.any([signal, timeoutSignal])
        : timeoutSignal;
      const { body } = await this.client.downloadFile(playlistKey, file.filename, profile, combinedSignal);
      const nodeStream = Readable.fromWeb(body as import('node:stream/web').ReadableStream);
      const writeStream = createWriteStream(tmpPath);
      await pipeline(nodeStream, writeStream);
      await rename(tmpPath, filePath);

      // Write-through: copy downloaded file into cache (non-fatal on failure)
      if (cache) {
        try {
          await cache.storeFromFile(file, playlistKey, filePath);
        } catch {
          // Cache write failures are non-fatal
        }
      }

      return true;
    } catch (err) {
      // Clean up partial download
      try {
        await unlink(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
      if (signal?.aborted) return false;
      const isTimeout = err instanceof DOMException && err.name === 'TimeoutError';
      if (isTimeout) {
        log('warn', `Download timed out for ${playlistKey}/${file.filename}`);
      } else {
        log('error', `Failed to download ${playlistKey}/${file.filename}: ${err}`);
      }
      return false;
    }
  }

}

/** Recursively collect all .mp3 file paths under a directory. */
async function findMp3s(dir: string): Promise<string[]> {
  const results: string[] = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return results;
  }
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...await findMp3s(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.mp3')) {
      results.push(fullPath);
    }
  }
  return results;
}

/** Remove empty subdirectories under a directory (deepest first). */
async function pruneEmptyDirs(dir: string): Promise<void> {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry.isDirectory()) {
      const subdir = join(dir, entry.name);
      await pruneEmptyDirs(subdir);
      try {
        const remaining = await readdir(subdir);
        if (remaining.length === 0) await rmdir(subdir);
      } catch { /* ignore */ }
    }
  }
}
