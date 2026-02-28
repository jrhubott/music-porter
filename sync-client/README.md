# Music Porter Sync Client

Cross-platform desktop sync client for [music-porter](../README.md). Connects to a `music-porter server` instance over your local network and syncs playlists to USB drives or local folders. Available as both an Electron GUI app and a CLI tool.

## Prerequisites

- **Node.js** 16+ and **npm** 8+
- A running `music-porter server` instance (see the main project README)

## Installation

From the `sync-client/` directory:

```bash
npm install
npm run build
```

This installs dependencies and builds all three workspace packages (core, cli, gui).

## Electron GUI App

### Development Mode

Run these in two separate terminals from `packages/gui/`:

```bash
# Terminal 1 — Vite dev server (hot-reload for renderer)
npm run dev

# Terminal 2 — Launch Electron
npm start
```

### Quick Launch

After building (`npm run build` from the `sync-client/` root), run the app directly:

```bash
cd packages/gui
npm start
```

No packaging or installation required — this launches Electron from the build output.

### Production Build

```bash
cd packages/gui
npm run pack
```

This uses electron-builder to produce a distributable package in `packages/gui/out/`:

| Platform | Output | Launch |
|----------|--------|--------|
| macOS | `Music Porter Sync.dmg` | Open the DMG and drag to Applications |
| Windows | `Music Porter Sync Setup.exe` | Run the installer |
| Linux | `Music-Porter-Sync.AppImage` | `chmod +x` and run, or install the `.deb` |

### Using the App

1. Launch the app — you'll land on the **Connect** page
2. Enter your server's URL and API key, or use **Discover** to find servers on the local network via Bonjour/mDNS
3. Once connected, browse playlists, select a destination (USB drive or folder), and sync

## CLI Tool

### Running

From the `sync-client/` directory after building:

```bash
node packages/cli/dist/index.js
```

Or link it globally for the `mporter-sync` command:

```bash
cd packages/cli
npm link
mporter-sync
```

Running with no arguments launches interactive mode.

### Quick Launch

After building (`npm run build` from the `sync-client/` root), run the CLI directly:

```bash
node packages/cli/dist/index.js
```

Running with no arguments launches interactive mode. Pass commands and flags as normal:

```bash
node packages/cli/dist/index.js list playlists
node packages/cli/dist/index.js sync --help
```

### Commands

| Command | Description |
|---------|-------------|
| `mporter-sync server configure` | Set server URL and API key |
| `mporter-sync server status` | Check connection to server |
| `mporter-sync discover` | Browse for servers via Bonjour/mDNS |
| `mporter-sync list playlists` | List available playlists |
| `mporter-sync list files <playlist>` | List files in a playlist |
| `mporter-sync status` | Show sync key status |
| `mporter-sync sync` | Sync playlists to a destination |
| `mporter-sync destinations` | List available drives and saved destinations |

Use `mporter-sync --help` or `mporter-sync <command> --help` for full usage details.

## Connecting to a Server

The sync client connects to a `music-porter server` instance, which provides API key authentication and Bonjour/mDNS advertising.

Start the server from the main project:

```bash
./music-porter server
./music-porter server --show-api-key    # Display the API key on startup
```

### GUI

Use the Connect page to enter the server URL and API key, or tap **Discover** to find advertised servers automatically.

### CLI

```bash
mporter-sync server configure
```

You'll be prompted for the server URL and API key. Configuration is stored in a platform-appropriate location:

| Platform | Config Path |
|----------|-------------|
| macOS | `~/Library/Application Support/mporter-sync/` |
| Linux | `~/.config/mporter-sync/` |
| Windows | `%APPDATA%/mporter-sync/` |

API keys are stored securely: Electron's safeStorage for the GUI, a 0600-permission file for the CLI.

### Settings and Configuration

Both the CLI and GUI store configuration in a `config.json` file at the platform-appropriate location shown above. The config file contains:

- **Server connection** — name, local URL, external URL
- **Preferences** — download concurrency, auto-sync on USB insert, notification settings

The API key is stored separately from the config file for security: the GUI uses Electron's `safeStorage` encryption, while the CLI writes it to a dedicated `api-key` file with `0600` permissions (owner read/write only).

## Local Audio Cache

The sync client includes a local audio cache that stores downloaded files on disk for faster syncing and offline use.

### How It Works

When you sync playlists, downloaded files are automatically written through to the local cache. On subsequent syncs, files already in cache are used instead of re-downloading from the server. This means:

- **First sync** downloads from the server and caches locally
- **Repeat syncs** to the same or different destinations are near-instant
- **Offline syncs** work entirely from cached files when the server is unreachable

### Cache Storage

Files are stored per-profile and per-playlist in the config directory:

| Platform | Cache Path |
|----------|------------|
| macOS | `~/Library/Application Support/mporter-sync/cache/<profile>/<playlist>/` |
| Linux | `~/.config/mporter-sync/cache/<profile>/<playlist>/` |
| Windows | `%APPDATA%/mporter-sync/cache/<profile>/<playlist>/` |

Each cached file uses its human-readable display filename (e.g., `Artist - Title.mp3`). A `cache-index.json` file in each profile directory tracks all cached entries with metadata.

### Pinning and Prefetch

Playlists can be **pinned** to mark them for background caching. Pinned playlists are automatically prefetched (downloaded to cache) so they're ready for offline use or instant sync.

- **Pin/unpin** individual playlists in the GUI (SyncPage) or CLI (`cache pin`/`cache unpin`)
- **Auto-pin** new playlists with the "Auto-Pin New Playlists" setting — all current and future server playlists are automatically pinned, while still allowing manual unpin of specific playlists
- **Background prefetch** (GUI) — when pinned playlists exist and the server is reachable, the app periodically checks for new files and caches them automatically
- **Manual prefetch** (CLI) — run `mporter-sync cache prefetch` to download all pinned playlist files to cache

### Cache Eviction

When the cache exceeds the configured maximum size, files are evicted based on their **server creation time** — the oldest files on the server are removed first. This ensures the newest content is always available in cache for offline use.

If a file is re-converted or updated on the server, the cache detects the change via the server's `updated_at` timestamp and re-downloads the file on the next prefetch cycle.

The default cache limit is 10 GB. Configure it in the GUI (Settings > Local Cache > Max Cache Size) or CLI.

### Offline Mode

When the server is unreachable, the sync client can operate in offline mode using only cached files:

- **GUI** — click "Continue Offline" on the Connect page (appears when cache has data), or "Go Offline" in Settings
- **CLI** — use `mporter-sync sync --offline` to sync from cache only

Offline sync copies cached files to the destination without contacting the server.

### CLI Cache Commands

| Command | Description |
|---------|-------------|
| `mporter-sync cache status` | Show cache size, pinned playlists, and per-playlist status |
| `mporter-sync cache pin <playlist>` | Pin a playlist for prefetch |
| `mporter-sync cache unpin <playlist>` | Unpin a playlist |
| `mporter-sync cache list` | List cached files |
| `mporter-sync cache prefetch` | Download all pinned playlist files to cache |
| `mporter-sync cache clear` | Clear the entire cache |
| `mporter-sync cache auto-pin <on\|off>` | Enable/disable automatic pinning of new playlists |

## Helper Scripts

Shell scripts in the `sync-client/` directory for common workflows. All scripts can be run from any directory.

| Script | Description |
|--------|-------------|
| `setup-and-build.sh` | Install dependencies and build all packages (`npm install && npm run build`) |
| `run-gui.sh` | Launch the Electron app from build output |
| `run-cli.sh` | Launch the CLI from build output (pass args: `./run-cli.sh list playlists`) |
| `dev-gui.sh` | Start Vite dev server + Electron together for GUI development |

## Project Structure

```
sync-client/
  packages/
    core/   @mporter/core  — Shared TypeScript library (API client, sync engine,
                              drive detection, Bonjour discovery, config storage)
    cli/    @mporter/cli   — CLI tool (mporter-sync)
    gui/    @mporter/gui   — Electron + React desktop app
```

Built as an npm workspaces monorepo. The core package is consumed by both the CLI and GUI.
