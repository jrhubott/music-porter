#!/usr/bin/env node
import { Command } from 'commander';
import { VERSION } from '@mporter/core';
import { registerCacheCommand } from './commands/cache.js';
import { registerServerCommand } from './commands/server.js';
import { registerDiscoverCommand } from './commands/discover.js';
import { registerListCommand } from './commands/list.js';
import { registerStatusCommand } from './commands/status.js';
import { registerSyncCommand } from './commands/sync.js';
import { registerDestinationsCommand } from './commands/destinations.js';
import { registerPlaylistCommand } from './commands/playlist.js';
import { runInteractiveMode } from './interactive.js';

const program = new Command();

program
  .name('mporter-sync')
  .description('Music Porter sync client — sync playlists from your server')
  .version(VERSION);

// Register all subcommands
registerCacheCommand(program);
registerServerCommand(program);
registerDiscoverCommand(program);
registerListCommand(program);
registerStatusCommand(program);
registerSyncCommand(program);
registerDestinationsCommand(program);
registerPlaylistCommand(program);

// If no arguments, run interactive mode
if (process.argv.length <= 2) {
  runInteractiveMode().catch((err) => {
    console.error(err);
    process.exit(1);
  });
} else {
  program.parse();
}
