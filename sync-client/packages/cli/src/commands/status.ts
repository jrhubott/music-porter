import type { Command } from 'commander';
import { printTable, printField, printError, formatBytes } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerStatusCommand(program: Command): void {
  program
    .command('status [key]')
    .description('Show sync status for all keys or a specific key')
    .option('--json', 'Output as JSON')
    .action(async (key: string | undefined, opts: { json?: boolean }) => {
      const client = await createConnectedClient();
      if (!client) return;

      if (key) {
        // Detail for one key
        try {
          const detail = await client.getSyncStatus(key);
          if (opts.json) {
            console.log(JSON.stringify(detail, null, 2));
            return;
          }

          console.log(`\nSync Key: ${detail.sync_key}`);
          if (detail.last_sync_at) {
            printField('Last Sync', new Date(detail.last_sync_at * 1000).toLocaleString());
          }
          printField('Total Files', `${detail.synced_files}/${detail.total_files}`);
          printField('New Files', String(detail.new_files));
          console.log();

          if (detail.playlists.length > 0) {
            printTable(
              ['Playlist', 'Synced', 'Total', 'New', 'Status'],
              detail.playlists.map((p) => [
                p.name,
                String(p.synced_files),
                String(p.total_files),
                String(p.new_files),
                p.is_new_playlist ? 'New' : p.new_files > 0 ? 'Updates' : 'Current',
              ]),
            );
            console.log();
          }
        } catch (err) {
          printError(`Failed to get status: ${err instanceof Error ? err.message : err}`);
        }
      } else {
        // All keys
        try {
          const keys = await client.getSyncKeys();
          if (opts.json) {
            console.log(JSON.stringify(keys, null, 2));
            return;
          }

          if (keys.length === 0) {
            console.log('No sync keys found.');
            return;
          }

          console.log();
          printTable(
            ['Sync Key', 'Files', 'Playlists', 'Last Sync'],
            keys.map((k) => [
              k.key_name,
              String(k.file_count),
              String(k.playlist_count),
              k.last_sync_at ? new Date(k.last_sync_at * 1000).toLocaleString() : 'Never',
            ]),
          );
          console.log();
        } catch (err) {
          printError(`Failed to get sync keys: ${err instanceof Error ? err.message : err}`);
        }
      }
    });
}
