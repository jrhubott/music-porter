import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { MANIFEST_FILENAME } from './constants.js';
import type { SyncManifest, SyncManifestPlaylist } from './types.js';

/** Read a sync manifest from a destination directory. Returns null if not found. */
export function readManifest(destDir: string): SyncManifest | null {
  const path = join(destDir, MANIFEST_FILENAME);
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, 'utf-8');
    return JSON.parse(raw) as SyncManifest;
  } catch {
    return null;
  }
}

/** Write a sync manifest to a destination directory. */
export function writeManifest(destDir: string, manifest: SyncManifest): void {
  const path = join(destDir, MANIFEST_FILENAME);
  writeFileSync(path, JSON.stringify(manifest, null, 2), 'utf-8');
}

/** Returns playlist keys recorded in the manifest at destDir, or [] if none. */
export function readManifestPlaylistKeys(destDir: string): string[] {
  const manifest = readManifest(destDir);
  return manifest ? Object.keys(manifest.playlists) : [];
}

/** Get the cached file map for a playlist from the manifest. */
export function getManifestFiles(
  manifest: SyncManifest | null,
  playlistKey: string,
): Record<string, number> {
  if (!manifest) return {};
  const playlist = manifest.playlists[playlistKey];
  return playlist?.files ?? {};
}

/** Create a new empty manifest. */
export function createManifest(destinationName: string, serverOrigin: string): SyncManifest {
  return {
    destination_name: destinationName,
    server_origin: serverOrigin,
    last_sync_at: new Date().toISOString(),
    playlists: {},
  };
}

/** Remove a specific file entry from the manifest's playlist files map. */
export function removeManifestFile(
  manifest: SyncManifest,
  playlistKey: string,
  filePath: string,
): void {
  const playlist = manifest.playlists[playlistKey];
  if (!playlist) return;
  delete playlist.files[filePath];
}

/** Update the manifest with synced files for a playlist. */
export function updateManifestPlaylist(
  manifest: SyncManifest,
  playlistKey: string,
  files: Record<string, number>,
): void {
  const existing = manifest.playlists[playlistKey];
  const merged: Record<string, number> = existing ? { ...existing.files, ...files } : { ...files };
  const entry: SyncManifestPlaylist = { files: merged };
  manifest.playlists[playlistKey] = entry;
  manifest.last_sync_at = new Date().toISOString();
}
