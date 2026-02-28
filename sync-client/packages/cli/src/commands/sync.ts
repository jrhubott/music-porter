import { join } from 'node:path';
import type { Command } from 'commander';
import cliProgress from 'cli-progress';
import chalk from 'chalk';
import {
  ConfigStore,
  DriveManager,
  SyncEngine,
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
    .action(async (opts: {
      playlist?: string;
      dest?: string;
      key?: string;
      profile?: string;
      concurrency?: string;
      dryRun?: boolean;
      force?: boolean;
    }) => {
      const client = await createConnectedClient();
      if (!client) return;

      const configStore = new ConfigStore();
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
