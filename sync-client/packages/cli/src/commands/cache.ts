import type { Command } from 'commander';
import cliProgress from 'cli-progress';
import chalk from 'chalk';
import {
  CacheManager,
  ConfigStore,
  MetadataCache,
  PrefetchEngine,
  getConfigDir,
  DEFAULT_CONCURRENCY,
  EXIT_ERROR,
} from '@mporter/core';
import type { SyncProgress } from '@mporter/core';
import { formatBytes, formatDuration, printError, printField, printSuccess, printTable } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

function resolveProfile(configStore: ConfigStore): string {
  const profile = configStore.profile;
  if (!profile) {
    printError('No profile set. Run "mporter-sync sync --profile <name>" first or set a default.');
    process.exit(EXIT_ERROR);
  }
  return profile;
}

function createCacheManager(configStore: ConfigStore): CacheManager {
  const profile = resolveProfile(configStore);
  return new CacheManager(getConfigDir(), profile);
}

export function registerCacheCommand(program: Command): void {
  const cache = program
    .command('cache')
    .description('Manage local audio file cache');

  // ── cache status ──
  cache
    .command('status')
    .description('Show cache size and pinned playlists')
    .action(() => {
      const configStore = new ConfigStore();
      const profile = configStore.profile;
      if (!profile) {
        printError('No profile set.');
        process.exitCode = EXIT_ERROR;
        return;
      }

      const cm = new CacheManager(getConfigDir(), profile);
      const pinned = configStore.preferences.pinnedPlaylists;

      console.log();
      printField('Profile', profile);
      printField('Cache size', formatBytes(cm.getTotalSize()));
      printField('Cached playlists', cm.getCachedPlaylists().join(', ') || '(none)');
      printField('Pinned playlists', pinned.length > 0 ? pinned.join(', ') : '(none)');
      console.log();
    });

  // ── cache pin ──
  cache
    .command('pin <playlist>')
    .description('Pin a playlist for offline caching')
    .action((playlist: string) => {
      const configStore = new ConfigStore();
      configStore.pinPlaylist(playlist);
      printSuccess(`Pinned "${playlist}"`);
    });

  // ── cache unpin ──
  cache
    .command('unpin <playlist>')
    .description('Unpin a playlist')
    .action((playlist: string) => {
      const configStore = new ConfigStore();
      configStore.unpinPlaylist(playlist);
      printSuccess(`Unpinned "${playlist}"`);
    });

  // ── cache list ──
  cache
    .command('list')
    .description('List pinned playlists')
    .action(() => {
      const configStore = new ConfigStore();
      const pinned = configStore.preferences.pinnedPlaylists;
      if (pinned.length === 0) {
        console.log(chalk.dim('No pinned playlists.'));
        return;
      }

      const profile = configStore.profile;
      const cm = profile ? new CacheManager(getConfigDir(), profile) : null;

      const rows = pinned.map((key) => {
        const cached = cm ? cm.getCachedFileInfos(key).length : 0;
        return [key, String(cached)];
      });

      console.log();
      printTable(['Playlist', 'Cached Files'], rows);
      console.log();
    });

  // ── cache auto-pin ──
  cache
    .command('auto-pin <state>')
    .description('Enable or disable auto-pin for new playlists (on/off)')
    .action((state: string) => {
      const normalized = state.toLowerCase();
      if (normalized !== 'on' && normalized !== 'off') {
        printError('Usage: cache auto-pin <on|off>');
        process.exitCode = EXIT_ERROR;
        return;
      }
      const configStore = new ConfigStore();
      const enabled = normalized === 'on';
      configStore.setAutoPinNewPlaylists(enabled);
      printSuccess(`Auto-pin new playlists: ${enabled ? 'enabled' : 'disabled'}`);
    });

  // ── cache prefetch ──
  cache
    .command('prefetch')
    .description('Download pinned playlists to local cache')
    .option('--concurrency <n>', 'Number of parallel downloads', String(DEFAULT_CONCURRENCY))
    .action(async (opts: { concurrency?: string }) => {
      const client = await createConnectedClient();
      if (!client) return;

      const configStore = new ConfigStore();
      const cm = createCacheManager(configStore);

      // Auto-sync pins with server when auto-pin is enabled
      if (configStore.autoPinNewPlaylists) {
        try {
          const playlists = await client.getPlaylists();
          const serverKeys = playlists.map((p) => p.key);
          const newlyPinned = configStore.syncPinsWithServer(serverKeys);
          if (newlyPinned.length > 0) {
            console.log(chalk.green(`Auto-pinned ${newlyPinned.length} new playlist(s): ${newlyPinned.join(', ')}`));
          }
        } catch (err) {
          console.log(chalk.yellow(`Warning: Could not sync pins with server: ${err}`));
        }
      }

      const pinned = configStore.preferences.pinnedPlaylists;

      if (pinned.length === 0) {
        console.log(chalk.dim('No pinned playlists. Use "mporter-sync cache pin <playlist>" to pin one.'));
        return;
      }

      const concurrency = parseInt(opts.concurrency ?? String(DEFAULT_CONCURRENCY), 10);
      const profile = configStore.profile;

      console.log(`Prefetching ${pinned.length} pinned playlist(s)...`);
      console.log();

      const abortController = new AbortController();
      process.on('SIGINT', () => {
        console.log(chalk.dim('\nAborting prefetch...'));
        abortController.abort();
      });

      const progressBar = new cliProgress.SingleBar(
        {
          format: '{bar} {percentage}% | {value}/{total} | {status}',
          hideCursor: true,
        },
        cliProgress.Presets.shades_grey,
      );
      let barStarted = false;

      const engine = new PrefetchEngine(client, cm);
      const mc = profile ? new MetadataCache(getConfigDir(), profile) : undefined;

      try {
        const result = await engine.prefetch({
          playlists: pinned,
          profile: profile || undefined,
          concurrency,
          maxCacheBytes: configStore.preferences.maxCacheBytes,
          pinnedPlaylists: new Set(pinned),
          signal: abortController.signal,
          metadataCache: mc,
          onProgress: (progress: SyncProgress) => {
            if (!barStarted && progress.total > 0) {
              progressBar.start(progress.total, 0, { status: 'Starting...' });
              barStarted = true;
            }
            if (barStarted) {
              const status = progress.file
                ? `${progress.playlist}/${progress.file}`
                : progress.phase;
              progressBar.update(progress.processed, { status });
            }
            if (progress.phase === 'complete' || progress.phase === 'aborted') {
              if (barStarted) progressBar.stop();
            }
          },
          onLog: (level, message) => {
            if (level === 'error') {
              if (barStarted) progressBar.stop();
              printError(message);
              if (barStarted) progressBar.start(0, 0);
            }
          },
        });

        if (barStarted) progressBar.stop();
        console.log();

        if (result.aborted) {
          console.log(chalk.yellow('Prefetch aborted.'));
        } else {
          printSuccess('Prefetch complete!');
        }

        printField('Downloaded', String(result.downloaded));
        printField('Already cached', String(result.skipped));
        if (result.capacityCapped > 0) {
          printField('Capped (limit)', chalk.yellow(String(result.capacityCapped)));
        }
        if (result.failed > 0) {
          printField('Failed', chalk.red(String(result.failed)));
        }
        printField('Duration', formatDuration(result.durationMs));
        printField('Cache size', formatBytes(cm.getTotalSize()));
        console.log();
      } catch (err) {
        if (barStarted) progressBar.stop();
        printError(`Prefetch failed: ${err instanceof Error ? err.message : err}`);
        process.exitCode = EXIT_ERROR;
      }
    });

  // ── cache clear ──
  cache
    .command('clear')
    .description('Clear cached files')
    .option('--playlist <key>', 'Clear only a specific playlist')
    .action((opts: { playlist?: string }) => {
      const configStore = new ConfigStore();
      const cm = createCacheManager(configStore);

      if (opts.playlist) {
        cm.clearPlaylist(opts.playlist);
        printSuccess(`Cleared cache for "${opts.playlist}"`);
      } else {
        cm.clearAll();
        printSuccess('Cache cleared');
      }
    });
}
