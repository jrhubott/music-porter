import { createInterface } from 'node:readline';
import { join } from 'node:path';
import chalk from 'chalk';
import { ConfigStore, APIClient, SyncEngine, DriveManager, VERSION } from '@mporter/core';
import { printField, printError, printSuccess, formatBytes, formatDuration } from './formatters.js';
import type { ProfileInfo, SyncProgress } from '@mporter/core';

/** Run the interactive menu (when CLI is invoked with no arguments). */
export async function runInteractiveMode(): Promise<void> {
  console.log(chalk.bold(`\nMusic Porter Sync Client v${VERSION}`));
  console.log(chalk.dim('─'.repeat(40)));

  const config = new ConfigStore();
  const server = config.serverConfig;

  if (!server) {
    console.log('\nNo server configured.');
    console.log(chalk.dim('Run "mporter-sync discover" to find servers, or:'));
    console.log(chalk.dim('  mporter-sync server set-local http://<host>:5555'));
    console.log(chalk.dim('  mporter-sync server set-key <api-key>\n'));
    return;
  }

  const client = new APIClient();
  const apiKey = config.getApiKey();
  client.configure(server.localURL, server.externalURL, apiKey ?? undefined);

  try {
    const response = await client.resolveConnection();
    const state = client.connectionState;
    printField('Server', response.server_name);
    printField('Version', response.version);
    printField(
      'Connection',
      state.type === 'external' ? 'External URL' : 'Local Network',
    );
  } catch (err) {
    printError(`Connection failed: ${err instanceof Error ? err.message : err}`);
    return;
  }

  // Fetch profiles for usb_dir resolution
  let profiles: Record<string, ProfileInfo> = {};
  let activeOutputType = '';
  try {
    const settings = await client.getSettings();
    profiles = settings.profiles;
    activeOutputType = (settings.settings['output_type'] as string) ?? '';
  } catch {
    // Non-critical — profiles not available
  }

  // Resolve active profile: stored preference > server's output_type > first available
  const profileNames = Object.keys(profiles);
  const activeProfileName = config.profile || activeOutputType || profileNames[0] || '';
  const activeProfile = profiles[activeProfileName];
  const usbDir = activeProfile?.usb_dir ?? '';

  if (activeProfileName) {
    printField('Profile', activeProfileName);
  }

  // Show playlists
  const playlists = await client.getPlaylists();
  console.log(`\nPlaylists (${playlists.length}):`);
  playlists.forEach((p, i) => {
    console.log(`  ${chalk.dim(`${i + 1}.`)} ${p.name} ${chalk.dim(`(${p.key})`)}`);
  });

  // Show drives
  const driveManager = new DriveManager();
  const drives = driveManager.listDrives();
  if (drives.length > 0) {
    console.log(`\nDetected Drives:`);
    drives.forEach((d) => {
      const free = d.freeSpace !== undefined ? ` (${formatBytes(d.freeSpace)} free)` : '';
      const usbPath = usbDir ? ` → ${chalk.cyan(join(d.path, usbDir))}` : '';
      console.log(`  ${d.name}${chalk.dim(free)}${usbPath} — ${chalk.dim(d.path)}`);
    });
  }

  // Menu
  console.log('\nActions:');
  console.log(`  ${chalk.bold('S')} — Sync all playlists`);
  console.log(`  ${chalk.bold('1-N')} — Sync specific playlist`);
  console.log(`  ${chalk.bold('D')} — List destinations`);
  console.log(`  ${chalk.bold('X')} — Exit`);

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer = await new Promise<string>((resolve) => {
    rl.question('\nChoice: ', (ans) => {
      rl.close();
      resolve(ans.trim());
    });
  });

  if (answer.toLowerCase() === 'x') {
    return;
  }

  if (answer.toLowerCase() === 'd') {
    const response = await client.getSyncDestinations();
    console.log('\nSaved Destinations:');
    for (const d of response.destinations) {
      console.log(`  ${d.name} — ${d.path}`);
    }
    return;
  }

  // Determine which playlists to sync
  let selectedPlaylists: string[] | undefined;
  const num = parseInt(answer, 10);
  if (!isNaN(num) && num >= 1 && num <= playlists.length) {
    selectedPlaylists = [playlists[num - 1]!.key];
    console.log(`\nSyncing playlist: ${playlists[num - 1]!.name}`);
  } else if (answer.toLowerCase() === 's') {
    console.log('\nSyncing all playlists...');
  } else {
    printError('Invalid choice.');
    return;
  }

  // Pick destination
  let dest = process.cwd();
  let usbDriveName: string | undefined;
  if (drives.length > 0) {
    console.log('\nSelect destination:');
    console.log(`  ${chalk.dim('0.')} Current directory (${process.cwd()})`);
    drives.forEach((d, i) => {
      const targetPath = usbDir ? join(d.path, usbDir) : d.path;
      console.log(`  ${chalk.dim(`${i + 1}.`)} ${d.name} (${targetPath})`);
    });

    const rl2 = createInterface({ input: process.stdin, output: process.stdout });
    const destAnswer = await new Promise<string>((resolve) => {
      rl2.question('\nDestination [0]: ', (ans) => {
        rl2.close();
        resolve(ans.trim() || '0');
      });
    });

    const destNum = parseInt(destAnswer, 10);
    if (destNum >= 1 && destNum <= drives.length) {
      const drive = drives[destNum - 1]!;
      dest = usbDir ? join(drive.path, usbDir) : drive.path;
      usbDriveName = drive.name;
    }
  }

  console.log(`\nSyncing to: ${dest}\n`);

  const engine = new SyncEngine(client);
  const result = await engine.sync(dest, {
    playlists: selectedPlaylists,
    usbDriveName,
    onProgress: (progress: SyncProgress) => {
      if (progress.phase === 'syncing' && progress.file) {
        process.stdout.write(
          `\r  [${progress.processed}/${progress.total}] ${progress.file}`.padEnd(80),
        );
      }
      if (progress.phase === 'complete' || progress.phase === 'aborted') {
        process.stdout.write('\r' + ' '.repeat(80) + '\r');
      }
    },
    onLog: (level, message) => {
      if (level !== 'info') console.log(`  ${message}`);
    },
  });

  console.log();
  if (result.aborted) {
    console.log(chalk.yellow('Sync aborted.'));
  } else {
    printSuccess('Sync complete!');
  }
  printField('Copied', String(result.copied));
  printField('Skipped', String(result.skipped));
  if (result.failed > 0) printField('Failed', chalk.red(String(result.failed)));
  printField('Duration', formatDuration(result.durationMs));
  console.log();
}
