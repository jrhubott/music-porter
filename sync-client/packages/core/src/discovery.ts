import { spawn } from 'node:child_process';
import { lookup } from 'node:dns';
import { platform } from 'node:os';
import { BONJOUR_SERVICE_TYPE, BONJOUR_BROWSE_TIMEOUT_MS } from './constants.js';
import type { DiscoveredServer } from './types.js';

export type DiscoveryCallback = (servers: DiscoveredServer[]) => void;

const RESOLVE_TIMEOUT_MS = 3000;
const SERVICE_TYPE_WITH_DOT = `${BONJOUR_SERVICE_TYPE}.`;

/**
 * mDNS service browser for discovering music-porter servers.
 *
 * On macOS, uses the system `dns-sd` tool (talks to Apple's mDNSResponder)
 * which is far more reliable than pure-JS multicast-dns. On other platforms,
 * falls back to `bonjour-service`.
 */
export class ServerDiscovery {
  private servers: Map<string, DiscoveredServer> = new Map();
  private callback: DiscoveryCallback | null = null;
  private stopTimer: ReturnType<typeof setTimeout> | null = null;
  private activeProcesses: ReturnType<typeof spawn>[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private fallbackBonjour: any = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private fallbackBrowser: any = null;

  /** Start browsing for music-porter servers on the local network. */
  startSearch(callback: DiscoveryCallback): void {
    this.stopSearch();
    this.servers.clear();
    this.callback = callback;

    if (platform() === 'darwin') {
      this.startMacOSSearch();
    } else {
      this.startFallbackSearch();
    }

    this.stopTimer = setTimeout(() => {
      this.stopSearch();
    }, BONJOUR_BROWSE_TIMEOUT_MS);
  }

  /** Stop browsing. */
  stopSearch(): void {
    if (this.stopTimer) {
      clearTimeout(this.stopTimer);
      this.stopTimer = null;
    }
    for (const proc of this.activeProcesses) {
      proc.kill();
    }
    this.activeProcesses = [];
    if (this.fallbackBrowser) {
      this.fallbackBrowser.stop();
      this.fallbackBrowser = null;
    }
    if (this.fallbackBonjour) {
      this.fallbackBonjour.destroy();
      this.fallbackBonjour = null;
    }
  }

  /** Get currently discovered servers. */
  get discoveredServers(): DiscoveredServer[] {
    return [...this.servers.values()];
  }

  // ── macOS: dns-sd + Node DNS ──

  private startMacOSSearch(): void {
    const proc = spawn('dns-sd', ['-B', BONJOUR_SERVICE_TYPE], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    this.activeProcesses.push(proc);

    let buffer = '';
    proc.stdout.on('data', (data: Buffer) => {
      buffer += data.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.includes('Add')) continue;
        const svcIdx = line.indexOf(SERVICE_TYPE_WITH_DOT);
        if (svcIdx < 0) continue;
        const instanceName = line.slice(svcIdx + SERVICE_TYPE_WITH_DOT.length).trim();
        if (instanceName) {
          this.resolveInstance(instanceName);
        }
      }
    });
  }

  /** Resolve a discovered instance using `dns-sd -L` to get host, port, and TXT records. */
  private resolveInstance(instanceName: string): void {
    const proc = spawn('dns-sd', ['-L', instanceName, BONJOUR_SERVICE_TYPE, 'local'], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    this.activeProcesses.push(proc);

    let output = '';
    const timer = setTimeout(() => proc.kill(), RESOLVE_TIMEOUT_MS);

    proc.stdout.on('data', (data: Buffer) => {
      output += data.toString();
      if (output.includes('can be reached at')) {
        clearTimeout(timer);
        proc.kill();
        this.parseAndResolve(instanceName, output);
      }
    });

    proc.on('close', () => {
      clearTimeout(timer);
    });
  }

  /** Parse dns-sd -L output, then resolve the hostname to an IP via Node DNS. */
  private parseAndResolve(instanceName: string, output: string): void {
    // Match: "XXX can be reached at hostname:port (interface N)"
    const reachMatch = output.match(/can be reached at\s+(\S+):(\d+)/);
    if (!reachMatch) return;

    const hostname = reachMatch[1]!;
    const port = parseInt(reachMatch[2]!, 10);

    // Extract TXT record key=value pairs from the output
    const txt: Record<string, string> = {};
    const txtLine = output.split('\n').find((l) => l.includes('=') && !l.includes('can be reached'));
    if (txtLine) {
      const pairs = txtLine.matchAll(/(\w+)=(\S+)/g);
      for (const m of pairs) {
        txt[m[1]!] = m[2]!;
      }
    }

    // Resolve hostname to IP using Node's built-in DNS (uses macOS resolver)
    lookup(hostname, { family: 4 }, (err, address) => {
      if (err || !address) return;

      const id = `${address}:${port}`;
      if (this.servers.has(id)) return;

      const server: DiscoveredServer = {
        name: instanceName,
        host: address,
        port,
        version: txt['version'],
        platform: txt['platform'],
        apiVersion: txt['api_version'] ? parseInt(txt['api_version'], 10) : undefined,
      };

      this.servers.set(id, server);
      this.callback?.([...this.servers.values()]);
    });
  }

  // ── Fallback: bonjour-service (Linux/Windows) ──

  private async startFallbackSearch(): Promise<void> {
    try {
      const { Bonjour } = await import('bonjour-service');
      this.fallbackBonjour = new Bonjour();
      this.fallbackBrowser = this.fallbackBonjour.find(
        { type: BONJOUR_SERVICE_TYPE },
        (service: { name: string; port: number; addresses?: string[]; txt?: Record<string, string> }) => {
          const host = this.resolveHost(service);
          if (!host) return;

          const id = `${host}:${service.port}`;
          if (this.servers.has(id)) return;

          const server: DiscoveredServer = {
            name: service.name,
            host,
            port: service.port,
            version: service.txt?.['version'],
            platform: service.txt?.['platform'],
            apiVersion: service.txt?.['api_version']
              ? parseInt(service.txt['api_version'], 10)
              : undefined,
          };

          this.servers.set(id, server);
          this.callback?.([...this.servers.values()]);
        },
      );
    } catch {
      // bonjour-service not available
    }
  }

  /** Resolve the IPv4 address from a service (fallback path). */
  private resolveHost(service: { addresses?: string[] }): string | null {
    if (!service.addresses || service.addresses.length === 0) return null;

    for (const addr of service.addresses) {
      if (addr.includes(':')) {
        const IPV4_MAPPED_PREFIX = '::ffff:';
        if (addr.startsWith(IPV4_MAPPED_PREFIX)) {
          return addr.slice(IPV4_MAPPED_PREFIX.length);
        }
        continue;
      }
      return addr;
    }

    return service.addresses[0] ?? null;
  }
}
