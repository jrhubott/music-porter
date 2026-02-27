import Bonjour from 'bonjour-service';
import { BONJOUR_SERVICE_TYPE, BONJOUR_BROWSE_TIMEOUT_MS } from './constants.js';
import type { DiscoveredServer } from './types.js';

export type DiscoveryCallback = (servers: DiscoveredServer[]) => void;

/** Bonjour/mDNS service browser for discovering music-porter servers. */
export class ServerDiscovery {
  private bonjour: InstanceType<typeof Bonjour> | null = null;
  private browser: ReturnType<InstanceType<typeof Bonjour>['find']> | null = null;
  private servers: Map<string, DiscoveredServer> = new Map();
  private callback: DiscoveryCallback | null = null;
  private stopTimer: ReturnType<typeof setTimeout> | null = null;

  /** Start browsing for music-porter servers on the local network. */
  startSearch(callback: DiscoveryCallback): void {
    this.stopSearch();
    this.servers.clear();
    this.callback = callback;

    this.bonjour = new Bonjour();
    this.browser = this.bonjour.find({ type: BONJOUR_SERVICE_TYPE }, (service) => {
      const host = this.resolveHost(service);
      if (!host) return;

      const port = service.port;
      const id = `${host}:${port}`;

      if (this.servers.has(id)) return;

      const server: DiscoveredServer = {
        name: service.name,
        host,
        port,
        version: service.txt?.['version'] as string | undefined,
        platform: service.txt?.['platform'] as string | undefined,
        apiVersion: service.txt?.['api_version']
          ? parseInt(service.txt['api_version'] as string, 10)
          : undefined,
      };

      this.servers.set(id, server);
      this.callback?.([...this.servers.values()]);
    });

    // Auto-stop after timeout
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
    if (this.browser) {
      this.browser.stop();
      this.browser = null;
    }
    if (this.bonjour) {
      this.bonjour.destroy();
      this.bonjour = null;
    }
  }

  /** Get currently discovered servers. */
  get discoveredServers(): DiscoveredServer[] {
    return [...this.servers.values()];
  }

  /** Resolve the IPv4 address from a service. */
  private resolveHost(service: { addresses?: string[] }): string | null {
    if (!service.addresses || service.addresses.length === 0) return null;

    // Prefer IPv4 addresses
    for (const addr of service.addresses) {
      // Skip IPv6 link-local and other non-routable addresses
      if (addr.includes(':')) {
        // Check for IPv4-mapped IPv6 (::ffff:192.168.x.x)
        const IPV4_MAPPED_PREFIX = '::ffff:';
        if (addr.startsWith(IPV4_MAPPED_PREFIX)) {
          return addr.slice(IPV4_MAPPED_PREFIX.length);
        }
        continue;
      }
      return addr;
    }

    // Fall back to first address
    return service.addresses[0] ?? null;
  }
}
