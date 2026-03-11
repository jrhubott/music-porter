import type { Command } from 'commander';
import { printError, printSuccess } from '../formatters.js';
import { createConnectedClient } from '../shared.js';

/** Detect source type from a playlist URL. Returns 'apple_music' or 'youtube_music'. */
function parsePlaylistURL(url: string): { sourceType: 'apple_music' | 'youtube_music'; key: string } | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes('music.apple.com')) {
      // Extract key from /playlist/<slug>/<id>
      const match = parsed.pathname.match(/\/playlist\/([^/]+)/);
      if (!match || !match[1]) return null;
      const key = match[1].split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('_');
      return { sourceType: 'apple_music', key };
    }
    if (parsed.hostname.includes('music.youtube.com') || parsed.hostname.includes('youtube.com')) {
      const listId = parsed.searchParams.get('list');
      if (!listId) return null;
      return { sourceType: 'youtube_music', key: listId };
    }
  } catch {
    // invalid URL
  }
  return null;
}

export function registerPlaylistCommand(program: Command): void {
  const cmd = program.command('playlist').description('Manage playlists on the server');

  cmd
    .command('add <url>')
    .description('Add a playlist by URL (Apple Music or YouTube Music)')
    .option('--name <name>', 'Display name (defaults to key)')
    .option('--key <key>', 'Playlist key override')
    .action(async (url: string, options: { name?: string; key?: string }) => {
      const parsed = parsePlaylistURL(url);
      if (!parsed) {
        printError(
          'Unrecognised playlist URL. Expected music.apple.com or music.youtube.com.',
        );
        return;
      }

      const key = options.key ?? parsed.key;
      const name = options.name ?? key;

      const client = await createConnectedClient();
      if (!client) return;

      try {
        await client.addPlaylist(key, url, name);
        printSuccess(
          `Added ${parsed.sourceType === 'youtube_music' ? 'YouTube Music' : 'Apple Music'} playlist: ${name} (${key})`,
        );
      } catch (err) {
        printError(`Failed to add playlist: ${err instanceof Error ? err.message : err}`);
      }
    });
}
