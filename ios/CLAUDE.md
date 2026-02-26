# iOS Companion App — CLAUDE.md

Context for the iOS companion app (`ios/MusicPorter/`). See the root `CLAUDE.md` for project-wide conventions (branching, SRS, versioning, commit preferences).

## Overview

Native SwiftUI app connecting to music-porter server over local network. Provides mobile interface for browsing playlists, triggering server-side operations, downloading MP3s, and exporting to USB drives.

## Requirements

- iOS 17+ (uses `@Observable` macro)
- Xcode 15+
- Apple Developer Program membership for MusicKit entitlement and device testing
- Server running with `./music-porter server` (not `web`)

## Architecture

### Models (9 files)

Codable structs matching server JSON responses:

- `ServerConnection` — Host, port, name, version, platform; computed `baseURL` and `apiURL(path:)` helper
- `ServerStatus` — Version, `CookieStatus` (validity, days remaining), `LibraryStats` (playlists, files, size), profile, busy flag
- `Playlist` — Key, URL, name
- `Track` — Filename, size, duration, title, artist, album, hasCoverArt, hasProtectionTags; computed `displayTitle`
- `ExportDirectory` — Name and file count
- `FileListResponse` — Playlist key, profile, fileCount, files array
- `SSEEvent` — Enum: `.log(level, message)`, `.progress(current, total, percent, stage)`, `.heartbeat`, `.done(status, result, error)`
- `TaskInfo` — Task id, operation, description, status, result, error, elapsed; computed `isRunning`, `isCompleted`, `isFailed`
- `USBSyncStatus` — `SyncKeySummary`, `SyncPlaylistInfo`, `SyncStatusDetail`, `SyncPruneResult`, `SyncDestination`, `SyncDestinationsResponse`

### Services (7 files)

Network and platform services:

- `APIClient` — `@MainActor @Observable` REST client; all endpoint methods (status, playlists CRUD, pipeline/convert/tag operations, file downloads, settings, sync destinations/status); `APIError` enum with `.notConfigured`, `.unauthorized`, `.serverBusy`, `.serverError`
- `SSEClient` — Swift actor; `events(taskId:)` returns `AsyncStream<SSEEvent>` from `GET /api/stream/<task_id>`; parses `"data: {json}"` lines
- `ServerDiscovery` — `@MainActor @Observable`; uses `NWBrowser` for `_music-porter._tcp` Bonjour browsing; resolves endpoints to IP:port; 10-second auto-stop
- `MusicKitService` — `@MainActor @Observable`; `requestAuthorization()`, `fetchLibraryPlaylists()`, `searchPlaylists(query:)` (limit 25); read-only due to DRM
- `FileDownloadManager` — `@MainActor @Observable`; `downloadFile()`, `downloadAll()` (ZIP), `localFiles()`, `deletePlaylist()`; stores in `~/Documents/MusicPorter/<playlist>/`; background `URLSession`
- `USBExportService` — `@Observable`; `UIDocumentPickerViewController` integration; `exportFiles()` with progress tracking; security-scoped URL access
- `KeychainService` — Static methods: `save(apiKey:)`, `load()`, `delete()`; service ID: `com.musicporter.apikey`

### ViewModels (5 files)

`@MainActor @Observable` state management:

- `AppState` — Global state injected via SwiftUI environment; owns all services; `connect()`, `disconnect()`, `attemptAutoReconnect()` (3-second timeout); persists `savedServer` in UserDefaults
- `DashboardViewModel` — Loads `ServerStatus` and `SummaryResponse` in parallel
- `PlaylistsViewModel` — Playlists + export directories; add/delete playlist methods
- `PlaylistDetailViewModel` — Track listing for a single playlist
- `OperationViewModel` — Operation lifecycle: `run()` triggers API call then SSE streaming; `handleEvent()` processes log/progress/done; `reset()` clears state

### Views (13 files + 3 components)

SwiftUI with enforced dark theme:

| View | Purpose |
|------|---------|
| `MusicPorterApp` | App entry point; creates `AppState`, injects as environment, enforces `.dark` color scheme |
| `ContentView` | Root view: shows `ServerDiscoveryView` if disconnected, `MainTabView` if connected |
| `MainTabView` | Bottom tab bar: Dashboard, Playlists, Pipeline, Downloads, Settings |
| `ServerDiscoveryView` | Bonjour discovery list + manual IP entry; presents `PairingView` as sheet |
| `PairingView` | SecureField for API key; validates and stores credentials |
| `DashboardView` | Server status card, library stats card, sync status, playlist overview; pull-to-refresh |
| `PlaylistsView` | Playlist list with add (+) and swipe-to-delete; navigates to detail |
| `PlaylistDetailView` | Track list with `TrackRow` components; pull-to-refresh |
| `PipelineView` | Pipeline form (source, preset, sync toggle) + `ProgressPanel` |
| `DownloadView` | Server playlists with download buttons; local storage display |
| `SettingsView` | Server info, profiles, disconnect, navigation to operations/sync status/Apple Music/USB |
| `OperationsView` | Task history with status badges (green/blue/red/orange) |
| `AppleMusicBrowserView` | MusicKit authorization, library browse, catalog search, send-to-server |
| `USBSyncView` | Playlist selection with checkmarks, export button, progress bar |
| `TrackRow` | Reusable: artwork thumbnail (44x44), title, artist, size |
| `StatusBadge` | Colored capsule badge (Valid/Invalid, Idle/Busy, completed/failed) |
| `ProgressPanel` | Progress bar + scrollable monospace log; color-coded levels |

## Server-Side Requirements

The iOS app requires `./music-porter server` (not `web`). Key differences:

| Feature | `web` | `server` |
|---------|-------|----------|
| Default host | `127.0.0.1` (local only) | `0.0.0.0` (network) |
| API key auth | Disabled | Required |
| Bonjour/mDNS | Disabled | Enabled |
| QR code pairing | No | Yes |
| iOS app support | No | Yes |

### iOS-Specific API Endpoints

Added for the iOS companion app (in addition to existing web dashboard endpoints):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/validate` | Validate API key, returns server identity |
| GET | `/api/server-info` | Server metadata (name, version, platform, profiles) |
| GET | `/api/files/<playlist_key>` | File listing with ID3 metadata |
| GET | `/api/files/<playlist_key>/<filename>` | Download single MP3 file (`audio/mpeg`) |
| GET | `/api/files/<playlist_key>/<filename>/artwork` | Extract cover art image from APIC frame |
| GET | `/api/files/<playlist_key>/download-all` | Streaming ZIP archive of all MP3s |

### Authentication Middleware

- All `/api/` routes require `Authorization: Bearer <api_key>` header
- API key generated via `secrets.token_urlsafe(32)`, persisted in `config.yaml` under `settings.api_key`
- CORS headers: `Access-Control-Allow-Origin: *`, permits `Authorization` header
- OPTIONS (preflight) requests skip auth check

## Bonjour/mDNS Discovery

**Server side (`BonjourAdvertiser` in `web_ui.py`):**

- Registers `_music-porter._tcp.local.` service via `zeroconf` library
- Broadcasts: service name, host IP, port, TXT record with version/platform/api\_version
- Local IP determined via UDP socket trick (connect to `10.255.255.255:1`)
- Only starts when `host != '127.0.0.1'`; gracefully skips if zeroconf not installed
- Unregistered on server shutdown in `finally` block

**iOS side (`ServerDiscovery`):**

- Uses `NWBrowser` to discover `_music-porter._tcp` services
- Resolves Bonjour endpoints to IP:port connections
- Extracts IPv4 from IPv6-mapped addresses (`::ffff:192.168.1.100` -> `192.168.1.100`)
- Strips interface scope IDs (`%bridge101`, `%en0`) from resolved addresses
- Auto-stops after 10 seconds; manual refresh available
- Deduplicates (one entry per unique host:port)

## QR Code Pairing

- Server generates QR code using `segno` library
- JSON payload: `{"host": "<ip>", "port": <port>, "key": "<api_key>"}`
- Rendered to terminal via `segno.terminal()` with compact mode
- Graceful fallback if `segno` not installed (prints install hint)

## Connection Flow

1. App launches -> `ServerDiscoveryView` browses for `_music-porter._tcp` via Bonjour
2. User selects discovered server (or enters IP manually)
3. `PairingView` — enter API key (displayed on server startup) or scan QR code
4. Key validated via `POST /api/auth/validate`, stored in iOS Keychain
5. Auto-reconnect on next launch using saved server + Keychain key (3-second timeout)

## Key Constraints

- **DRM protection**: MusicKit can browse playlists/metadata but CANNOT export audio. All downloads and conversions must happen on the server.
- **USB drives**: iOS supports USB drives since iOS 13 via `UIDocumentPickerViewController` (FAT, ExFAT, HFS+, APFS).
- **Background downloads**: Uses `URLSession` for file downloads with progress tracking.
- **One operation at a time**: Server enforces single background task (HTTP 409 if busy).

## Key Implementation Notes

- All `@Observable` classes must be annotated with `@MainActor` for thread-safe UI updates
- URL construction uses `URLComponents` (never string interpolation) to handle IPv6 addresses and special characters
- `ServerConnection.baseURL` is a computed property constructing `http://host:port`
- `APIClient` includes Bearer token in all requests via a shared `authenticatedRequest(for:)` helper
- `SSEClient` is a Swift actor (not `@MainActor`) for background streaming without blocking UI
- `FileDownloadManager` uses background `URLSessionConfiguration` for resilient downloads
- `AppState` is injected as SwiftUI environment object; all services instantiated there
- Dark color scheme enforced at app level via `.preferredColorScheme(.dark)`

## Additional Resources

- **IOS-COMPANION-GUIDE.md** (root) — iOS companion app setup, pairing, and usage guide
