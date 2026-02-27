# SRS 20: iOS Direct Export (Server Fallback)

**Version:** 1.0  |  **Date:** 2026-02-26  |  **Status:** Draft

---

## Purpose

Enhance the iOS USB export flow so that files missing from local device storage are transparently fetched from the server during export, eliminating the requirement to download all files to the device before exporting to USB. Local files are preferred when available (fast copy); missing files are streamed from the server on the fly. A user-facing toggle controls whether server-fetched files are also cached to local device storage.

This mirrors the existing dual-source pattern in `AudioPlayerService`, which already falls back to server streaming when no local file exists for playback.

---

## Requirements

### 20.1 Transparent Server Fallback During Export

The `USBExportService` shall export files to USB using local copies when available, falling back to fetching from the server for files not present on the device.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.1.1 | | [x] | For each file in the export list, `USBExportService` checks if a local copy exists in `~/Documents/MusicPorter/<playlist>/`; if present, copies from local storage (existing behavior) |
| 20.1.2 | | [x] | If no local copy exists, `USBExportService` downloads the file from the server via `GET /api/files/<playlist>/<filename>` and writes it directly to the USB destination |
| 20.1.3 | | [x] | Server downloads use the authenticated `APIClient` (Bearer token in Authorization header) |
| 20.1.4 | | [x] | The export flow no longer requires all files to be downloaded locally before the "Export to USB" button is enabled |
| 20.1.5 | | [x] | Export progress (`exportProgress`, `currentFileName`) updates identically for both local copies and server-fetched files |
| 20.1.6 | | [x] | Server fetch failures for individual files are handled the same as local copy failures: logged, counted, and the batch continues |

### 20.2 Export Source Indication

The export progress UI shall distinguish between files copied locally and files fetched from the server.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.2.1 | | [x] | `ExportResult` includes a breakdown of files copied from local storage vs. files fetched from the server |
| 20.2.2 | | [x] | The completion message reports both counts (e.g., "Exported 42 files (30 local, 12 from server)") |
| 20.2.3 | | [x] | During export, the progress display indicates whether the current file is being copied locally or fetched from the server (e.g., different icon or label prefix) |

### 20.3 Optional Local Caching of Server-Fetched Files

A user-facing toggle shall control whether files fetched from the server during export are also saved to local device storage.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.3.1 | | [x] | An "Also save to device" toggle is displayed in the export flow UI (before or alongside the export button) |
| 20.3.2 | | [x] | When the toggle is ON, files fetched from the server are written to both the USB destination and `~/Documents/MusicPorter/<playlist>/` |
| 20.3.3 | | [x] | When the toggle is OFF (default), server-fetched files are written only to the USB destination — no local copy is created |
| 20.3.4 | | [x] | The toggle state persists across app sessions via `UserDefaults` (key: `exportCacheToDevice`) |
| 20.3.5 | | [x] | Files that already exist locally are never re-downloaded from the server regardless of toggle state |

### 20.4 Export File Source Resolution

The export service shall build a unified export manifest that resolves each file's source before beginning the copy/download phase.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.4.1 | | [x] | `USBExportService` accepts a list of tracks (with playlist key and filename) plus the `APIClient` reference for server access |
| 20.4.2 | | [x] | Before export begins, the service builds an export manifest mapping each file to its source: `.local(URL)` or `.server(playlist, filename)` |
| 20.4.3 | | [x] | The manifest is built by checking `FileDownloadManager.localFiles(playlist:)` for each playlist; files not found locally are marked as `.server` |
| 20.4.4 | | [x] | The grouped export method (`exportFiles(groups:to:)`) continues to create playlist subdirectories on the USB destination (existing behavior) |

### 20.5 UI Changes

Views that trigger USB export shall be updated to support exporting without requiring prior downloads.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.5.1 | | [x] | `LibraryView` "Export to USB" button is enabled when any server playlists have files (not just playlists with local downloads) |
| 20.5.2 | | [x] | `LibraryView` per-playlist swipe "Export" action is available for all playlists with server files, not just those with local copies |
| 20.5.3 | | [x] | `PipelineView` "Export to USB" post-process button works immediately after pipeline completion without requiring a separate download step |
| 20.5.4 | | [x] | The "Also save to device" toggle appears in `LibraryView` export section and `PipelineView` post-process section |
| 20.5.5 | | [x] | Export UI sections show file source breakdown: "X local, Y from server" before export begins |

### 20.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 20.6.1 | | [x] | Server unreachable during export: server-sourced files fail individually; locally-sourced files continue to export; completion message reports network failures separately |
| 20.6.2 | | [x] | Mixed playlist (some local, some server): both sources used within the same playlist export — no all-or-nothing behavior |
| 20.6.3 | | [x] | Large files: server downloads use streaming (chunked writes) to avoid excessive memory usage |
| 20.6.4 | | [x] | Export cancellation: if the user backgrounds the app or cancels, any in-progress server download is cancelled via `Task.checkCancellation()` |
| 20.6.5 | | [x] | Concurrent local cache write: when "Also save to device" is ON, the local cache write does not block or delay the USB write — USB copy takes priority |
| 20.6.6 | | [x] | Security-scoped URL access: server-fetched files use the same security-scoped URL lifecycle as local copies (start/stop accessing) |
| 20.6.7 | | [x] | Empty server response: if server returns 404 for a file (e.g., deleted between listing and export), the file is counted as failed and export continues |

---
