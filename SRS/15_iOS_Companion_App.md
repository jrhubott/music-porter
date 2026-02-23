# SRS 15: iOS Companion App

**Version:** 1.0  |  **Date:** 2026-02-23  |  **Status:** Complete  |  **Implemented in:** v2.8.0

---

## Purpose

Provide a native iOS companion app that connects to the music-porter server over the local network, enabling mobile browsing of playlists, triggering server-side operations (pipeline, convert, tag, cover art), downloading MP3 files to the device, and exporting to USB drives — all authenticated via API key and discoverable via Bonjour/mDNS.

## Requirements

### 15.1 Server Command and Authentication

The `server` subcommand shall start the Flask web server with API key authentication, Bonjour advertisement, and CORS support for iOS clients.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.1.1 | v2.8.0 | [x] | `server` subcommand starts Flask on `0.0.0.0:5555` by default (network-accessible) |
| 15.1.2 | v2.8.0 | [x] | API key generated via `secrets.token_urlsafe(32)` and persisted in `config.yaml` under `settings.api_key` |
| 15.1.3 | v2.8.0 | [x] | Authentication middleware validates `Authorization: Bearer <key>` on all `/api/` routes; returns 401 if missing or invalid |
| 15.1.4 | v2.8.0 | [x] | CORS `after_request` handler sets `Access-Control-Allow-Origin: *`, permits `Authorization` header, and allows GET/POST/PUT/DELETE/OPTIONS methods |
| 15.1.5 | v2.8.0 | [x] | Auth middleware skips OPTIONS requests to allow CORS preflight |
| 15.1.6 | v2.8.0 | [x] | `--no-auth` flag disables authentication middleware (sets `app.config['NO_AUTH']`) |
| 15.1.7 | v2.8.0 | [x] | `--show-api-key` flag displays the full API key at startup |
| 15.1.8 | v2.8.0 | [x] | `--no-bonjour` flag disables Bonjour/mDNS service advertisement |
| 15.1.9 | v2.8.0 | [x] | `POST /api/auth/validate` validates Bearer token and returns server identity (name, version, platform) |
| 15.1.10 | v2.8.0 | [x] | `GET /api/server-info` returns server metadata (name, version, platform, available profiles) |
| 15.1.11 | v2.8.0 | [x] | Startup banner prints connection instructions: local IP, port, API key (masked unless `--show-api-key`), and QR code |

### 15.2 Bonjour/mDNS Discovery

The `BonjourAdvertiser` class shall register the server as a discoverable service on the local network using zeroconf.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.2.1 | v2.8.0 | [x] | Service type registered as `_music-porter._tcp.local.` |
| 15.2.2 | v2.8.0 | [x] | Service name formatted as `"Music Porter on {safe_hostname}._music-porter._tcp.local."` |
| 15.2.3 | v2.8.0 | [x] | mDNS TXT record includes `version`, `platform`, and `api_version` properties |
| 15.2.4 | v2.8.0 | [x] | Local IP determined via UDP socket trick (`connect('10.255.255.255', 1)`) |
| 15.2.5 | v2.8.0 | [x] | Bonjour only starts when host is not `127.0.0.1` (network interfaces only) |
| 15.2.6 | v2.8.0 | [x] | Graceful degradation if `zeroconf` package is not installed (prints skip message) |
| 15.2.7 | v2.8.0 | [x] | Service unregistered on server shutdown (`stop()` called in `finally` block) |
| 15.2.8 | v2.8.0 | [x] | iOS `ServerDiscovery` class uses `NWBrowser` to browse for `_music-porter._tcp` services |
| 15.2.9 | v2.8.0 | [x] | Discovery auto-stops after 10 seconds to conserve battery |
| 15.2.10 | v2.8.0 | [x] | Resolved endpoints deduplicated (one connection per unique server) |

### 15.3 File Serving Endpoints

The server shall provide REST endpoints for listing, downloading, and streaming files from the export directory.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.3.1 | v2.8.0 | [x] | `GET /api/files/<playlist_key>` returns JSON array of MP3 files with ID3 metadata (title, artist, album, duration, size, has\_cover\_art, has\_protection\_tags) |
| 15.3.2 | v2.8.0 | [x] | `GET /api/files/<playlist_key>/<filename>` serves the MP3 file with `audio/mpeg` MIME type |
| 15.3.3 | v2.8.0 | [x] | `GET /api/files/<playlist_key>/<filename>/artwork` extracts and serves the APIC frame image with correct MIME type |
| 15.3.4 | v2.8.0 | [x] | `GET /api/files/<playlist_key>/download-all` streams a ZIP archive of all MP3s (ZIP\_STORED, 64KB chunks) |
| 15.3.5 | v2.8.0 | [x] | All file endpoints validate paths via `_safe_dir()` to prevent directory traversal |
| 15.3.6 | v2.8.0 | [x] | File download validates `.mp3` extension and confirms resolved path stays within safe directory |
| 15.3.7 | v2.8.0 | [x] | File listing response includes `playlist`, `profile`, `file_count`, and `files` array |
| 15.3.8 | v2.8.0 | [x] | Artwork endpoint returns 404 if no APIC frame found in MP3 |

### 15.4 QR Code Pairing

The server shall generate a terminal-displayable QR code containing connection credentials for iOS app pairing.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.4.1 | v2.8.0 | [x] | QR code generated using `segno` library with JSON payload: `{"host": "<ip>", "port": <port>, "key": "<api_key>"}` |
| 15.4.2 | v2.8.0 | [x] | QR rendered to terminal via `segno.terminal()` with compact mode |
| 15.4.3 | v2.8.0 | [x] | Each QR line indented with two spaces for consistent formatting |
| 15.4.4 | v2.8.0 | [x] | Graceful fallback if `segno` not installed (prints install hint) |
| 15.4.5 | v2.8.0 | [x] | QR code displayed as step 4 of the server startup connection guide |

### 15.5 iOS App — Connection Flow

The iOS app shall discover servers via Bonjour, allow manual IP entry, validate API keys, and persist credentials for auto-reconnect.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.5.1 | v2.8.0 | [x] | `ServerDiscoveryView` shown as root view when not connected |
| 15.5.2 | v2.8.0 | [x] | Discovered servers listed with name, host, and port; tap to select |
| 15.5.3 | v2.8.0 | [x] | Manual connection section with server address field (URL keyboard) and port field (default 5555) |
| 15.5.4 | v2.8.0 | [x] | `PairingView` presented as sheet after server selection; accepts API key via `SecureField` |
| 15.5.5 | v2.8.0 | [x] | API key validated against server via `POST /api/auth/validate` |
| 15.5.6 | v2.8.0 | [x] | Validated API key stored in iOS Keychain via `KeychainService` (service ID: `com.musicporter.apikey`) |
| 15.5.7 | v2.8.0 | [x] | Server connection saved to `UserDefaults` as `savedServer` for auto-reconnect |
| 15.5.8 | v2.8.0 | [x] | Auto-reconnect attempted on app launch using saved server and Keychain API key (3-second timeout) |
| 15.5.9 | v2.8.0 | [x] | Failed auto-reconnect falls back to discovery screen silently |
| 15.5.10 | v2.8.0 | [x] | Refresh button in toolbar restarts Bonjour search |

### 15.6 iOS App — Dashboard and Browsing

The iOS app shall display server status, library statistics, and allow browsing playlists and tracks with metadata.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.6.1 | v2.8.0 | [x] | Dashboard tab shows server card: version, active profile, cookie status badge (Valid/Invalid with green/red), expiration days, busy status badge (Idle/Busy with green/orange) |
| 15.6.2 | v2.8.0 | [x] | Dashboard shows library stats card: playlist count, file count, total size in MB |
| 15.6.3 | v2.8.0 | [x] | Dashboard lists all playlists with per-playlist file counts |
| 15.6.4 | v2.8.0 | [x] | Pull-to-refresh on dashboard reloads status and summary |
| 15.6.5 | v2.8.0 | [x] | Playlists tab lists all server playlists with name, key, and file count |
| 15.6.6 | v2.8.0 | [x] | Tapping a playlist navigates to `PlaylistDetailView` showing all tracks |
| 15.6.7 | v2.8.0 | [x] | `TrackRow` component shows artwork thumbnail (44x44, rounded), title, artist, and file size |
| 15.6.8 | v2.8.0 | [x] | Artwork loaded via `AsyncImage` from `/api/files/<key>/<filename>/artwork` endpoint |
| 15.6.9 | v2.8.0 | [x] | Add playlist via plus button in toolbar: form with key, URL, and display name fields |
| 15.6.10 | v2.8.0 | [x] | Delete playlist via swipe-to-delete gesture |

### 15.7 iOS App — Operations and SSE

The iOS app shall trigger server-side operations and display real-time progress via Server-Sent Events.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.7.1 | v2.8.0 | [x] | Pipeline tab provides form with source selection (playlist picker, URL field, or auto-all toggle) |
| 15.7.2 | v2.8.0 | [x] | Pipeline options include quality preset picker (lossless, high, medium, low) and copy-to-USB toggle |
| 15.7.3 | v2.8.0 | [x] | Run Pipeline button triggers `POST /api/pipeline/run` and returns task ID |
| 15.7.4 | v2.8.0 | [x] | `SSEClient` (actor) subscribes to `GET /api/stream/<task_id>` and yields `AsyncStream<SSEEvent>` |
| 15.7.5 | v2.8.0 | [x] | SSE events parsed from `"data: {json}"` lines into typed `SSEEvent` enum: `.log`, `.progress`, `.heartbeat`, `.done` |
| 15.7.6 | v2.8.0 | [x] | `ProgressPanel` component shows progress bar with stage name and percentage during operations |
| 15.7.7 | v2.8.0 | [x] | `ProgressPanel` shows scrollable monospace log with color-coded levels: ERROR=red, WARN=orange, OK=green, SKIP=yellow |
| 15.7.8 | v2.8.0 | [x] | `OperationViewModel` manages operation lifecycle: `run()`, `handleEvent()`, `reset()` |
| 15.7.9 | v2.8.0 | [x] | Completion status shown as green checkmark (success) or red X with error message (failure) |
| 15.7.10 | v2.8.0 | [x] | Form inputs disabled while operation is running |

### 15.8 iOS App — MusicKit Integration

The iOS app shall use MusicKit to browse the user's Apple Music library and send playlist URLs to the server for processing.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.8.1 | v2.8.0 | [x] | `MusicKitService` requests MusicKit authorization on user action (not at launch) |
| 15.8.2 | v2.8.0 | [x] | Authorization prompt shown only when user taps "Authorize Apple Music" button |
| 15.8.3 | v2.8.0 | [x] | `fetchLibraryPlaylists()` retrieves user's library playlists sorted by name |
| 15.8.4 | v2.8.0 | [x] | `searchPlaylists(query:)` searches Apple Music catalog with limit of 25 results |
| 15.8.5 | v2.8.0 | [x] | `AppleMusicBrowserView` lists playlists with name, description, and send-to-server button |
| 15.8.6 | v2.8.0 | [x] | Searchable modifier enables catalog search from the playlist list |
| 15.8.7 | v2.8.0 | [x] | Sending a playlist to server triggers pipeline via `POST /api/pipeline/run` with the playlist URL |
| 15.8.8 | v2.8.0 | [x] | MusicKit cannot export audio due to DRM; all downloads handled server-side |

### 15.9 iOS App — File Downloads

The iOS app shall download MP3 files from the server to local device storage with progress tracking.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.9.1 | v2.8.0 | [x] | `FileDownloadManager` downloads individual MP3 files via `GET /api/files/<key>/<filename>` |
| 15.9.2 | v2.8.0 | [x] | `downloadAll(playlist:)` downloads entire playlist as ZIP via `GET /api/files/<key>/download-all` |
| 15.9.3 | v2.8.0 | [x] | Files stored in `~/Documents/MusicPorter/<playlist>/` on device |
| 15.9.4 | v2.8.0 | [x] | Per-file download state tracked: `.pending`, `.downloading(progress)`, `.completed(URL)`, `.failed(Error)` |
| 15.9.5 | v2.8.0 | [x] | `DownloadView` shows server playlists with file counts and local file counts (green indicator) |
| 15.9.6 | v2.8.0 | [x] | Local storage usage displayed in Downloads tab |
| 15.9.7 | v2.8.0 | [x] | `deletePlaylist(playlist:)` removes locally downloaded files for a playlist |
| 15.9.8 | v2.8.0 | [x] | Background `URLSession` used for resilient file downloads |

### 15.10 iOS App — USB Export

The iOS app shall export downloaded MP3 files to USB drives or external storage via the system document picker.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.10.1 | v2.8.0 | [x] | `USBExportService` presents `UIDocumentPickerViewController` for folder selection |
| 15.10.2 | v2.8.0 | [x] | Supports FAT, ExFAT, HFS+, and APFS formatted drives |
| 15.10.3 | v2.8.0 | [x] | `USBSyncView` lists downloaded playlists with selectable checkmarks |
| 15.10.4 | v2.8.0 | [x] | Export button shows count of selected playlists |
| 15.10.5 | v2.8.0 | [x] | File copy progress tracked via `exportProgress` (0.0–1.0) |
| 15.10.6 | v2.8.0 | [x] | `ExportResult` reports success status, files copied count, and message |
| 15.10.7 | v2.8.0 | [x] | Security-scoped URLs used for accessing external storage (iOS sandbox compliance) |

### 15.11 iOS App — Settings

The iOS app shall display server connection details, available profiles, and provide access to advanced operations.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.11.1 | v2.8.0 | [x] | Settings tab shows server host:port and server name |
| 15.11.2 | v2.8.0 | [x] | Disconnect button (red, destructive) clears server, API key, and Keychain data |
| 15.11.3 | v2.8.0 | [x] | Profiles section lists available output profiles with descriptions |
| 15.11.4 | v2.8.0 | [x] | Operations navigation link shows task history with status badges (completed=green, running=blue, failed=red, cancelled=orange) |
| 15.11.5 | v2.8.0 | [x] | Apple Music navigation link opens `AppleMusicBrowserView` |
| 15.11.6 | v2.8.0 | [x] | USB navigation link opens `USBSyncView` |
| 15.11.7 | v2.8.0 | [x] | About section shows app version |

### 15.12 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.12.1 | v2.8.0 | [x] | IPv6 addresses: `ServerDiscovery` extracts mapped IPv4 from IPv6 (e.g., `::ffff:192.168.1.100` → `192.168.1.100`) |
| 15.12.2 | v2.8.0 | [x] | Scope IDs stripped from resolved addresses (e.g., `%bridge101`, `%en0` removed) |
| 15.12.3 | v2.8.0 | [x] | Network timeout: auto-reconnect uses 3-second timeout; failure falls back to discovery silently |
| 15.12.4 | v2.8.0 | [x] | Server busy (HTTP 409): `APIError.serverBusy` returned when attempting operation while another is running |
| 15.12.5 | v2.8.0 | [x] | Stale reconnect data: if saved server is unreachable, app falls back to discovery screen without error toast |
| 15.12.6 | v2.8.0 | [x] | Empty playlist directory: file listing returns empty `files` array with `file_count: 0` |
| 15.12.7 | v2.8.0 | [x] | Missing cover art: artwork endpoint returns 404; `TrackRow` shows music note placeholder |
| 15.12.8 | v2.8.0 | [x] | URL construction uses `URLComponents` to properly handle IPv6 addresses and special characters |
| 15.12.9 | v2.8.0 | [x] | All `@Observable` ViewModels annotated with `@MainActor` for thread-safe UI updates |
| 15.12.10 | v2.8.0 | [x] | Bonjour discovery deduplicates servers (one connection per unique host:port) |
