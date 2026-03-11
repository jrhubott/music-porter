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
          console.log('\nSaved Destinations:');
          printTable(
            ['Name', 'Description', 'Path', 'Linked'],
            response.destinations.map((d) => {
              const linked = d.linked_destinations ?? [];
              const linkedLabel = linked.length > 0
                ? `${linked.join(', ')}`
                : '—';
              return [d.name, d.description ?? '', d.path, linkedLabel];
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
    .command('link <name> <target-destination>')
    .description('Link a destination to share tracking with another destination')
    .action(async (name: string, targetDest: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        const result = await client.linkDestination(name, targetDest);
        printSuccess(`Linked '${name}' to '${targetDest}'.`);
        if (result.merge_stats) {
          console.log(`  Merged ${result.merge_stats.records_moved} tracking record(s).`);
        }
      } catch (err) {
        printError(`Failed to link destination: ${err instanceof Error ? err.message : err}`);
      }
    });

  cmd
    .command('unlink <name>')
    .description('Unlink a destination from its group')
    .action(async (name: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        await client.linkDestination(name, null);
        printSuccess(`Unlinked '${name}' from its group.`);
      } catch (err) {
        printError(`Failed to unlink destination: ${err instanceof Error ? err.message : err}`);
      }
    });

  cmd
    .command('reset <name>')
    .description('Reset sync tracking for a destination group')
    .action(async (name: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        const result = await client.resetDestinationTracking(name);
        printSuccess(`Reset tracking for '${name}' (${result.files_cleared} record(s) cleared).`);
      } catch (err) {
        printError(`Failed to reset tracking: ${err instanceof Error ? err.message : err}`);
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
