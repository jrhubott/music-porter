import { existsSync, mkdirSync, statSync, createWriteStream, renameSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { DEFAULT_CONCURRENCY, TEMP_SUFFIX } from './constants.js';
import { SyncError } from './errors.js';
import type { APIClient } from './api-client.js';
import type { FileInfo, SyncManifest, SyncProgress, SyncResult } from './types.js';
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
  /** Override the sync key. */
  syncKey?: string;
  /** Number of parallel downloads. */
  concurrency?: number;
  /** AbortSignal for cancellation. */
  signal?: AbortSignal;
  /** Preview only — don't download files. */
  dryRun?: boolean;
  /** Progress callback. */
  onProgress?: ProgressCallback;
  /** Log callback. */
  onLog?: LogCallback;
}

/**
 * Sync engine — downloads files from music-porter server to a local destination.
 *
 * Replicates the browser sync flow from templates/sync.html:
 * 1. Read manifest from destination
 * 2. Resolve sync key (explicit > manifest > generated)
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
    const startTime = Date.now();
    const concurrency = options.concurrency ?? DEFAULT_CONCURRENCY;
    const log = options.onLog ?? (() => {});
    const onProgress = options.onProgress ?? (() => {});

    if (!existsSync(destDir)) {
      mkdirSync(destDir, { recursive: true });
    }

    // Phase 1: Read existing manifest
    const manifest = readManifest(destDir);

    // Phase 2: Resolve sync key
    const syncKey = this.resolveSyncKey(options.syncKey, manifest, destDir);
    log('info', `Sync key: ${syncKey}`);

    // Phase 3: Determine which playlists to sync
    let playlistKeys = options.playlists ?? [];
    if (playlistKeys.length === 0) {
      const playlists = await this.client.getPlaylists();
      playlistKeys = playlists.map((p) => p.key);
    }

    // Phase 4: Write initial manifest (persists sync_key across interruptions)
    const activeURL = this.client.connectionState.activeURL ?? '';
    const newManifest = manifest ?? createManifest(syncKey, activeURL);
    newManifest.sync_key = syncKey;
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
        const response = await this.client.getFiles(key);
        playlistFileList.push({ key, files: response.files });
        grandTotal += response.files.length;
      } catch (err) {
        log('warn', `Skipping playlist "${key}": ${err}`);
      }
    }

    log('info', `Found ${grandTotal} files across ${playlistFileList.length} playlists`);

    // Phase 6: Sync each playlist
    let totalCopied = 0;
    let totalSkipped = 0;
    let totalFailed = 0;
    let processed = 0;
    let aborted = false;

    for (const { key, files } of playlistFileList) {
      if (options.signal?.aborted) {
        aborted = true;
        break;
      }

      const playlistDir = join(destDir, key);
      if (!options.dryRun && !existsSync(playlistDir)) {
        mkdirSync(playlistDir, { recursive: true });
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

        const manifestSize = manifestFiles[file.filename];
        if (manifestSize !== undefined && manifestSize === file.size) {
          // Skip — manifest says this file is current
          totalSkipped++;
          processed++;
          syncedFiles[file.filename] = file.size;
          onProgress({
            phase: 'syncing',
            playlist: key,
            file: file.filename,
            processed,
            total: grandTotal,
            copied: totalCopied,
            skipped: totalSkipped,
            failed: totalFailed,
          });
          continue;
        }

        // Check disk
        const filePath = join(playlistDir, file.filename);
        if (existsSync(filePath)) {
          try {
            const stat = statSync(filePath);
            if (stat.size === file.size) {
              totalSkipped++;
              processed++;
              syncedFiles[file.filename] = file.size;
              onProgress({
                phase: 'syncing',
                playlist: key,
                file: file.filename,
                processed,
                total: grandTotal,
                copied: totalCopied,
                skipped: totalSkipped,
                failed: totalFailed,
              });
              continue;
            }
          } catch {
            // Can't stat — will download
          }
        }

        filesToDownload.push(file);
      }

      if (aborted) break;

      // Record skipped files on server (fire-and-forget)
      if (!options.dryRun && Object.keys(syncedFiles).length > 0) {
        this.client
          .recordSync(syncKey, key, Object.keys(syncedFiles))
          .catch(() => {});
      }

      // Download files with concurrency limit
      if (!options.dryRun) {
        const results = await this.downloadBatch(
          key,
          filesToDownload,
          playlistDir,
          syncKey,
          concurrency,
          options.signal,
          (file, success) => {
            processed++;
            if (success) {
              totalCopied++;
              syncedFiles[file.filename] = file.size;
            } else {
              totalFailed++;
            }
            onProgress({
              phase: 'syncing',
              playlist: key,
              file: file.filename,
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
          processed++;
          totalCopied++;
          log('info', `[dry-run] Would download: ${key}/${file.filename}`);
          onProgress({
            phase: 'syncing',
            playlist: key,
            file: file.filename,
            processed,
            total: grandTotal,
            copied: totalCopied,
            skipped: totalSkipped,
            failed: totalFailed,
          });
        }
      }

      // Update manifest after each playlist
      if (!options.dryRun) {
        updateManifestPlaylist(newManifest, key, syncedFiles);
        writeManifest(destDir, newManifest);
      }

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
      syncKey,
      copied: totalCopied,
      skipped: totalSkipped,
      failed: totalFailed,
      aborted,
      durationMs: Date.now() - startTime,
    };
  }

  /** Download a batch of files with concurrency limit. */
  private async downloadBatch(
    playlistKey: string,
    files: FileInfo[],
    destDir: string,
    syncKey: string,
    concurrency: number,
    signal: AbortSignal | undefined,
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
        const success = await this.downloadFile(playlistKey, file, destDir, signal, log);
        onFile(file, success);

        // Record to server (fire-and-forget)
        if (success) {
          this.client
            .recordSync(syncKey, playlistKey, [file.filename])
            .catch(() => {});
        }
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
    signal: AbortSignal | undefined,
    log: LogCallback,
  ): Promise<boolean> {
    const filePath = join(destDir, file.filename);
    const tmpPath = filePath + TEMP_SUFFIX;

    try {
      const { body } = await this.client.downloadFile(playlistKey, file.filename, signal);
      const nodeStream = Readable.fromWeb(body as import('node:stream/web').ReadableStream);
      const writeStream = createWriteStream(tmpPath);
      await pipeline(nodeStream, writeStream);
      renameSync(tmpPath, filePath);
      return true;
    } catch (err) {
      // Clean up partial download
      try {
        if (existsSync(tmpPath)) unlinkSync(tmpPath);
      } catch {
        // Ignore cleanup errors
      }
      if (signal?.aborted) return false;
      log('error', `Failed to download ${playlistKey}/${file.filename}: ${err}`);
      return false;
    }
  }

  /** Resolve the sync key from explicit, manifest, or generated. */
  private resolveSyncKey(
    explicit: string | undefined,
    manifest: SyncManifest | null,
    destDir: string,
  ): string {
    if (explicit) return explicit;
    if (manifest?.sync_key) return manifest.sync_key;
    // Generate from directory name
    const dirName = destDir.split('/').pop() ?? destDir.split('\\').pop() ?? 'sync';
    return `client-${dirName}`;
  }
}
