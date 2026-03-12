import { readdirSync, statSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { join } from 'node:path';
import { DRIVE_POLL_INTERVAL_MS } from './constants.js';
import { currentPlatform, getExcludedVolumes, getUSBMountPaths } from './platform.js';
import type { DriveInfo } from './types.js';

export type DriveChangeCallback = (added: DriveInfo[], removed: DriveInfo[]) => void;

/** Cross-platform USB drive detection and hotplug monitoring. */
export class DriveManager {
  private previousDrives: Map<string, DriveInfo> = new Map();
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private changeCallback: DriveChangeCallback | null = null;

  /** Detect currently mounted USB/external drives. */
  listDrives(): DriveInfo[] {
    const platform = currentPlatform();
    switch (platform) {
      case 'darwin':
        return this.listMacDrives();
      case 'linux':
        return this.listLinuxDrives();
      case 'win32':
        return this.listWindowsDrives();
    }
  }

  /** Start polling for drive changes. */
  startWatching(callback: DriveChangeCallback): void {
    this.changeCallback = callback;
    this.previousDrives = new Map(this.listDrives().map((d) => [d.path, d]));

    this.pollTimer = setInterval(() => {
      this.checkForChanges();
    }, DRIVE_POLL_INTERVAL_MS);
  }

  /** Stop polling for drive changes. */
  stopWatching(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.changeCallback = null;
  }

  /** Eject a drive (macOS and Linux only). */
  ejectDrive(path: string): boolean {
    const platform = currentPlatform();
    try {
      if (platform === 'darwin') {
        execSync(`diskutil eject "${path}"`, { stdio: 'pipe' });
        return true;
      } else if (platform === 'linux') {
        execSync(`udisksctl unmount -b "${path}"`, { stdio: 'pipe' });
        return true;
      }
    } catch {
      return false;
    }
    // Windows: manual eject required
    return false;
  }

  // ── Platform-specific detection ──

  private listMacDrives(): DriveInfo[] {
    const excluded = new Set(getExcludedVolumes());
    const drives: DriveInfo[] = [];
    try {
      const entries = readdirSync('/Volumes');
      for (const name of entries) {
        if (excluded.has(name)) continue;
        const path = join('/Volumes', name);
        try {
          const stat = statSync(path);
          if (stat.isDirectory()) {
            drives.push({
              name,
              path,
              freeSpace: this.getFreeSpace(path),
              volumeId: this.getVolumeId(path),
            });
          }
        } catch {
          // Skip inaccessible volumes
        }
      }
    } catch {
      // /Volumes not readable
    }
    return drives;
  }

  private listLinuxDrives(): DriveInfo[] {
    const drives: DriveInfo[] = [];
    const mountPaths = getUSBMountPaths();

    for (const mountBase of mountPaths) {
      try {
        const entries = readdirSync(mountBase);
        for (const name of entries) {
          const path = join(mountBase, name);
          try {
            const stat = statSync(path);
            if (stat.isDirectory()) {
              drives.push({
                name,
                path,
                freeSpace: this.getFreeSpace(path),
                volumeId: this.getVolumeId(path),
              });
            }
          } catch {
            // Skip inaccessible
          }
        }
      } catch {
        // Mount path not readable
      }
    }
    return drives;
  }

  private listWindowsDrives(): DriveInfo[] {
    const drives: DriveInfo[] = [];
    try {
      const output = execSync(
        'wmic logicaldisk where "drivetype=2" get name,freespace,volumename /format:csv',
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] },
      );
      const lines = output.trim().split('\n').filter((l) => l.trim());
      // Skip header line
      for (let i = 1; i < lines.length; i++) {
        const parts = lines[i]!.split(',');
        if (parts.length >= 4) {
          const freeSpace = parts[1] ? parseInt(parts[1], 10) : undefined;
          const name = parts[3]?.trim() || parts[2]?.trim() || 'USB Drive';
          const path = parts[2]?.trim() ?? '';
          if (path) {
            drives.push({
              name,
              path,
              freeSpace: freeSpace && !isNaN(freeSpace) ? freeSpace : undefined,
              volumeId: this.getVolumeId(path),
            });
          }
        }
      }
    } catch {
      // wmic not available or failed
    }
    return drives;
  }

  /** Get the filesystem UUID for a mounted volume path. Returns undefined on failure. */
  private getVolumeId(mountPath: string): string | undefined {
    try {
      if (currentPlatform() === 'darwin') {
        return this.getVolumeIdMac(mountPath);
      } else if (currentPlatform() === 'linux') {
        return this.getVolumeIdLinux(mountPath);
      } else if (currentPlatform() === 'win32') {
        return this.getVolumeIdWindows(mountPath);
      }
    } catch {
      // Fall through
    }
    return undefined;
  }

  private getVolumeIdMac(mountPath: string): string | undefined {
    try {
      const output = execSync(`diskutil info -plist "${mountPath}"`, {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 5000,
      });
      // Extract VolumeUUID from plist XML using a simple regex (no stdlib XML parser needed)
      const match = output.match(/<key>VolumeUUID<\/key>\s*<string>([^<]+)<\/string>/);
      if (match) return match[1];
      const fallback = output.match(/<key>DiskUUID<\/key>\s*<string>([^<]+)<\/string>/);
      if (fallback) return fallback[1];
    } catch {
      // diskutil not available or failed
    }
    return undefined;
  }

  private getVolumeIdLinux(mountPath: string): string | undefined {
    try {
      const output = execSync(`findmnt -no UUID "${mountPath}"`, {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 5000,
      });
      const uuid = output.trim();
      return uuid || undefined;
    } catch {
      // findmnt not available or failed
    }
    return undefined;
  }

  private getVolumeIdWindows(mountPath: string): string | undefined {
    try {
      // PowerShell fallback: Get-Volume UniqueId
      const driveLetter = mountPath.replace(/[:\\]+$/, '');
      const output = execSync(
        `powershell -Command "(Get-Volume -DriveLetter ${driveLetter}).UniqueId"`,
        { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'], timeout: 5000 },
      );
      const guid = output.trim();
      return guid || undefined;
    } catch {
      // PowerShell not available or failed
    }
    return undefined;
  }

  /** Get free space on a mounted volume (macOS/Linux). */
  private getFreeSpace(path: string): number | undefined {
    try {
      const output = execSync(`df -k "${path}"`, {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      const lines = output.trim().split('\n');
      if (lines.length >= 2) {
        const parts = lines[1]!.split(/\s+/);
        const availKB = parts[3] ? parseInt(parts[3], 10) : NaN;
        const KB_TO_BYTES = 1024;
        if (!isNaN(availKB)) return availKB * KB_TO_BYTES;
      }
    } catch {
      // df not available
    }
    return undefined;
  }

  private checkForChanges(): void {
    const currentDrives = new Map(this.listDrives().map((d) => [d.path, d]));

    const added: DriveInfo[] = [];
    const removed: DriveInfo[] = [];

    for (const [path, drive] of currentDrives) {
      if (!this.previousDrives.has(path)) {
        added.push(drive);
      }
    }

    for (const [path, drive] of this.previousDrives) {
      if (!currentDrives.has(path)) {
        removed.push(drive);
      }
    }

    this.previousDrives = currentDrives;

    if ((added.length > 0 || removed.length > 0) && this.changeCallback) {
      this.changeCallback(added, removed);
    }
  }
}
