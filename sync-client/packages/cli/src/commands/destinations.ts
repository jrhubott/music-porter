import type { Command } from 'commander';
import { DriveManager } from '@mporter/core';
import { printTable, printError, printSuccess, printField, formatBytes } from '../formatters.js';
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
            ['Name', 'Path', 'Sync Key'],
            response.destinations.map((d) => [d.name, d.path, d.sync_key ?? '—']),
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
