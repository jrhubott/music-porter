import type { Command } from 'commander';
import { DriveManager } from '@mporter/core';
import { printTable, printError, printSuccess, formatBytes } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerDestinationsCommand(program: Command): void {
  const cmd = program.command('destinations').alias('dest').description('Manage sync destinations');

  cmd
    .command('list', { isDefault: true })
    .description('List saved destinations and detected drives')
    .action(async () => {
      const client = await createConnectedClient();
      if (!client) return;

      // Server-side destinations
      try {
        const response = await client.getSyncDestinations();
        if (response.destinations.length > 0) {
          // Detect shared sync keys (same key used by multiple destinations)
          const keyCounts = new Map<string, number>();
          for (const d of response.destinations) {
            const key = d.sync_key;
            if (key) {
              keyCounts.set(key, (keyCounts.get(key) ?? 0) + 1);
            }
          }

          console.log('\nSaved Destinations:');
          printTable(
            ['Name', 'Path', 'Sync Key'],
            response.destinations.map((d) => {
              const key = d.sync_key ?? '—';
              const shared = d.sync_key && (keyCounts.get(d.sync_key) ?? 0) > 1;
              return [d.name, d.path, shared ? `${key} (shared)` : key];
            }),
          );
          console.log();
        } else {
          console.log('\nNo saved destinations on server.\n');
        }
      } catch (err) {
        printError(`Failed to fetch destinations: ${err instanceof Error ? err.message : err}`);
      }

      // Local drives
      const driveManager = new DriveManager();
      const drives = driveManager.listDrives();
      if (drives.length > 0) {
        console.log('Detected Drives:');
        printTable(
          ['Name', 'Path', 'Free Space'],
          drives.map((d) => [
            d.name,
            d.path,
            d.freeSpace !== undefined ? formatBytes(d.freeSpace) : '—',
          ]),
        );
        console.log();
      } else {
        console.log('No USB drives detected.\n');
      }
    });

  cmd
    .command('link <name> <sync-key>')
    .description('Link a destination to an existing sync key')
    .action(async (name: string, syncKey: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        const result = await client.linkDestination(name, syncKey);
        printSuccess(`Linked '${name}' to sync key '${result.sync_key}'.`);
        if (result.merge_stats) {
          console.log(`  Merged ${result.merge_stats.merged_count} tracking record(s).`);
        }
      } catch (err) {
        printError(`Failed to link destination: ${err instanceof Error ? err.message : err}`);
      }
    });

  cmd
    .command('unlink <name>')
    .description('Unlink a destination from its shared sync key')
    .action(async (name: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        await client.linkDestination(name, null);
        printSuccess(`Unlinked '${name}' from its sync key.`);
      } catch (err) {
        printError(`Failed to unlink destination: ${err instanceof Error ? err.message : err}`);
      }
    });

  cmd
    .command('drives')
    .description('List detected USB drives')
    .action(() => {
      const driveManager = new DriveManager();
      const drives = driveManager.listDrives();
      if (drives.length === 0) {
        console.log('No USB drives detected.');
        return;
      }

      console.log();
      printTable(
        ['Name', 'Path', 'Free Space'],
        drives.map((d) => [
          d.name,
          d.path,
          d.freeSpace !== undefined ? formatBytes(d.freeSpace) : '—',
        ]),
      );
      console.log();
    });
}
