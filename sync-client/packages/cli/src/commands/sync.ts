import type { Command } from 'commander';
import cliProgress from 'cli-progress';
import chalk from 'chalk';
import {
  ConfigStore,
  APIClient,
  SyncEngine,
  EXIT_SUCCESS,
  EXIT_ERROR,
  EXIT_PARTIAL_FAILURE,
  DEFAULT_CONCURRENCY,
} from '@mporter/core';
import type { SyncProgress } from '@mporter/core';
import { formatBytes, formatDuration, printError, printSuccess, printField } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerSyncCommand(program: Command): void {
  program
    .command('sync')
    .description('Sync playlists to a destination')
    .option('-p, --playlist <key>', 'Sync a specific playlist')
    .option('-d, --dest <path>', 'Destination path or saved destination name')
    .option('-k, --key <name>', 'Override sync key')
    .option('--concurrency <n>', 'Number of parallel downloads', String(DEFAULT_CONCURRENCY))
    .option('--dry-run', 'Preview sync without downloading')
    .action(async (opts: {
      playlist?: string;
      dest?: string;
      key?: string;
      concurrency?: string;
      dryRun?: boolean;
    }) => {
      const client = await createConnectedClient();
      if (!client) return;

      const dest = opts.dest ?? process.cwd();
      const concurrency = parseInt(opts.concurrency ?? String(DEFAULT_CONCURRENCY), 10);
      const playlists = opts.playlist ? [opts.playlist] : undefined;

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

      console.log(`Syncing to: ${dest}`);
      if (opts.key) console.log(`Sync key: ${opts.key}`);
      console.log();

      try {
        const result = await engine.sync(dest, {
          playlists,
          syncKey: opts.key,
          concurrency,
          signal: abortController.signal,
          dryRun: opts.dryRun,
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
