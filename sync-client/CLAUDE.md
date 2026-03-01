# Sync Client — CLAUDE.md

Context for the standalone sync client (`sync-client/`). See the root `CLAUDE.md` for project-wide conventions (branching, SRS, versioning, commit preferences).

## Overview

Cross-platform desktop sync client for music-porter. Connects to `./music-porter server` via API and syncs playlists to USB drives or local folders. Three packages: shared core library, CLI tool (`mporter-sync`), and Electron GUI app.

## Architecture

### Monorepo Structure (npm workspaces)

```
sync-client/
  packages/
    core/    — @mporter/core: Shared TypeScript library
    cli/     — @mporter/cli: CLI tool (mporter-sync binary)
    gui/     — @mporter/gui: Electron + React desktop app
```

### Core (@mporter/core)

Shared library consumed by both CLI and GUI:
- `types.ts` — All shared interfaces (API responses, sync, drives, config)
- `constants.ts` — Named constants (no magic numbers per project rules)
- `errors.ts` — Custom error hierarchy (MPorterError base)
- `platform.ts` — OS detection, config dirs, USB mount paths
- `api-client.ts` — HTTP client with dual-URL connection resolution
- `sync-engine.ts` — Download + incremental sync with manifest optimization
- `manifest.ts` — Read/write `.music-porter-sync.json`
- `drive-manager.ts` — Cross-platform USB detection + hotplug polling
- `discovery.ts` — Bonjour/mDNS service browsing
- `config-store.ts` — Persistent JSON config with secure API key storage
- `progress.ts` — Callback types for progress reporting

### Cache Module (`packages/core/src/cache/`)

Offline audio file caching and API response metadata caching:

- `constants.ts` — Named constants (cache dir names, filenames, size limits)
- `types.ts` — TypeScript interfaces for cache data structures: `CacheEntry` (snake\_case JSON for cache-index.json), `CachedPlaylistData`/`MetadataCacheData` (camelCase JSON for metadata-cache.json), `PrefetchResult`, `PlaylistCacheStatus`, `BackgroundPrefetchStatus`
- `cache-utils.ts` — Utility functions: `loadJsonIndex`/`saveJsonIndex` (atomic JSON read/write with fallback), `removeEmptyDirs`, `atomicCopyFile`
- `metadata-cache.ts` — `MetadataCache` class managing `metadata-cache.json` (playlist file lists + ETags). Schema versioned (`METADATA_CACHE_VERSION = 1`)
- `cache-manager.ts` — `CacheManager` class managing `cache-index.json` + audio files at `<configDir>/cache/<profile>/<playlist>/<display_filename>`. Store/retrieve cached audio (streaming or file-based), staleness detection, eviction (unpinned first, then oldest), playlist/full cache clearing
- `prefetch-engine.ts` — `PrefetchEngine` class for background prefetching with concurrent workers, capacity-aware eviction, and AbortSignal cancellation

**Storage:** `<configDir>/cache/<profile>/` — one directory per output profile, containing `metadata-cache.json`, `cache-index.json`, and `<playlist>/<display_filename>` audio files.

**JSON format compatibility:** The iOS companion app (`ios/`) implements an equivalent cache module in Swift. Both must use identical JSON formats, schema versions, and cache invalidation behavior. When modifying cache logic, types, or file formats here, update the iOS implementation in `ios/MusicPorter/MusicPorter/Services/Cache/` to match.

### CLI (@mporter/cli)

Binary: `mporter-sync`. Uses commander for subcommand parsing.

Commands: `server` (connection mgmt), `discover` (mDNS browse), `list` (playlists/files), `status` (sync keys), `sync` (download to destination), `destinations` (drives + saved).

Interactive mode when invoked with no arguments.

### GUI (@mporter/gui)

Electron 33+ with React 19 renderer. Bootstrap 5.3.3 dark theme (bundled locally).

Process separation:
- **Main**: Full OS access, hosts core library instances, IPC, tray, drive watcher
- **Preload**: Typed `contextBridge` API surface
- **Renderer**: Sandboxed React app (`contextIsolation: true`, `nodeIntegration: false`)

State management: Zustand store (`app-state.ts`).

Pages: ConnectPage, PlaylistsPage, SyncPage, DestinationsPage, SettingsPage.

## Versioning

The sync client has its **own independent version**, decoupled from the server's version.

- Version constant: `VERSION` in `packages/core/src/constants.ts`
- Only bumped when sync client code changes — NOT on every server version bump
- Uses semantic versioning (e.g., `1.0.0`)
- Displayed in GUI Settings > About and `mporter-sync --version`

## Commands

```bash
# From sync-client/
npm install                     # Install all dependencies
npm run build                   # Build all packages
npm run lint                    # ESLint across all packages
npm run lint:fix                # ESLint auto-fix
npm run format                  # Prettier format
npm run format:check            # Prettier check
npm run typecheck               # tsc --noEmit all packages

# CLI development
cd packages/cli
npm run build && node dist/index.js

# GUI development
cd packages/gui
npm run dev                     # Vite dev server for renderer
npm start                       # Launch Electron
npm run pack                    # Build distributable
```

## Key Patterns

### Dual-URL Connection

Single server with local-first, external-fallback:
1. Try local URL (3-second timeout when external exists, 10-second otherwise)
2. If local fails and external URL configured, try external (10-second timeout)
3. Track `connectionType` ('local' | 'external') for UI indicator

### Sync Engine

Replicates browser sync flow from `templates/sync.html`:
1. Read `.music-porter-sync.json` manifest from destination
2. Resolve sync key (explicit > manifest > `client-<dirname>`)
3. For each playlist: fetch file list, check manifest/disk for skip, download new
4. Atomic writes (`.tmp` + rename), concurrent downloads (default: 4)
5. Record synced files to server via `POST /api/sync/client-record`
6. Update manifest after each playlist

### Config Storage

Platform-appropriate locations:
- macOS: `~/Library/Application Support/mporter-sync/`
- Linux: `~/.config/mporter-sync/`
- Windows: `%APPDATA%/mporter-sync/`

API keys stored separately: safeStorage (GUI) / 0600-permission file (CLI).

## Key Dependencies

| Package | Purpose |
|---------|---------|
| commander | CLI framework |
| chalk, cli-progress | CLI output |
| bonjour-service | mDNS discovery |
| electron | Desktop framework |
| react, zustand | Renderer UI + state |
| bootstrap | Dark theme CSS |
| vite | Renderer bundler |
