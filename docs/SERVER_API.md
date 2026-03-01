# Server API Reference

All endpoints are defined in `web_api.py` as a Flask Blueprint. Base URL: `http://<host>:<port>`.

## Common Patterns

### Authentication

All protected endpoints require a Bearer token:

```
Authorization: Bearer <api_key>
```

The API key is generated via `secrets.token_urlsafe(32)` and persisted in `config.yaml`.

### Background Task Model

Long-running operations (pipeline, convert, sync, cookie refresh) use a one-at-a-time task model:

1. `POST` endpoint returns `{"task_id": "<uuid>"}` (HTTP 200)
2. HTTP 409 if another task is already running
3. Client streams progress via `GET /api/stream/<task_id>` (Server-Sent Events)
4. SSE event types: `log`, `progress`, `overall_progress`, `heartbeat` (30s), `done`

### ETag Caching

Supported on `GET /api/playlists` and `GET /api/files/<key>`:

- Response includes `ETag` header
- Client sends `If-None-Match: <etag>` on subsequent requests
- Server returns 304 Not Modified if unchanged

### Pagination

Used by task history and audit endpoints:

- Query params: `limit` (default 50), `offset` (default 0)
- Optional filters: `operation`, `status`, `from`, `to` (ISO dates)
- Response: `{"entries": [...], "total": N, "limit": N, "offset": N}`

### Error Responses

Standard JSON format with appropriate HTTP status:

```json
{"error": "descriptive message"}
```

Common status codes: 400 (validation), 404 (not found), 409 (busy/conflict), 413 (too large), 503 (unavailable).

---

## Endpoints

### Auth and Server Info

#### POST /api/auth/validate

Validate API key and get server identity.

**Response:** `{"valid": true, "version": "2.37.0", "server_name": "My Server", "api_version": 1}`

#### GET /api/server-info

Server metadata for client discovery.

**Response:** `{"name", "version", "platform", "profiles": [], "api_version", "external_url?"}`

---

### Status and Dashboard

#### GET /api/status

Dashboard status snapshot.

**Response:**

```json
{
  "version": "2.37.0",
  "cookies": {"valid": true, "exists": true, "reason": "...", "days_remaining": 30},
  "library": {"playlists": 5, "files": 120, "size_mb": 450.5},
  "busy": false,
  "scheduler": {"enabled": true, "next_run": "..."}
}
```

#### GET /api/summary

Detailed library summary from TrackDB.

**Response:** `{"total_playlists", "total_files", "total_size_bytes", "scan_duration", "freshness", "tag_integrity", "cover_art", "playlists": [...]}`

#### GET /api/library-stats

Music source directory (M4A) statistics.

**Response:** `{"total_playlists", "total_files", "total_size_bytes", "total_exported", "total_unconverted", "scan_duration", "playlists": [...]}`

#### GET /api/library-stats/\<key\>/unconverted

List M4A files with no TrackDB record.

**Response:** `{"files": [{"artist", "title", "display_name"}]}`

**Status:** 400 if key invalid, 404 if no source directory

---

### Cookie Management

#### GET /api/cookies/browsers

List installed browsers available for cookie extraction.

**Response:** `{"default": "chrome", "installed": ["chrome", "firefox", "safari"]}`

#### POST /api/cookies/refresh

Background task: refresh cookies via Selenium browser automation.

**Body:** `{"browser": "auto"|"chrome"|"firefox"|..., "verbose?": false}`

**Response:** `{"task_id": "..."}`

**Status:** 409 if busy

#### POST /api/cookies/upload

Accept Netscape-format cookies from a remote client.

**Body:** `{"cookies": "# Netscape HTTP Cookie File\n..."}`

**Response:** `{"valid": true, "reason": "...", "days_remaining": 30}`

**Status:** 400 if invalid format

---

### Playlists CRUD

#### GET /api/playlists

List all playlists with aggregate stats. Supports ETag caching.

**Response:**

```json
[
  {"key": "my_playlist", "url": "https://...", "name": "My Playlist",
   "file_count": 15, "size_bytes": 52428800, "duration_s": 3600}
]
```

**Headers:** `ETag`, accepts `If-None-Match` (returns 304)

#### POST /api/playlists

Add a new playlist.

**Body:** `{"key": "my_playlist", "url": "https://music.apple.com/...", "name": "My Playlist"}`

**Response:** `{"ok": true}`

**Status:** 400 if missing fields, 409 if duplicate key

#### PUT /api/playlists/\<key\>

Update playlist name and/or URL.

**Body:** `{"url?": "...", "name?": "..."}`

**Response:** `{"ok": true}`

**Status:** 404 if key not found

#### DELETE /api/playlists/\<key\>

Remove playlist from config (does not delete files).

**Response:** `{"ok": true}`

**Status:** 404 if key not found

#### POST /api/playlists/\<key\>/delete-data

Delete source M4A and/or library MP3 data for a playlist.

**Body:** `{"delete_source?": true, "delete_library?": true, "remove_config?": false, "dry_run?": false}`

**Response:** `{"success": true, "files_deleted": 15, "bytes_freed": 52428800, ...}`

---

### Settings and Configuration

#### GET /api/settings

Get all settings, output profiles, and quality presets.

**Response:**

```json
{
  "settings": {"output_type": "ride-command", "workers": 4, ...},
  "profiles": {"ride-command": {"description": "...", "id3_title": "{title}", ...}},
  "quality_presets": ["lossless", "high", "medium", "low"]
}
```

#### POST /api/settings

Update settings values.

**Body:** `{"output_type": "basic", "workers": 2}`

**Response:** `{"ok": true}`

#### GET /api/config/verify

Validate config.yaml structure and values.

**Response:** `{"results": [{"level": "error"|"warning"|"info", "message": "..."}], "errors": 0, "warnings": 1, "valid": true}`

#### POST /api/config/reset

Backup current config and reset to defaults.

**Response:** `{"ok": true, "backup": "config.yaml.backup"}`

---

### Scheduler

#### GET /api/scheduler/status

Get scheduler configuration and next run time.

**Response:** `{"enabled", "interval_hours", "playlists", "preset", "retry_minutes", "max_retries", "run_at", "on_missed", "next_run_time", ...}`

#### POST /api/scheduler/config

Update scheduler configuration.

**Body:** `{"enabled?", "interval_hours?", "playlists?", "preset?", "retry_minutes?", "max_retries?", "run_at?", "on_missed?"}`

**Response:** `{"ok": true, "status": {...}}`

#### POST /api/scheduler/run-now

Trigger an immediate scheduled pipeline run.

**Response:** `{"ok": true, "status": {...}}`

**Status:** 409 if busy

---

### Directories

#### GET /api/directories/music

List playlist keys that have source M4A files on disk.

**Response:** `["playlist_key_1", "playlist_key_2"]`

#### GET /api/directories/export

List library playlists with MP3 file counts.

**Response:** `[{"name": "playlist_key", "display_name": "Playlist Name", "files": 15}]`

---

### Pipeline

#### POST /api/pipeline/run

Background task: full pipeline (download + convert + optional sync).

**Body:**

```json
{
  "playlist?": "single_key",
  "url?": "https://music.apple.com/...",
  "auto?": false,
  "dry_run?": false,
  "verbose?": false,
  "preset?": "lossless",
  "sync_destination?": "My USB",
  "eq?": {"loudnorm": true},
  "no_eq?": false
}
```

**Response:** `{"task_id": "..."}`

**Status:** 400 if invalid params, 409 if busy

---

### Conversion

#### POST /api/convert/run

Background task: convert M4A files to MP3 for a single directory.

**Body:** `{"input_dir", "output_dir?", "force?", "dry_run?", "verbose?", "preset?", "eq?", "no_eq?"}`

**Response:** `{"task_id": "..."}`

#### POST /api/convert/batch

Background task: convert multiple playlists.

**Body:** `{"playlists": ["key1", "key2"], "force?", "dry_run?", "verbose?", "preset?", "eq?", "no_eq?"}`

**Response:** `{"task_id": "..."}`

---

### Library Maintenance

#### POST /api/library/backfill-metadata

Background task: re-read M4A source tags into TrackDB for existing tracks.

**Response:** `{"task_id": "..."}`

#### POST /api/library/audit

Background task: verify DB and filesystem integrity.

**Body:** `{"allow_updates?": false}`

**Response:** `{"task_id": "..."}`

---

### File Serving

#### GET /api/files/\<key\>

List MP3 files with metadata for a playlist. Supports ETag caching.

**Query params:** `profile?`, `include_sync?` (boolean)

**Response:**

```json
{
  "playlist": "key",
  "name": "Playlist Name",
  "file_count": 15,
  "files": [
    {
      "filename": "abc123.mp3",
      "display_filename": "Artist - Title.mp3",
      "output_subdir": "Playlist Name/",
      "size": 5242880,
      "duration": 240.5,
      "title": "Title",
      "artist": "Artist",
      "album": "Album",
      "uuid": "abc123",
      "has_cover_art": true,
      "synced_to": ["usbkey-MyDrive"],
      "created_at": 1700000000,
      "updated_at": 1700000000
    }
  ]
}
```

#### GET /api/files/\<key\>/\<filename\>

Download a single MP3 file. Optionally applies profile-specific tags.

**Query params:** `profile?`

**Headers:** `Content-Disposition: attachment; filename="Artist - Title.mp3"`

**Response:** Binary MP3 data

#### GET /api/files/\<key\>/\<filename\>/artwork

Serve cover art for a track.

**Query params:** `size?` (resize to N pixels)

**Response:** Binary JPEG/PNG

**Status:** 404 if no artwork

#### GET /api/files/\<key\>/sync-status

Per-file sync status map for a playlist.

**Response:** `{"filename1.mp3": ["usbkey-Drive1"], "filename2.mp3": []}`

#### GET /api/files/\<key\>/download-all

Stream a ZIP archive of all MP3s in a playlist.

**Response:** Binary ZIP with Content-Length header

#### POST /api/files/download-zip

Stream a ZIP archive from multiple playlists.

**Body:** `{"playlists": ["key1", "key2"]}`

**Response:** Binary ZIP

---

### Sync Destinations

#### GET /api/sync/destinations

List saved destinations and auto-detected USB drives.

**Response:** `{"destinations": [{"name", "path", "sync_key?", "is_web_client?"}]}`

#### POST /api/sync/destinations

Add a saved destination.

**Body:** `{"name", "path", "sync_key?"}`

**Response:** `{"ok": true, "name", "path", "sync_key?"}`

#### DELETE /api/sync/destinations/\<name\>

Remove a saved destination.

**Response:** `{"ok": true}`

#### PUT /api/sync/destinations/\<name\>/link

Link or unlink a sync\_key to a destination.

**Body:** `{"sync_key?": "usbkey-Drive1"}`

**Response:** `{"ok": true, "sync_key", "merge_stats?"}`

#### POST /api/sync/destinations/\<name\>/rename

Rename a saved destination.

**Body:** `{"new_name": "New Name"}`

**Response:** `{"ok": true, "old_name", "new_name", "tracking_renamed"}`

---

### Sync Operations

#### POST /api/sync/run

Background task: sync MP3s to a destination with profile-specific tags.

**Body:** `{"source_dir?", "playlist_key?", "destination", "profile?", "dry_run?", "verbose?"}`

**Response:** `{"task_id": "..."}`

#### GET /api/sync/status

Summary of all sync keys.

**Response:** `[{"key_name", "last_sync_at", "total_files", "synced_files", "new_files", "new_playlists"}]`

#### GET /api/sync/status/\<key\>

Per-playlist breakdown for a sync key.

**Response:**

```json
{
  "sync_key": "usbkey-Drive1",
  "last_sync_at": 1700000000,
  "playlists": [{"name", "total_files", "synced_files", "new_files", "is_new_playlist"}],
  "total_files": 120,
  "synced_files": 115,
  "new_files": 5,
  "new_playlists": 0
}
```

---

### Sync Keys

#### GET /api/sync/keys

List all tracked sync keys.

**Response:** `[{"key_name", "last_sync_at", "created_at"}]`

#### DELETE /api/sync/keys/\<key\>

Delete a sync key and all its tracking data.

**Response:** `{"ok": true}`

#### DELETE /api/sync/keys/\<key\>/playlists/\<playlist\>

Delete tracking for one playlist on a sync key.

**Response:** `{"ok": true, "deleted": 15}`

#### POST /api/sync/keys/\<key\>/prune

Prune stale tracking records for files no longer in the library.

**Response:** `{"pruned_count": 3, ...}`

#### POST /api/sync/keys/\<key\>/rename

Rename a sync key.

**Body:** `{"new_key": "new-key-name"}`

**Response:** `{"ok": true, "old_key", "new_key", "stats", "destinations_updated"}`

#### POST /api/sync/client-record

Record client-side synced files for tracking.

**Body:** `{"sync_key": "client-folder", "playlist": "key", "files": ["file1.mp3", "file2.mp3"], "folder_name?"}`

**Response:** `{"ok": true, "recorded": 2}`

---

### Tasks and Operations

#### GET /api/tasks

List active background tasks.

**Response:** `[{"id", "operation", "description", "status", "started_at", "progress"}]`

#### GET /api/tasks/\<id\>

Get single task details.

**Response:** `{"id", "operation", "status", "started_at", "finished_at", "result", "error", "elapsed"}`

#### POST /api/tasks/\<id\>/cancel

Cancel a running task.

**Response:** `{"ok": true}`

#### GET /api/tasks/history

Paginated task history.

**Query params:** `limit`, `offset`, `operation?`, `status?`, `from?`, `to?`

**Response:** `{"entries": [...], "total", "limit", "offset"}`

#### GET /api/tasks/stats

Task history statistics.

**Response:** `{"total", "today", "by_operation": {...}, "by_status": {...}}`

#### POST /api/tasks/clear

Delete old task history entries.

**Body:** `{"confirm": true, "before_date?"}`

**Response:** `{"deleted": 50}`

---

### SSE Stream

#### GET /api/stream/\<task\_id\>

Server-Sent Events stream for a background task.

**Event format:** `data: {"type": "...", ...}\n\n`

**Event types:**

| Type | Fields | Description |
|------|--------|-------------|
| `log` | `level`, `message` | Log line (INFO, OK, WARN, ERROR, SKIP) |
| `progress` | `current`, `total`, `label` | Item-level progress |
| `overall_progress` | `current`, `total`, `label` | Multi-playlist overall progress |
| `heartbeat` | (none) | Keep-alive every 30 seconds |
| `done` | `status`, `result?`, `error?` | Task finished (completed, failed, cancelled) |

---

### EQ Presets

#### GET /api/eq

List EQ configurations.

**Query params:** `profile?`

**Response:** `{"eq_presets": [{"profile", "playlist?", "loudnorm", "bass_boost", "treble_boost", "compressor"}]}`

#### POST /api/eq

Set EQ config for a profile or profile+playlist.

**Body:** `{"profile", "playlist?", "loudnorm?", "bass_boost?", "treble_boost?", "compressor?"}`

**Response:** `{"success": true, "eq": {...}}`

#### DELETE /api/eq

Delete an EQ config.

**Body:** `{"profile", "playlist?"}`

**Response:** `{"success": true}`

#### GET /api/eq/resolve

Resolve the effective EQ for a profile+playlist combination.

**Query params:** `profile` (required), `playlist?`

**Response:** `{"eq": {...}, "any_enabled": true, "filter_chain": "...", "effects": [...]}`

#### GET /api/eq/effects

List available EQ effects.

**Response:** `{"effects": [{"name", "description"}]}`

---

### Pairing

#### GET /api/pairing-qr

Generate QR code (SVG) for iOS companion app pairing.

**Response:** SVG image (Content-Type: image/svg+xml)

#### GET /api/pairing-info

JSON server pairing details for programmatic access.

**Response:** `{"api_key", "host", "port", "address"}`

---

### Audit Log

#### GET /api/audit

Paginated audit entries with filters.

**Query params:** `limit`, `offset`, `operation?`, `status?`, `from?`, `to?`

**Response:** `{"entries": [...], "total", "limit", "offset"}`

#### GET /api/audit/stats

Audit log statistics.

**Response:** `{"total", "today", "by_operation": {...}, "by_status": {...}}`

#### POST /api/audit/clear

Delete old audit entries.

**Body:** `{"confirm": true, "before_date?"}`

**Response:** `{"deleted": 100}`

---

### About

#### GET /api/about

Version and release notes.

**Response:** `{"version": "2.37.0", "release_notes": "Version 2.37.0 (2026-03-01):\n..."}`
