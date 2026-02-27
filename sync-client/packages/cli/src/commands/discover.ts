import type { Command } from 'commander';
import { ServerDiscovery } from '@mporter/core';
import { printField, printSuccess } from '../formatters.js';
import chalk from 'chalk';

const SEARCH_TIMEOUT_MS = 10000;
const SEARCH_POLL_MS = 500;

export function registerDiscoverCommand(program: Command): void {
  program
    .command('discover')
    .description('Browse for music-porter servers on the local network')
    .action(async () => {
      console.log(chalk.dim('Searching for music-porter servers...'));
      console.log();

      const discovery = new ServerDiscovery();
      let lastCount = 0;

      discovery.startSearch((servers) => {
        if (servers.length > lastCount) {
          for (let i = lastCount; i < servers.length; i++) {
            const server = servers[i]!;
            printSuccess(`Found: ${server.name}`);
            printField('  Address', `${server.host}:${server.port}`);
            if (server.version) printField('  Version', server.version);
            if (server.platform) printField('  Platform', server.platform);
            console.log();
          }
          lastCount = servers.length;
        }
      });

      // Wait for search to complete
      await new Promise<void>((resolve) => {
        const checkInterval = setInterval(() => {
          // Discovery auto-stops after BONJOUR_BROWSE_TIMEOUT_MS
        }, SEARCH_POLL_MS);

        setTimeout(() => {
          clearInterval(checkInterval);
          discovery.stopSearch();
          resolve();
        }, SEARCH_TIMEOUT_MS);
      });

      const servers = discovery.discoveredServers;
      if (servers.length === 0) {
        console.log(chalk.dim('No servers found. Make sure the server is running with:'));
        console.log(chalk.dim(`  ./music-porter server`));
      } else {
        console.log(chalk.dim(`Found ${servers.length} server(s).`));
        console.log();
        console.log('To connect:');
        const firstServer = servers[0]!;
        console.log(
          chalk.dim(`  mporter-sync server set-local http://${firstServer.host}:${firstServer.port}`),
        );
        console.log(chalk.dim('  mporter-sync server set-key <api-key>'));
      }
    });
}
