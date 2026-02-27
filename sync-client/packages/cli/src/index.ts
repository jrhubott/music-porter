#!/usr/bin/env node
import { Command } from 'commander';
import { VERSION, EXIT_SUCCESS } from '@mporter/core';
import { registerServerCommand } from './commands/server.js';
import { registerDiscoverCommand } from './commands/discover.js';
import { registerListCommand } from './commands/list.js';
import { registerStatusCommand } from './commands/status.js';
import { registerSyncCommand } from './commands/sync.js';
import { registerDestinationsCommand } from './commands/destinations.js';
import { runInteractiveMode } from './interactive.js';

const program = new Command();

program
  .name('mporter-sync')
  .description('Music Porter sync client — sync playlists from your server')
  .version(VERSION);

// Register all subcommands
registerServerCommand(program);
registerDiscoverCommand(program);
registerListCommand(program);
registerStatusCommand(program);
registerSyncCommand(program);
registerDestinationsCommand(program);

// If no arguments, run interactive mode
if (process.argv.length <= 2) {
  runInteractiveMode().catch((err) => {
    console.error(err);
    process.exit(1);
  });
} else {
  program.parse();
}
