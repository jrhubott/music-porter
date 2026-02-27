import type { Command } from 'commander';
import { printTable, printError, formatBytes } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

export function registerListCommand(program: Command): void {
  const cmd = program.command('list').description('List playlists and files');

  cmd
    .command('playlists', { isDefault: true })
    .alias('--playlists')
    .description('List all playlists on the server')
    .action(async () => {
      const client = await createConnectedClient();
      if (!client) return;

      const playlists = await client.getPlaylists();
      if (playlists.length === 0) {
        console.log('No playlists configured on the server.');
        return;
      }

      console.log();
      printTable(
        ['#', 'Key', 'Name'],
        playlists.map((p, i) => [String(i + 1), p.key, p.name]),
      );
      console.log();
    });

  cmd
    .command('files <playlist>')
    .description('List files in a playlist')
    .action(async (playlist: string) => {
      const client = await createConnectedClient();
      if (!client) return;

      try {
        const response = await client.getFiles(playlist);
        if (response.files.length === 0) {
          console.log(`No files in playlist "${playlist}".`);
          return;
        }

        console.log(`\nPlaylist: ${response.playlist} (${response.file_count} files)\n`);
        printTable(
          ['Filename', 'Size', 'Artist', 'Title'],
          response.files.map((f) => [f.filename, formatBytes(f.size), f.artist, f.title]),
        );
        console.log();
      } catch (err) {
        printError(`Failed to list files: ${err instanceof Error ? err.message : err}`);
      }
    });
}
