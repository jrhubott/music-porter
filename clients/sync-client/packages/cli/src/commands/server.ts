import type { Command } from 'commander';
import { ConfigStore, APIClient, DEFAULT_PORT } from '@mporter/core';
import { printField, printError, printSuccess } from '../formatters.js';

export function registerServerCommand(program: Command): void {
  const cmd = program.command('server').description('Manage server connection');

  cmd
    .command('show', { isDefault: true })
    .description('Show current server connection')
    .action(() => {
      const config = new ConfigStore();
      const server = config.serverConfig;
      if (!server) {
        printError('No server configured. Use "mporter-sync server set-local <url>" to configure.');
        return;
      }
      console.log('\nServer Connection:');
      printField('Name', server.name);
      printField('Local URL', server.localURL);
      if (server.externalURL) {
        printField('External URL', server.externalURL);
      }
      const apiKey = config.getApiKey();
      printField('API Key', apiKey ? '(set)' : '(not set)');
      console.log();
    });

  cmd
    .command('set-local <url>')
    .description('Set the local server URL')
    .action((url: string) => {
      const config = new ConfigStore();
      const server = config.serverConfig ?? { name: '', localURL: '' };
      server.localURL = normalizeURL(url);
      config.serverConfig = server;
      printSuccess(`Local URL set to ${server.localURL}`);
    });

  cmd
    .command('set-external <url>')
    .description('Set the external server URL')
    .action((url: string) => {
      const config = new ConfigStore();
      const server = config.serverConfig ?? { name: '', localURL: '' };
      server.externalURL = normalizeURL(url);
      config.serverConfig = server;
      printSuccess(`External URL set to ${server.externalURL}`);
    });

  cmd
    .command('set-key <api-key>')
    .description('Set the API key')
    .action((apiKey: string) => {
      const config = new ConfigStore();
      config.setApiKey(apiKey);
      printSuccess('API key saved.');
    });

  cmd
    .command('test')
    .description('Test connection to server')
    .action(async () => {
      const config = new ConfigStore();
      const server = config.serverConfig;
      const apiKey = config.getApiKey();
      if (!server) {
        printError('No server configured.');
        return;
      }

      const client = new APIClient();
      client.configure(server.localURL, server.externalURL, apiKey ?? undefined);

      try {
        const response = await client.resolveConnection();
        const state = client.connectionState;
        console.log('\nConnection successful!');
        printField('Server', response.server_name);
        printField('Version', response.version);
        printField('Connected via', state.type === 'external' ? 'External URL' : 'Local Network');
        printField('Active URL', state.activeURL ?? 'unknown');
        console.log();

        // Update stored name
        if (server.name !== response.server_name) {
          server.name = response.server_name;
          config.serverConfig = server;
        }
      } catch (err) {
        printError(`Connection failed: ${err instanceof Error ? err.message : err}`);
      }
    });
}

/** Normalize a URL — add http:// if no scheme, ensure port. */
function normalizeURL(url: string): string {
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = `http://${url}`;
  }
  // Add default port if none specified and it's http
  try {
    const parsed = new URL(url);
    if (!parsed.port && parsed.protocol === 'http:') {
      parsed.port = String(DEFAULT_PORT);
    }
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return url;
  }
}
