import { ConfigStore, APIClient } from '@mporter/core';
import { printError } from './formatters.js';
import chalk from 'chalk';

/** Create an APIClient that is configured and connected. Returns null on failure. */
export async function createConnectedClient(): Promise<APIClient | null> {
  const config = new ConfigStore();
  const server = config.serverConfig;
  const apiKey = config.getApiKey();

  if (!server) {
    printError('No server configured. Run "mporter-sync server set-local <url>" first.');
    return null;
  }

  const client = new APIClient();
  client.configure(server.localURL, server.externalURL, apiKey ?? undefined);

  try {
    const response = await client.resolveConnection();
    const state = client.connectionState;
    console.log(
      chalk.dim(
        `Connected to ${response.server_name} via ${state.type === 'external' ? 'external URL' : 'local network'} (${state.activeURL})`,
      ),
    );
    return client;
  } catch (err) {
    printError(`Connection failed: ${err instanceof Error ? err.message : err}`);
    return null;
  }
}
