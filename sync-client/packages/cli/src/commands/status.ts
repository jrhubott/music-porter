import type { Command } from 'commander';
import { printTable, printField, printError } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerStatusCommand(program: Command): void {
  program
    .command('status [destination]')
    .description('Show sync status for all destination groups or a specific destination')
    .option('--json', 'Output as JSON')
    .action(async (destination: string | undefined, opts: { json?: boolean }) => {
      const client = await createConnectedClient();
      if (!client) return;

      if (destination) {
        // Detail for one destination
        try {
          const detail = await client.getSyncStatus(destination);
          if (opts.json) {
            console.log(JSON.stringify(detail, null, 2));
            return;
          }

          const dests = detail.destinations ?? [destination];
          console.log(`\nDestination${dests.length > 1 ? 's' : ''}: ${dests.join(', ')}`);
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
        // All destination groups — use summary endpoint
        try {
          const summary = await client.getSyncStatusSummary();
          if (opts.json) {
            console.log(JSON.stringify(summary, null, 2));
            return;
          }

          if (summary.length === 0) {
            console.log('No sync destinations found.');
            return;
          }

          console.log();
          printTable(
            ['Destinations', 'Total', 'Synced', 'New', 'Last Sync'],
            summary.map((k) => [
              (k.destinations ?? []).join(', ') || '—',
              String(k.total_files),
              String(k.synced_files),
              String(k.new_files),
              k.last_sync_at ? new Date(k.last_sync_at * 1000).toLocaleString() : 'Never',
            ]),
          );
          console.log();
        } catch (err) {
          printError(`Failed to get sync status: ${err instanceof Error ? err.message : err}`);
        }
      }
    });
}
