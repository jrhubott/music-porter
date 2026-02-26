# SRS 17: Client-Side Sync

**Version:** 1.0  |  **Date:** 2026-02-26  |  **Status:** In Progress  |  **Target:** v2.29.0

---

## Purpose

Enable web dashboard users to sync playlists to USB drives or folders
connected to their **client** machine (browser), not just destinations
accessible from the server. Two complementary approaches: the File System
Access API (Chromium browsers) for incremental folder sync, and a multi-playlist
ZIP download (all browsers) for bulk export.

## Requirements

### 17.1 Multi-Playlist ZIP Download API

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.1.1 | v2.29.0 | [x] | `POST /api/files/download-zip` accepts JSON body `{"playlists": ["key1", "key2", ...]}` |
| 17.1.2 | v2.29.0 | [x] | Response is a streamed ZIP archive with `Content-Disposition: attachment; filename="music-porter-export.zip"` |
| 17.1.3 | v2.29.0 | [x] | ZIP uses `ZIP_STORED` compression (MP3s are already compressed) |
| 17.1.4 | v2.29.0 | [x] | ZIP contains one subdirectory per playlist, each containing the playlist's MP3 files |
| 17.1.5 | v2.29.0 | [x] | Returns HTTP 413 if total file count across all playlists exceeds 2000 |
| 17.1.6 | v2.29.0 | [x] | Returns HTTP 400 if `playlists` array is empty or missing |
| 17.1.7 | v2.29.0 | [x] | Each playlist directory is validated with `safe_dir()` before inclusion |
| 17.1.8 | v2.29.0 | [x] | Uses `ctx.get_output_profile()` to resolve the correct export directory |
| 17.1.9 | v2.29.0 | [x] | Playlists with no MP3 files are silently skipped (not an error) |

### 17.2 Client Sync Tracking API

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.2.1 | v2.29.0 | [x] | `POST /api/sync/client-record` accepts JSON body `{"sync_key": "client-<name>", "playlist": "<key>", "files": ["file1.mp3", ...]}` |
| 17.2.2 | v2.29.0 | [x] | Calls `ctx.sync_tracker.record_batch(sync_key, playlist, files)` to persist tracking |
| 17.2.3 | v2.29.0 | [x] | Returns HTTP 400 if `sync_key`, `playlist`, or `files` is missing |
| 17.2.4 | v2.29.0 | [x] | Returns HTTP 400 if `sync_tracker` is not available |
| 17.2.5 | v2.29.0 | [x] | Logs to audit with operation `client_sync_record` including sync_key, playlist, and file count |
| 17.2.6 | v2.29.0 | [x] | Client sync keys appear in existing Sync Keys tracking table on the web UI |

### 17.3 Client-Side Sync UI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.3.1 | v2.29.0 | [x] | New "Client-Side Sync" card appears on `/sync` page between the Output card and Section 2: Sync Status |
| 17.3.2 | v2.29.0 | [x] | Card header shows browser support badge: green "Chromium" if `showDirectoryPicker` is available, yellow "ZIP Only" otherwise |
| 17.3.3 | v2.29.0 | [x] | Info alert explains Chromium requirement when File System Access API is not available |
| 17.3.4 | v2.29.0 | [x] | Playlist checkboxes are loaded from `GET /api/directories/export` with Select All / Select None links |
| 17.3.5 | v2.29.0 | [x] | "Sync to Local Folder" button is only visible when File System Access API is supported |
| 17.3.6 | v2.29.0 | [x] | "Download as ZIP" button is always visible |
| 17.3.7 | v2.29.0 | [x] | Progress bar (1.4rem height, `bg-info`) shows per-file progress during File System Access sync |
| 17.3.8 | v2.29.0 | [x] | Result summary alert shows copied/skipped/failed counts after sync completes |

### 17.4 File System Access API Sync (JavaScript)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.4.1 | v2.29.0 | [x] | Calls `showDirectoryPicker({mode: 'readwrite'})` to let user select target folder |
| 17.4.2 | v2.29.0 | [x] | Creates one subdirectory per selected playlist in the target folder |
| 17.4.3 | v2.29.0 | [x] | Fetches file list per playlist via `GET /api/files/<key>` |
| 17.4.4 | v2.29.0 | [x] | Skips files that already exist in target directory with matching size (incremental sync) |
| 17.4.5 | v2.29.0 | [x] | Downloads each new file via `GET /api/files/<key>/<filename>` and writes via `FileSystemWritableFileStream` |
| 17.4.6 | v2.29.0 | [x] | After each playlist completes, reports synced files to `POST /api/sync/client-record` |
| 17.4.7 | v2.29.0 | [x] | Progress bar updates per-file with current file name |
| 17.4.8 | v2.29.0 | [x] | `AbortError` from user cancelling the directory picker is silently ignored |
| 17.4.9 | v2.29.0 | [x] | Network or write errors are logged per-file; sync continues with remaining files |
| 17.4.10 | v2.29.0 | [x] | `QuotaExceededError` is caught and displayed as a disk full warning |
| 17.4.11 | v2.29.0 | [x] | On sync start, reads `.music-porter-sync.json` from selected directory; reuses stored `sync_key` if present |
| 17.4.12 | v2.29.0 | [x] | Files in manifest with matching size are skipped without filesystem checks |
| 17.4.13 | v2.29.0 | [x] | On sync completion, writes `.music-porter-sync.json` with sync_key, server_origin, last_sync_at, and per-playlist file maps |
| 17.4.14 | v2.29.0 | [x] | If manifest is missing or unparseable, sync proceeds normally (generates key from folder name, checks all files on disk) |
| 17.4.15 | v2.29.0 | [x] | Each file is recorded to the server DB individually via `POST /api/sync/client-record` as it is copied or skipped (realtime tracking) |
| 17.4.16 | v2.29.0 | [x] | Per-file server recording is fire-and-forget (non-blocking, non-fatal) |
| 17.4.17 | v2.29.0 | [x] | Sync Keys table has a browser-sync button (pc-display icon) that triggers client-side sync for that key |
| 17.4.18 | v2.29.0 | [x] | Playlist Breakdown table has a per-playlist browser-sync button |
| 17.4.19 | v2.29.0 | [x] | Browser-sync buttons are only visible when File System Access API is available |
| 17.4.20 | v2.29.0 | [x] | Syncing to an existing (non-client) key does not auto-register a web-client:// destination |
| 17.4.21 | v2.29.0 | [x] | The local manifest is written with the chosen key name so future syncs reuse it |

### 17.5 ZIP Download Flow (JavaScript)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.5.1 | v2.29.0 | [x] | Single playlist download uses existing `GET /api/files/<key>/download-all` endpoint |
| 17.5.2 | v2.29.0 | [x] | Multiple playlist download uses `POST /api/files/download-zip` and triggers download via blob URL |
| 17.5.3 | v2.29.0 | [x] | Download button is disabled during ZIP generation and re-enabled on completion |

### 17.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.6.1 | v2.29.0 | [x] | No playlists selected: action buttons are disabled with tooltip "Select at least one playlist" |
| 17.6.2 | v2.29.0 | [x] | Empty export directory (no playlists): card body shows "No exported playlists found" message |
| 17.6.3 | v2.29.0 | [x] | Server mode with API key auth: fetch calls include credentials for cookie-based sessions |
| 17.6.4 | v2.29.0 | [x] | File System Access sync in progress: both action buttons are disabled until complete |

### 17.7 web-client:// Destination Type

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.7.1 | v2.29.0 | [x] | `SyncDestination.type` returns `'web-client'` for paths with `web-client://` scheme |
| 17.7.2 | v2.29.0 | [x] | `SyncDestination.available` returns `True` for `web-client` type |
| 17.7.3 | v2.29.0 | [x] | `ConfigManager.add_destination()` accepts `web-client://` scheme and skips filesystem validation |
| 17.7.4 | v2.29.0 | [x] | `POST /api/sync/client-record` auto-registers a `web-client://` destination in config on first sync |
| 17.7.5 | v2.29.0 | [x] | `POST /api/sync/run` rejects `web-client` destinations with HTTP 400 |
| 17.7.6 | v2.29.0 | [x] | Sync Keys table shows `bi-pc-display` icon for web-client keys |
| 17.7.7 | v2.29.0 | [x] | Saved Destinations table shows "Client" badge (blue) for web-client destinations |
| 17.7.8 | v2.29.0 | [x] | Server-side sync dropdown excludes web-client destinations |
