import { join } from 'node:path';
import type { Command } from 'commander';
import cliProgress from 'cli-progress';
import chalk from 'chalk';
import {
  CacheManager,
  ConfigStore,
  DriveManager,
  MetadataCache,
  SyncEngine,
  getConfigDir,
  EXIT_ERROR,
  EXIT_PARTIAL_FAILURE,
  DEFAULT_CONCURRENCY,
} from '@mporter/core';
import type { SyncProgress } from '@mporter/core';
import { formatDuration, printError, printSuccess, printField } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerSyncCommand(program: Command): void {
  program
    .command('sync')
    .description('Sync playlists to a destination')
    .option('-p, --playlist <key>', 'Sync a specific playlist')
    .option('-d, --dest <path>', 'Destination path or saved destination name')
    .option('-k, --key <name>', 'Override sync key')
    .option('--profile <name>', 'Output profile to use (determines USB directory)')
    .option('--concurrency <n>', 'Number of parallel downloads', String(DEFAULT_CONCURRENCY))
    .option('--dry-run', 'Preview sync without downloading')
    .option('--force', 'Force re-download all files (ignore manifest and disk cache)')
    .option('--offline', 'Sync from local cache only (no server connection)')
    .action(async (opts: {
      playlist?: string;
      dest?: string;
      key?: string;
      profile?: string;
      concurrency?: string;
      dryRun?: boolean;
      force?: boolean;
      offline?: boolean;
    }) => {
      const configStore = new ConfigStore();

      // Offline mode — no server needed
      if (opts.offline) {
        const profile = opts.profile ?? configStore.profile;
        if (!profile) {
          printError('No profile set. Use --profile <name> or set a default.');
          process.exitCode = EXIT_ERROR;
          return;
        }
        const cm = new CacheManager(getConfigDir(), profile);
        if (!cm.hasData()) {
          printError('No cached files. Run "mporter-sync cache prefetch" while connected to cache files first.');
          process.exitCode = EXIT_ERROR;
          return;
        }

        const dest = opts.dest ?? process.cwd();
        const playlists = opts.playlist ? [opts.playlist] : undefined;
        const abortController = new AbortController();
        process.on('SIGINT', () => {
          console.log(chalk.dim('\nAborting sync...'));
          abortController.abort();
        });

        console.log(chalk.yellow('Offline mode — syncing from local cache only'));
        console.log(`Profile: ${profile}`);
        console.log(`Syncing to: ${dest}`);
        console.log();

        const engine = new SyncEngine(null as never); // Client unused in offline mode
        const progressBar = new cliProgress.SingleBar(
          {
            format: '{bar} {percentage}% | {value}/{total} | {status}',
            hideCursor: true,
          },
          cliProgress.Presets.shades_grey,
        );
        let barStarted = false;

        try {
          const result = await engine.sync(dest, {
            playlists,
            syncKey: opts.key,
            offlineOnly: true,
            cacheManager: cm,
            signal: abortController.signal,
            onProgress: (progress: SyncProgress) => {
              if (progress.phase === 'discovering') return;
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
            console.log(chalk.yellow('Sync aborted.'));
          } else {
            printSuccess('Offline sync complete!');
          }
          printField('Sync Key', result.syncKey);
          printField('Copied', String(result.copied));
          printField('Skipped', String(result.skipped));
          if (result.failed > 0) {
            printField('Failed', chalk.red(String(result.failed)));
          }
          printField('Duration', formatDuration(result.durationMs));
          console.log();

          if (result.failed > 0) {
            process.exitCode = EXIT_PARTIAL_FAILURE;
          }
        } catch (err) {
          if (barStarted) progressBar.stop();
          printError(`Offline sync failed: ${err instanceof Error ? err.message : err}`);
          process.exitCode = EXIT_ERROR;
        }
        return;
      }

      const client = await createConnectedClient();
      if (!client) return;

      const concurrency = parseInt(opts.concurrency ?? String(DEFAULT_CONCURRENCY), 10);
      const playlists = opts.playlist ? [opts.playlist] : undefined;

      // Resolve profile and usb_dir
      let usbDir = '';
      let resolvedProfileName = opts.profile ?? configStore.profile ?? '';
      try {
        const settings = await client.getSettings();
        if (!resolvedProfileName) {
          resolvedProfileName = (settings.settings['output_type'] as string) ?? '';
        }
        if (resolvedProfileName && settings.profiles[resolvedProfileName]) {
          usbDir = settings.profiles[resolvedProfileName]!.usb_dir;
        }
      } catch {
        // Non-critical — proceed without usb_dir
      }

      // Resolve destination, detecting USB drives
      let dest = opts.dest ?? process.cwd();
      let usbDriveName: string | undefined;

      if (opts.dest) {
        // Check if --dest points to a detected USB drive
        const driveManager = new DriveManager();
        const drives = driveManager.listDrives();
        const matchingDrive = drives.find(
          (d) => d.path === opts.dest || opts.dest!.startsWith(d.path),
        );
        if (matchingDrive) {
          usbDriveName = matchingDrive.name;
          // Append usb_dir if dest is the drive root
          if (usbDir && opts.dest === matchingDrive.path) {
            dest = join(matchingDrive.path, usbDir);
          }
        }
      }

      const abortController = new AbortController();

      // Handle Ctrl+C gracefully
      process.on('SIGINT', () => {
        console.log(chalk.dim('\nAborting sync...'));
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

      const engine = new SyncEngine(client);

      // Instantiate cache manager and metadata cache if we have a resolved profile
      const cacheManager = resolvedProfileName
        ? new CacheManager(getConfigDir(), resolvedProfileName)
        : undefined;
      const metadataCache = resolvedProfileName
        ? new MetadataCache(getConfigDir(), resolvedProfileName)
        : undefined;

      if (opts.dryRun) {
        console.log(chalk.dim('Dry run — no files will be downloaded.\n'));
      }

      if (resolvedProfileName) console.log(`Profile: ${resolvedProfileName}`);
      console.log(`Syncing to: ${dest}`);
      if (opts.key) console.log(`Sync key: ${opts.key}`);
      if (usbDriveName) console.log(`USB drive: ${usbDriveName}`);
      console.log();

      try {
        const result = await engine.sync(dest, {
          playlists,
          syncKey: opts.key,
          usbDriveName,
          profile: resolvedProfileName || undefined,
          concurrency,
          signal: abortController.signal,
          dryRun: opts.dryRun,
          force: opts.force,
          cacheManager,
          metadataCache,
          onProgress: (progress: SyncProgress) => {
            if (progress.phase === 'discovering') {
              // Don't start bar yet
              return;
            }

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

        // Print results
        if (result.aborted) {
          console.log(chalk.yellow('Sync aborted.'));
        } else {
          printSuccess('Sync complete!');
        }

        printField('Sync Key', result.syncKey);
        printField('Copied', String(result.copied));
        printField('Skipped', String(result.skipped));
        if (result.failed > 0) {
          printField('Failed', chalk.red(String(result.failed)));
        }
        printField('Duration', formatDuration(result.durationMs));
        console.log();

        if (result.failed > 0) {
          process.exitCode = EXIT_PARTIAL_FAILURE;
        }
      } catch (err) {
        if (barStarted) progressBar.stop();
        printError(`Sync failed: ${err instanceof Error ? err.message : err}`);
        process.exitCode = EXIT_ERROR;
      }
    });
}
