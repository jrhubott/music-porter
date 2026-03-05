# iOS Companion App — CLAUDE.md

Context for the iOS companion app (`ios/MusicPorter/`). See the root `CLAUDE.md` for project-wide conventions (branching, SRS, versioning, commit preferences).

## Overview

Native SwiftUI app connecting to music-porter server over local network. Simplified 3-tab interface focused on the core flow: **Browse Apple Music -> Add Playlist -> Sync to USB**. Also supports downloading MP3s, triggering server-side operations, and audio playback.

## Requirements

- iOS 17+ (uses `@Observable` macro)
- Xcode 15+
- Apple Developer Program membership for MusicKit entitlement and device testing
- Server running with `./music-porter server` (not `web`)

## iOS App Versioning

The iOS app has its **own independent version**, decoupled from the server's version.

- Version constant: `MusicPorterApp.appVersion` in `MusicPorterApp.swift`
- Only bump when iOS code changes — NOT on every server version bump
- Uses semantic versioning (e.g., `1.1.0`)
- Displayed in Settings > About
- `MARKETING_VERSION` in Xcode project.pbxproj is the App Store version (may differ)

## Architecture

### Navigation Structure (3 tabs)

| Tab | View | Purpose |
|-----|------|---------|
| Library | `LibraryView` | Segmented control: "My Playlists" (server playlists with download/export) and "Apple Music" (MusicKit browse/search/add). Guided flow after adding playlists. |
| Process | `PipelineView` | Simplified pipeline form (playlist picker + Process button). Advanced options behind DisclosureGroup. Embedded task history. Post-process USB export prompt. |
| Settings | `SettingsView` | Server info, disconnect, sync status nav link, server dashboard nav link, profiles, about (with iOS version). |

### Models (9 files)

Codable structs matching server JSON responses:

- `ServerConnection` — Host, port, name, version, platform; computed `baseURL` and `apiURL(path:)` helper
- `ServerStatus` — Version, `CookieStatus` (validity, days remaining), `LibraryStats` (playlists, files, size), busy flag
- `Playlist` — Key, URL, name
- `Track` — Filename, size, duration, title, artist, album, uuid, hasCoverArt; computed `displayTitle`
- `ExportDirectory` — Name and file count
- `FileListResponse` — Playlist key, fileCount, files array
- `SSEEvent` — Enum: `.log(level, message)`, `.progress(current, total, percent, stage)`, `.heartbeat`, `.done(status, result, error)`
- `TaskInfo` — Task id, operation, description, status, result, error, elapsed; computed `isRunning`, `isCompleted`, `isFailed`
- `USBSyncStatus` — `SyncStatusSummary`, `SyncPlaylistInfo`, `SyncStatusDetail`, `ResetTrackingResponse`, `SyncDestination`, `SyncDestinationsResponse`, `ResolveDestinationResponse`

### Services (9 files + Cache module)

Network and platform services:

- `APIClient` — `@MainActor @Observable` REST client; all endpoint methods (status, playlists CRUD, pipeline/convert operations, file downloads with optional profile for tagged output, settings, sync destinations/status); ETag support for conditional requests (`getWithETag`, `getFilesWithETag`); `downloadFileData` for raw file downloads; `APIError` enum with `.notConfigured`, `.unauthorized`, `.serverBusy`, `.serverError`
- `SSEClient` — Swift actor; `events(taskId:)` returns `AsyncStream<SSEEvent>` from `GET /api/stream/<task_id>`; parses `"data: {json}"` lines
- `ServerDiscovery` — `@MainActor @Observable`; uses `NWBrowser` for `_music-porter._tcp` Bonjour browsing; resolves endpoints to IP:port; 10-second auto-stop
- `MusicKitService` — `@MainActor @Observable`; `requestAuthorization()`, `fetchLibraryPlaylists()`, `searchPlaylists(query:)` (limit 25); read-only due to DRM
- `FileDownloadManager` — `@MainActor @Observable`; `downloadFile()`, `downloadAll()`, `localFiles()`, `deletePlaylist()`; stores in `~/Documents/MusicPorter/<playlist>/`; background `URLSession`
- `USBExportService` — `@Observable`; `exportFiles(groups:to:profile:)` creates playlist subdirectories matching server sync behavior; passes profile for tagged server downloads; `PlaylistExportGroup` struct for grouped export; security-scoped URL access
- `AudioPlayerService` — `@MainActor @Observable`; dual-engine playback (AVPlayer for server tracks, ApplicationMusicPlayer for Apple Music); queue management, skip, seek; Now Playing Info Center integration
- `KeychainService` — Static methods: `save(apiKey:)`, `load()`, `delete()`; service ID: `com.musicporter.apikey`

### Cache Module (6 files in `Services/Cache/`)

Offline audio file caching and API response metadata caching. All cache classes are Swift actors (not `@MainActor`) for thread-safe file I/O off the main thread. Wired into `AppState` — initialized per-profile on connect.

- `CacheConstants` — Named constants matching sync client's `cache/constants.ts` (cache dir names, filenames, schema version, size limits, concurrency)
- `CacheTypes` — Codable structs for JSON serialization: `CacheEntry` (snake\_case, cache-index.json), `CachedFileInfo`/`CachedPlaylistData`/`MetadataCacheData` (camelCase, metadata-cache.json), `ETagResult<T>`, `PrefetchResult`, `PrefetchOptions`, `PrefetchProgress`, `PlaylistCacheStatus`
- `CacheUtils` — Static utility methods: `loadJsonIndex`/`saveJsonIndex` (atomic JSON read/write with fallback), `removeEmptyDirs`, `atomicCopyFile`, `cacheBaseDirectory`/`cacheDirectory(profile:)`, `isoNow`, `formatBytes`
- `MetadataCache` — Actor managing `metadata-cache.json` (playlist file lists + ETags). Methods: `getPlaylistFiles`, `getCachedPlaylists`, `getETag`, `storePlaylistFiles`, `removePlaylist`, `clearAll`
- `AudioCacheManager` — Actor managing `cache-index.json` + audio files at `<cacheDir>/<profile>/<playlist>/<display_filename>.mp3`. Store/retrieve cached audio, staleness detection, eviction (unpinned first, then oldest), playlist/full cache clearing
- `PrefetchEngine` — Actor for background prefetching. Prunes stale entries, fetches file lists with ETag, filters cached entries, downloads concurrently via TaskGroup, mid/post-download eviction, cancellable via structured concurrency

**Storage:** `<Application Support>/MusicPorter/cache/<profile>/` — one directory per output profile, containing `metadata-cache.json`, `cache-index.json`, and `<playlist>/<display_filename>.mp3` audio files.

**JSON format compatibility:** This cache module mirrors the sync client's implementation (`sync-client/packages/core/src/cache/`). Both must use identical JSON formats, schema versions, and cache invalidation behavior. When modifying cache logic here, update the sync client implementation to match.

### ViewModels (5 files)

`@MainActor @Observable` state management:

- `AppState` — Global state injected via SwiftUI environment; owns all services; `connect()`, `disconnect()`, `attemptAutoReconnect()` (3-second timeout); tab coordination (`selectedTab`, `pendingPipelinePlaylist`); persists `savedServer` in UserDefaults
- `DashboardViewModel` — Loads `ServerStatus` and `SummaryResponse` in parallel
- `PlaylistsViewModel` — Playlists + export directories + Apple Music state; add/delete playlist methods; guided flow state (`lastAddedPlaylist`, `showProcessPrompt`)
- `PlaylistDetailViewModel` — Track listing for a single playlist
- `OperationViewModel` — Operation lifecycle: `run()` triggers API call then SSE streaming; `handleEvent()` processes log/progress/done; `isCompleted` computed property; `reset()` clears state

### Views

SwiftUI with enforced dark theme:

| View | Purpose |
|------|---------|
| `MusicPorterApp` | App entry point; `appVersion` constant; creates `AppState`, injects as environment, enforces `.dark` color scheme |
| `ContentView` | Root view: shows `ServerDiscoveryView` if disconnected, `MainTabView` if connected |
| `MainTabView` | Bottom tab bar: Library, Process, Settings (3 tabs); MiniPlayer overlay |
| `LibraryView` | Segmented control ("My Playlists" / "Apple Music"); playlist download/export; Apple Music browse/add; guided flow banner |
| `PipelineView` | Simplified pipeline form + DisclosureGroup advanced options + task history + post-process USB export |
| `SettingsView` | Server info, disconnect, sync status nav, server dashboard nav, profiles, about |
| `ServerDiscoveryView` | Bonjour discovery list + manual IP entry; presents `PairingView` as sheet |
| `PairingView` | SecureField for API key; validates and stores credentials |
| `DashboardView` | Server status card, library stats, sync status, playlist overview; accessed from Settings |
| `PlaylistDetailView` | Track list with `TrackRow` components; pull-to-refresh |
| `OperationsView` | Full task history with status badges; accessed from Process tab "View All" |
| `SyncStatusView` | Destination groups, playlist detail, saved destinations; accessed from Settings |
| `AppleMusicPlaylistDetailView` | Apple Music playlist track listing with playback |
| `QRScannerView` | QR code scanner for pairing |
| `TrackRow` | Reusable: artwork thumbnail (44x44), title, artist, size |
| `StatusBadge` | Colored capsule badge (Valid/Invalid, Idle/Busy, completed/failed) |
| `ProgressPanel` | Progress bar + scrollable monospace log; color-coded levels |
| `MiniPlayerView` | Overlay player: play/pause, skip, seek, artwork |
| `DocumentExportPicker` | UIDocumentPickerViewController wrapper for USB folder selection |

### Guided Flow

When a user adds a playlist from Apple Music:
1. Success banner appears: "Playlist added! Process it now?"
2. "Process Now" button sets `pendingPipelinePlaylist` on `AppState` and switches to Process tab
3. PipelineView detects the pending playlist and pre-selects it
4. After processing completes, "Export to USB" button appears

### USB Export Directory Structure

Files are exported with playlist subdirectories matching the server's sync behavior:
```
dest/<playlist_name>/Artist - Title.mp3
```

`USBExportService.exportFiles(groups:to:)` accepts `[PlaylistExportGroup]` (playlist name + file URLs) and creates subdirectories automatically. The user is informed that subdirectories will be created within their chosen location.

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

## Connection Flow (Dual-URL)

The app uses a local-first, external-fallback connection model:

1. App launches -> `ServerDiscoveryView` browses for `_music-porter._tcp` via Bonjour
2. User selects discovered server (or enters IP manually)
3. `PairingView` — enter API key or scan QR code (QR includes optional external URL)
4. `AppState.connect()` → `resolveConnection()`:
   - Try local URL (3-second timeout when external exists, 10-second otherwise)
   - If local fails and external URL exists, try external URL (10-second timeout)
   - Set `APIClient.activeBaseURL` and `connectionType` on success
5. After auth validation, fetch `/api/server-info` to get external URL if not already set
6. `ServerConnection` saved to UserDefaults; API key stored in Keychain
7. Auto-reconnect on next launch uses same dual-URL fallback

**Connection indicator:** Settings shows house icon (local) or globe icon (external) with both URLs visible.

## Key Constraints

- **DRM protection**: MusicKit can browse playlists/metadata but CANNOT export audio. All downloads and conversions must happen on the server.
- **USB drives**: iOS supports USB drives since iOS 13 via `UIDocumentPickerViewController` (FAT, ExFAT, HFS+, APFS).
- **Background downloads**: Uses `URLSession` for file downloads with progress tracking.
- **One operation at a time**: Server enforces single background task (HTTP 409 if busy).

## Key Implementation Notes

- All `@Observable` classes must be annotated with `@MainActor` for thread-safe UI updates
- URL construction uses `URLComponents` (never string interpolation) to handle IPv6 addresses and special characters
- `ServerConnection.localURL` is a computed property constructing `http://host:port`; `externalURL` is stored from QR code or server-info
- `APIClient.activeBaseURL` is the resolved URL used for all API calls; `connectionType` tracks local vs external
- `APIClient` includes Bearer token in all requests via a shared `authenticatedRequest(for:)` helper
- `SSEClient` is a Swift actor (not `@MainActor`) for background streaming without blocking UI
- `FileDownloadManager` uses background `URLSessionConfiguration` for resilient downloads
- `AppState` is injected as SwiftUI environment object; all services instantiated there
- Dark color scheme enforced at app level via `.preferredColorScheme(.dark)`
- Tab coordination: `AppState.selectedTab` and `pendingPipelinePlaylist` enable guided flow between Library and Process tabs

## Additional Resources

- **IOS-COMPANION-GUIDE.md** (root) — iOS companion app setup, pairing, and usage guide
