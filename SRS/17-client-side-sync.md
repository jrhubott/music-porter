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
| 17.1.1 | v2.29.0 | [ ] | `POST /api/files/download-zip` accepts JSON body `{"playlists": ["key1", "key2", ...]}` |
| 17.1.2 | v2.29.0 | [ ] | Response is a streamed ZIP archive with `Content-Disposition: attachment; filename="music-porter-export.zip"` |
| 17.1.3 | v2.29.0 | [ ] | ZIP uses `ZIP_STORED` compression (MP3s are already compressed) |
| 17.1.4 | v2.29.0 | [ ] | ZIP contains one subdirectory per playlist, each containing the playlist's MP3 files |
| 17.1.5 | v2.29.0 | [ ] | Returns HTTP 413 if total file count across all playlists exceeds 2000 |
| 17.1.6 | v2.29.0 | [ ] | Returns HTTP 400 if `playlists` array is empty or missing |
| 17.1.7 | v2.29.0 | [ ] | Each playlist directory is validated with `safe_dir()` before inclusion |
| 17.1.8 | v2.29.0 | [ ] | Uses `ctx.get_output_profile()` to resolve the correct export directory |
| 17.1.9 | v2.29.0 | [ ] | Playlists with no MP3 files are silently skipped (not an error) |

### 17.2 Client Sync Tracking API

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.2.1 | v2.29.0 | [ ] | `POST /api/sync/client-record` accepts JSON body `{"sync_key": "client-<name>", "playlist": "<key>", "files": ["file1.mp3", ...]}` |
| 17.2.2 | v2.29.0 | [ ] | Calls `ctx.sync_tracker.record_batch(sync_key, playlist, files)` to persist tracking |
| 17.2.3 | v2.29.0 | [ ] | Returns HTTP 400 if `sync_key`, `playlist`, or `files` is missing |
| 17.2.4 | v2.29.0 | [ ] | Returns HTTP 400 if `sync_tracker` is not available |
| 17.2.5 | v2.29.0 | [ ] | Logs to audit with operation `client_sync_record` including sync_key, playlist, and file count |
| 17.2.6 | v2.29.0 | [ ] | Client sync keys appear in existing Sync Keys tracking table on the web UI |

### 17.3 Client-Side Sync UI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.3.1 | v2.29.0 | [ ] | New "Client-Side Sync" card appears on `/sync` page between the Output card and Section 2: Sync Status |
| 17.3.2 | v2.29.0 | [ ] | Card header shows browser support badge: green "Chromium" if `showDirectoryPicker` is available, yellow "ZIP Only" otherwise |
| 17.3.3 | v2.29.0 | [ ] | Info alert explains Chromium requirement when File System Access API is not available |
| 17.3.4 | v2.29.0 | [ ] | Playlist checkboxes are loaded from `GET /api/directories/export` with Select All / Select None links |
| 17.3.5 | v2.29.0 | [ ] | "Sync to Local Folder" button is only visible when File System Access API is supported |
| 17.3.6 | v2.29.0 | [ ] | "Download as ZIP" button is always visible |
| 17.3.7 | v2.29.0 | [ ] | Progress bar (1.4rem height, `bg-info`) shows per-file progress during File System Access sync |
| 17.3.8 | v2.29.0 | [ ] | Result summary alert shows copied/skipped/failed counts after sync completes |

### 17.4 File System Access API Sync (JavaScript)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.4.1 | v2.29.0 | [ ] | Calls `showDirectoryPicker({mode: 'readwrite'})` to let user select target folder |
| 17.4.2 | v2.29.0 | [ ] | Creates one subdirectory per selected playlist in the target folder |
| 17.4.3 | v2.29.0 | [ ] | Fetches file list per playlist via `GET /api/files/<key>` |
| 17.4.4 | v2.29.0 | [ ] | Skips files that already exist in target directory with matching size (incremental sync) |
| 17.4.5 | v2.29.0 | [ ] | Downloads each new file via `GET /api/files/<key>/<filename>` and writes via `FileSystemWritableFileStream` |
| 17.4.6 | v2.29.0 | [ ] | After each playlist completes, reports synced files to `POST /api/sync/client-record` |
| 17.4.7 | v2.29.0 | [ ] | Progress bar updates per-file with current file name |
| 17.4.8 | v2.29.0 | [ ] | `AbortError` from user cancelling the directory picker is silently ignored |
| 17.4.9 | v2.29.0 | [ ] | Network or write errors are logged per-file; sync continues with remaining files |
| 17.4.10 | v2.29.0 | [ ] | `QuotaExceededError` is caught and displayed as a disk full warning |

### 17.5 ZIP Download Flow (JavaScript)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.5.1 | v2.29.0 | [ ] | Single playlist download uses existing `GET /api/files/<key>/download-all` endpoint |
| 17.5.2 | v2.29.0 | [ ] | Multiple playlist download uses `POST /api/files/download-zip` and triggers download via blob URL |
| 17.5.3 | v2.29.0 | [ ] | Download button is disabled during ZIP generation and re-enabled on completion |

### 17.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 17.6.1 | v2.29.0 | [ ] | No playlists selected: action buttons are disabled with tooltip "Select at least one playlist" |
| 17.6.2 | v2.29.0 | [ ] | Empty export directory (no playlists): card body shows "No exported playlists found" message |
| 17.6.3 | v2.29.0 | [ ] | Server mode with API key auth: fetch calls include credentials for cookie-based sessions |
| 17.6.4 | v2.29.0 | [ ] | File System Access sync in progress: both action buttons are disabled until complete |
