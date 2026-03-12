# Server API Reference

All endpoints are defined in `web_api.py` as a Flask Blueprint. Base URL: `http://<host>:<port>`.

---

## Common Patterns

### Authentication

All protected endpoints require a Bearer token:

```
Authorization: Bearer <api_key>
```

The API key is generated via `secrets.token_urlsafe(32)` and persisted in `config.yaml`. The `GET /api/server-info` endpoint is the only unauthenticated endpoint.

### Background Task Model

Long-running operations (pipeline, convert, sync, cookie refresh, backfill, audit) use a one-at-a-time task model:

1. `POST` endpoint returns `{"task_id": "<uuid>"}` (HTTP 200)
2. HTTP 409 if another task is already running: `{"error": "Another operation is already running"}`
3. Client streams progress via `GET /api/stream/<task_id>` (Server-Sent Events)
4. SSE event types: `log`, `progress`, `overall_progress`, `heartbeat` (30s keepalive), `done`

### ETag Caching

Supported on `GET /api/playlists` and `GET /api/files/<key>`:

- Response includes `ETag` header (MD5-based fingerprint)
- Client sends `If-None-Match: <etag>` on subsequent requests
- Server returns HTTP 304 Not Modified if unchanged

### Pagination

Used by task history and audit endpoints:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | `50` | Maximum entries per page |
| `offset` | integer | `0` | Number of entries to skip |
| `operation` | string | — | Filter by operation type |
| `status` | string | — | Filter by status |
| `from` | string | — | Start date filter (ISO format) |
| `to` | string | — | End date filter (ISO format) |

Response shape: `{"entries": [...], "total": N, "limit": N, "offset": N}`

### Error Responses

All errors return JSON with an `error` field and appropriate HTTP status:

```json
{"error": "descriptive message"}
```

| Status | Meaning |
|--------|---------|
| 400 | Validation error or missing required fields |
| 404 | Resource not found |
| 409 | Conflict — server busy or duplicate resource |
| 413 | Payload too large (e.g., ZIP file limit exceeded) |
| 503 | Service unavailable (e.g., missing dependency) |

---

## Auth and Server Info

### POST /api/auth/validate

Validate an API key and return server identity.

**Request:** No body required. Authentication is validated from the `Authorization` header.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `valid` | boolean | Always `true` if the request reaches this endpoint (auth middleware rejects invalid keys) |
| `version` | string | Server version (e.g., `"2.37.0"`) |
| `server_name` | string | Human-readable server name from config |
| `api_version` | integer | API version number (currently `2`) |

```json
{
  "valid": true,
  "version": "2.37.0",
  "server_name": "My Server",
  "api_version": 2
}
```

---

### GET /api/server-info

Server metadata for client discovery. **No authentication required.**

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Server name from config |
| `version` | string | Server version |
| `platform` | string | OS display name (e.g., `"macOS"`, `"Linux"`, `"Windows"`) |
| `profiles` | string[] | Available output profile names |
| `api_version` | integer | API version number (currently `2`) |
| `external_url` | string? | External URL if configured (omitted if not set) |

```json
{
  "name": "My Server",
  "version": "2.37.0",
  "platform": "macOS",
  "profiles": ["ride-command", "basic"],
  "api_version": 2,
  "external_url": "https://music.example.com:5555"
}
```

---

## Status and Dashboard

### GET /api/status

Dashboard status snapshot with cookie health, library size, and scheduler state.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Server version |
| `cookies` | object | Cookie health status |
| `cookies.valid` | boolean | Whether cookies are valid for Apple Music |
| `cookies.exists` | boolean | Whether cookies file exists on disk |
| `cookies.reason` | string | Human-readable status explanation |
| `cookies.days_remaining` | integer? | Days until cookie expiration, or `null` |
| `library` | object | Library size summary |
| `library.playlists` | integer | Number of playlists in library |
| `library.files` | integer | Total MP3 files in library |
| `library.size_mb` | number | Total library size in megabytes |
| `busy` | boolean | Whether a background task is currently running |
| `scheduler` | object? | Scheduler status, or `null` if scheduler unavailable |

```json
{
  "version": "2.37.0",
  "cookies": {
    "valid": true,
    "exists": true,
    "reason": "Valid (30 days remaining)",
    "days_remaining": 30
  },
  "library": {
    "playlists": 5,
    "files": 120,
    "size_mb": 450.5
  },
  "busy": false,
  "scheduler": {
    "enabled": true,
    "next_run": "2026-03-02T03:00:00"
  }
}
```

---

### GET /api/summary

Detailed library summary from TrackDB with per-playlist breakdowns.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `total_playlists` | integer | Number of playlists |
| `total_files` | integer | Total tracks across all playlists |
| `total_size_bytes` | integer | Total library size in bytes |
| `scan_duration` | number | Time to generate summary (seconds) |
| `freshness` | object | Counts by download freshness level |
| `freshness.current` | integer | Playlists downloaded today |
| `freshness.recent` | integer | Playlists downloaded within 7 days |
| `freshness.stale` | integer | Playlists downloaded within 30 days |
| `freshness.outdated` | integer | Playlists not downloaded in 30+ days |
| `tag_integrity` | object | Tag protection stats |
| `tag_integrity.protected` | integer | Tracks with UUID tag |
| `tag_integrity.checked` | integer | Total tracks checked |
| `tag_integrity.missing` | integer | Tracks missing UUID tag |
| `cover_art` | object | Cover art stats |
| `cover_art.with_art` | integer | Tracks with cover art |
| `cover_art.without_art` | integer | Tracks without cover art |
| `cover_art.original` | integer | Original-size cover art count |
| `cover_art.resized` | integer | Resized cover art count |
| `playlists` | object[] | Per-playlist details |

**Playlist object fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Playlist key |
| `file_count` | integer | Number of tracks |
| `size_bytes` | integer | Total size in bytes |
| `avg_size_mb` | number | Average file size in MB |
| `last_modified` | string? | ISO timestamp of most recent track content change, or `null` |
| `last_downloaded` | string? | ISO timestamp of last download attempt, or `null` |
| `download_freshness` | string | One of: `"current"`, `"recent"`, `"stale"`, `"outdated"` — based on `last_downloaded` |
| `tags_checked` | integer | Tracks checked for tag integrity |
| `tags_protected` | integer | Tracks with valid UUID tag |
| `cover_with` | integer | Tracks with cover art |
| `cover_without` | integer | Tracks without cover art |

---

### GET /api/library-stats

Music source directory (M4A) statistics scanned from disk.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `total_playlists` | integer | Number of source directories |
| `total_files` | integer | Total M4A files found |
| `total_size_bytes` | integer | Total size of source files |
| `total_exported` | integer | Files already converted to MP3 |
| `total_unconverted` | integer | Files not yet converted |
| `scan_duration` | number | Scan time in seconds |
| `playlists` | object[] | Per-playlist source stats |

---

### GET /api/library-stats/\<key\>/unconverted

List M4A source files that have no matching TrackDB record (not yet converted).

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `files` | object[] | List of unconverted files |
| `files[].artist` | string | Artist name (from directory structure) |
| `files[].title` | string | Track title (from filename stem) |
| `files[].display_name` | string | Formatted as `"Artist - Title"` |

**Status codes:** 400 if key contains invalid characters

---

## Cookie Management

### GET /api/cookies/browsers

List installed browsers available for cookie extraction.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `default` | string | Default browser name (e.g., `"chrome"`) |
| `installed` | string[] | All installed browser names |

```json
{
  "default": "chrome",
  "installed": ["chrome", "firefox", "safari"]
}
```

---

### POST /api/cookies/refresh

Background task: refresh cookies via Selenium browser automation.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `browser` | string | No | `"auto"` | Browser to use: `"auto"`, `"chrome"`, `"firefox"`, `"safari"`, `"edge"` |
| `verbose` | boolean | No | `false` | Enable verbose logging |

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 409 if another task is running

---

### POST /api/cookies/upload

Accept Netscape-format cookies from a remote client. Backs up existing cookies before overwriting, then cleans non-Apple cookies and validates.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cookies` | string | Yes | Full Netscape-format cookie text |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `valid` | boolean | Whether uploaded cookies are valid for Apple Music |
| `reason` | string | Validation result explanation |
| `days_remaining` | integer? | Days until expiration, or `null` |

**Status codes:** 400 if cookies field is empty

---

## Playlists CRUD

### GET /api/playlists

List all playlists with aggregate stats from TrackDB. Supports ETag caching.

**Response headers:** `ETag` (accepts `If-None-Match`, returns 304 if unchanged)

**Response:** Array of playlist objects.

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | Unique playlist identifier |
| `url` | string | Playlist URL (Apple Music or YouTube Music) |
| `name` | string | Human-readable playlist name |
| `source_type` | string | `"apple_music"` or `"youtube_music"` |
| `file_count` | integer | Number of converted MP3 tracks |
| `size_bytes` | integer | Total size of MP3 files in bytes |
| `duration_s` | number | Total duration in seconds |
| `freshness` | string | Download freshness: `"current"`, `"recent"`, `"stale"`, `"outdated"` |

```json
[
  {
    "key": "my_playlist",
    "url": "https://music.apple.com/us/playlist/my-playlist/pl.abc123",
    "name": "My Playlist",
    "source_type": "apple_music",
    "file_count": 15,
    "size_bytes": 52428800,
    "duration_s": 3600,
    "freshness": "current"
  }
]
```

---

### POST /api/playlists

Add a new playlist. The `source_type` is auto-detected from the URL.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Unique playlist key (used as directory name) |
| `url` | string | Yes | Apple Music (`music.apple.com`) or YouTube Music (`music.youtube.com`) URL |
| `name` | string | Yes | Human-readable display name |

**Response:** `{"ok": true}`

**Status codes:** 400 if missing fields or unrecognised URL, 409 if key already exists

---

### PUT /api/playlists/\<key\>

Update a playlist's name and/or URL.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key to update |

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | No | New Apple Music URL |
| `name` | string | No | New display name |

**Response:** `{"ok": true}`

**Status codes:** 404 if key not found

---

### DELETE /api/playlists/\<key\>

Remove a playlist from the config. Does not delete source or library files.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key to remove |

**Response:** `{"ok": true}`

**Status codes:** 404 if key not found

---

### POST /api/playlists/\<key\>/delete-data

Delete source M4A and/or library MP3 data for a playlist. Optionally removes the playlist from config.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `delete_source` | boolean | No | `true` | Delete source M4A files |
| `delete_library` | boolean | No | `true` | Delete converted MP3 files and TrackDB records |
| `remove_config` | boolean | No | `false` | Also remove playlist from config |
| `dry_run` | boolean | No | `false` | Preview deletion without actually deleting |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the operation completed |
| `files_deleted` | integer | Number of files deleted |
| `bytes_freed` | integer | Total bytes freed |
| `source_deleted` | boolean | Whether source directory was deleted |
| `library_deleted` | boolean | Whether library data was deleted |

**Status codes:** 404 if playlist not found and has no data on disk

---

## Settings and Configuration

### GET /api/settings

Get all settings, output profile definitions, and available quality presets.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `settings` | object | Current settings from config.yaml |
| `settings.output_type` | string | Active output profile name |
| `settings.workers` | integer | Number of concurrent workers |
| `settings.server_name` | string | Server display name |
| `settings.quality_preset` | string | Default quality preset |
| `profiles` | object | Map of profile name to profile definition |
| `quality_presets` | string[] | Available preset names: `["lossless", "high", "medium", "low"]` |

**Profile definition fields:**

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Human-readable profile description |
| `id3_title` | string | Title tag template (e.g., `"{title}"`) |
| `id3_artist` | string | Artist tag template |
| `id3_album` | string | Album tag template |
| `id3_genre` | string | Genre tag template |
| `id3_extra` | object | Additional ID3 tag mappings |
| `filename` | string | Output filename template |
| `directory` | string | Output directory template |
| `id3_versions` | string[] | ID3 tag versions (e.g., `["2.3"]`) |
| `artwork_size` | integer | Cover art size in pixels (0 = original, -1 = strip) |
| `usb_dir` | string | USB sync subdirectory |

---

### POST /api/settings

Update one or more settings values.

**Request body:** Key-value pairs to update.

```json
{"output_type": "basic", "workers": 2}
```

**Response:** `{"ok": true}`

---

### GET /api/config/verify

Validate config.yaml structure and values. Returns a structured report.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `results` | object[] | Validation results |
| `results[].level` | string | Severity: `"error"`, `"warning"`, or `"info"` |
| `results[].message` | string | Description of the issue |
| `errors` | integer | Total error count |
| `warnings` | integer | Total warning count |
| `valid` | boolean | `true` if no errors found |

---

### POST /api/config/reset

Back up current config.yaml and recreate with default values.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `backup` | string? | Path to backup file, or `null` if no existing config |

---

## Scheduler

### GET /api/scheduler/status

Get current scheduler configuration and next run time.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether scheduler is active |
| `interval_hours` | number | Hours between pipeline runs |
| `playlists` | string[] | Playlist keys to process (empty = all) |
| `preset` | string? | Quality preset override, or `null` for default |
| `retry_minutes` | integer | Minutes between retry attempts |
| `max_retries` | integer | Maximum retry attempts |
| `run_at` | string? | Fixed daily run time (HH:MM), or `null` for interval mode |
| `on_missed` | string | Missed run behavior: `"run"` or `"skip"` |
| `next_run_time` | string? | ISO timestamp of next scheduled run |
| `last_run_time` | string? | ISO timestamp of last run |
| `last_run_status` | string? | Status of last run |

**Status codes:** 404 if scheduler unavailable

---

### POST /api/scheduler/config

Update scheduler configuration. All fields are optional — only provided fields are updated.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean | No | Enable or disable scheduler |
| `interval_hours` | number | No | Hours between runs (minimum `0.5`) |
| `playlists` | string[] | No | Playlist keys to process |
| `preset` | string | No | Quality preset name |
| `retry_minutes` | integer | No | Minutes between retries |
| `max_retries` | integer | No | Maximum retry count |
| `run_at` | string | No | Fixed daily time (HH:MM format, `""` to clear) |
| `on_missed` | string | No | `"run"` or `"skip"` |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `status` | object | Updated scheduler status (same shape as GET) |

**Status codes:** 400 if validation fails, 404 if scheduler unavailable

---

### POST /api/scheduler/run-now

Trigger an immediate scheduled pipeline execution.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `status` | object | Current scheduler status |

**Status codes:** 400 if scheduler disabled, 404 if scheduler unavailable, 409 if busy

---

## Directories

### GET /api/directories/music

List playlist keys that have source M4A files on disk.

**Response:** Array of strings (playlist keys).

```json
["playlist_key_1", "playlist_key_2"]
```

---

### GET /api/directories/export

List library playlists with converted MP3 file counts from TrackDB.

**Response:** Array of directory objects.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Playlist key |
| `display_name` | string | Human-readable playlist name from config |
| `files` | integer | Number of converted MP3 files |

```json
[
  {"name": "my_playlist", "display_name": "My Playlist", "files": 15}
]
```

---

## Pipeline

### POST /api/pipeline/run

Background task: full pipeline (download + convert + optional sync) for one or all playlists.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `playlist` | string | No* | — | Single playlist key to process |
| `url` | string | No* | — | Apple Music URL (creates playlist if new) |
| `auto` | boolean | No* | `false` | Process all configured playlists |
| `dry_run` | boolean | No | `false` | Preview without making changes |
| `verbose` | boolean | No | `false` | Enable verbose logging |
| `preset` | string | No | config default | Quality preset: `"lossless"`, `"high"`, `"medium"`, `"low"` |
| `sync_destination` | string | No | — | Destination name to sync after pipeline |
| `eq` | object | No | — | EQ config override: `{loudnorm, bass_boost, treble_boost, compressor}` |
| `no_eq` | boolean | No | `false` | Disable all EQ processing |
| `cleanup_removed_tracks` | boolean | No | server setting | When `true`, cascade-delete tracks removed from the Apple Music playlist (source M4A, library MP3, artwork, TrackDB record, sync records). Overrides the `cleanup_removed_tracks` server setting. |

*At least one of `playlist`, `url`, or `auto` is required.

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 400 if no target specified, 409 if busy

---

## Conversion

### POST /api/convert/run

Background task: convert M4A files to MP3 for a single directory.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `input_dir` | string | Yes | — | Source directory path (relative to project root) |
| `output_dir` | string | No | `library/audio/` | Output directory for MP3 files |
| `force` | boolean | No | `false` | Re-convert already converted files |
| `dry_run` | boolean | No | `false` | Preview without converting |
| `verbose` | boolean | No | `false` | Enable verbose logging |
| `preset` | string | No | `"lossless"` | Quality preset |
| `eq` | object | No | — | EQ config override |
| `no_eq` | boolean | No | `false` | Disable all EQ processing |

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 400 if `input_dir` missing or invalid, 409 if busy

---

### POST /api/convert/batch

Background task: convert multiple playlists in a single operation.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `playlists` | string[] | Yes | — | List of playlist keys to convert |
| `force` | boolean | No | `false` | Re-convert already converted files |
| `dry_run` | boolean | No | `false` | Preview without converting |
| `verbose` | boolean | No | `false` | Enable verbose logging |
| `preset` | string | No | `"lossless"` | Quality preset |
| `eq` | object | No | — | EQ config override |
| `no_eq` | boolean | No | `false` | Disable all EQ processing |

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 400 if playlists empty, 404 if playlist source directory not found, 409 if busy

---

## Library Maintenance

### POST /api/library/backfill-metadata

Background task: re-read M4A source tags into TrackDB for existing tracks. Populates extended metadata columns (genre, track number, composer, etc.) that may have been missed during initial conversion.

**Request:** No body required.

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 409 if busy

---

### POST /api/library/audit

Background task: verify DB records match filesystem and clean up orphans.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `allow_updates` | boolean | No | `false` | Allow the audit to fix issues (delete orphans, update records) |

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 409 if busy

---

## Track Search

### GET /api/tracks/search

Search all tracks across all playlists by title, artist, or album. Case-insensitive.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `q` | string | Search term. SQL LIKE metacharacters (`%`, `_`, `\`) are automatically escaped. |

**Response:** JSON array of track objects. Each object contains all `tracks` table columns plus:

| Field | Type | Description |
|---|---|---|
| `playlist_name` | string | Human-readable playlist name (resolved from playlists table) |

Empty `q` returns `[]` HTTP 200. No matches returns `[]` HTTP 200.

**Status codes:** 200 OK

---

## File Serving

### GET /api/files/\<key\>

List MP3 files in a playlist with metadata from TrackDB. Supports ETag caching.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profile` | string | — | Output profile name for display filename/subdir resolution |
| `include_sync` | boolean | `false` | Include per-file sync status (`synced_to` array) |

**Response headers:** `ETag` (accepts `If-None-Match`, returns 304 if unchanged)

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `playlist` | string | Playlist key |
| `name` | string | Playlist display name (only present when `profile` is set) |
| `file_count` | integer | Number of files returned |
| `files` | object[] | File metadata entries |

**File object fields:**

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | UUID-based filename on disk (e.g., `"abc123.mp3"`) |
| `display_filename` | string | Human-readable name (e.g., `"Artist - Title.mp3"`) |
| `output_subdir` | string? | Output subdirectory (only when `profile` is set) |
| `size` | integer | File size in bytes |
| `duration` | number | Duration in seconds |
| `title` | string | Track title |
| `artist` | string | Track artist |
| `album` | string | Album name |
| `uuid` | string | Unique track identifier |
| `has_cover_art` | boolean | Whether cover art exists |
| `synced_to` | string[]? | Sync keys this file has been synced to (only when `include_sync=true`) |
| `created_at` | number | Unix timestamp when track was added |
| `updated_at` | number | Unix timestamp of last metadata update |

**Status codes:** 404 if no tracks found for playlist

---

### GET /api/files/\<key\>/\<filename\>

Download a single MP3 file. Without `?profile`, serves the clean library MP3 (UUID-only tags). With `?profile`, streams a copy with profile-specific ID3 tags applied on-the-fly.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |
| `filename` | string | UUID-based filename (e.g., `"abc123.mp3"`) |

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profile` | string | — | Output profile name for on-the-fly tagging |

**Response:** Binary MP3 data with headers:

- `Content-Type: audio/mpeg`
- `Content-Disposition: attachment; filename="Artist - Title.mp3"`
- `Content-Length: <bytes>` (when profile tagging is used)

**Status codes:** 400 if invalid path, 404 if file or track not found

---

### GET /api/files/\<key\>/\<filename\>/artwork

Serve cover art for a track. Optionally resize to a target dimension.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |
| `filename` | string | UUID-based filename (e.g., `"abc123.mp3"`) |

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `size` | integer | — | Resize to N x N pixels (omit for original size) |

**Response:** Binary JPEG or PNG image.

**Status codes:** 404 if no cover art found or file missing

---

### GET /api/files/\<key\>/sync-status

Per-file sync status map for a playlist. Lightweight endpoint with no ID3 reads.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |

**Response:** Object mapping filenames to arrays of destination names they have been synced to.

```json
{
  "abc123.mp3": ["My-USB", "Downloads"],
  "def456.mp3": []
}
```

---

### GET /api/files/\<key\>/download-all

Stream a ZIP archive of all MP3s in a playlist. Files are stored uncompressed (ZIP_STORED) for streaming efficiency. Archive entries use human-readable display filenames.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Playlist key |

**Response:** Binary ZIP archive with headers:

- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="<key>.zip"`
- `Content-Length: <bytes>`

**Status codes:** 404 if no MP3 files found

---

### POST /api/files/download-zip

Stream a ZIP archive of MP3s from multiple playlists. Files are organized into subdirectories by playlist key. Maximum 2000 files.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `playlists` | string[] | Yes | Playlist keys to include |

**Response:** Binary ZIP archive with headers:

- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="music-porter-export.zip"`
- `Content-Length: <bytes>`

**Status codes:** 400 if playlists empty, 404 if no files found, 413 if total files exceed 2000

---

## Sync Destinations

### GET /api/sync/destinations

List all sync destinations (saved from DB + auto-detected USB drives in web mode).

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `destinations` | object[] | Destination list |
| `destinations[].name` | string | Destination name |
| `destinations[].path` | string | Destination path with scheme (e.g., `"usb:///Volumes/Drive/Music"`, `"folder:///path"`) |
| `destinations[].type` | string | Destination type: `"usb"`, `"folder"`, or `"web-client"` |
| `destinations[].available` | boolean | Whether the destination path is currently accessible |
| `destinations[].linked_destinations` | string[] | Names of other destinations sharing the same sync tracking group |
| `destinations[].playlist_prefs` | string[] \| null | Saved playlist selection for this group. `null` = sync all playlists; array = sync only listed playlist keys |
| `destinations[].description` | string | Optional free-text note for this destination (empty string if not set) |
| `destinations[].volume_id` | string | Filesystem UUID of the drive (empty string if not set or not a USB destination) |

---

### POST /api/sync/destinations

Add a saved sync destination.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Destination display name |
| `path` | string | Yes | Destination path with scheme |
| `description` | string | No | Optional free-text note (max 200 characters) |
| `volume_id` | string | No | Filesystem UUID of the drive for persistent identification |
| `link_to` | string | No | Name of an existing destination to share tracking with (instead of independent tracking) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `name` | string | Destination name |
| `path` | string | Destination path |
| `type` | string | Destination type: `"usb"`, `"folder"`, or `"web-client"` |
| `available` | boolean | Whether the destination path is currently accessible |
| `linked_destinations` | string[] | Names of other destinations sharing the same sync tracking group |

**Status codes:** 400 if name or path missing, or if add fails. 404 if `link_to` target not found

---

### DELETE /api/sync/destinations/\<name\>

Remove a saved sync destination.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Destination name |

**Response:** `{"ok": true}`

**Status codes:** 404 if destination not found

---

### PUT /api/sync/destinations/\<name\>/description

Set or clear the description for a saved destination.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Destination name |

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | New description text (max 200 characters). Empty string clears the description. |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `name` | string | Destination name |
| `description` | string | The saved description value |

**Status codes:** 404 if destination not found

---

### PUT /api/sync/destinations/\<name\>/link

Link or unlink a destination's sync tracking to another destination's group.

- **To link:** `{"destination": "other-dest-name"}` — joins the target's tracking group
- **To unlink:** `{"destination": null}` — creates new independent tracking

If the destination does not exist and a `path` is provided in the body, it will be auto-created (useful for sync-client first-time setup).

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Destination name |

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `destination` | string? | No | Name of the destination to link to, or `null` to unlink |
| `path` | string | No | Destination path with scheme — used to auto-create the destination if it doesn't exist |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `name` | string | Destination name |
| `path` | string | Destination path |
| `type` | string | Destination type |
| `available` | boolean | Whether the destination path is currently accessible |
| `linked_destinations` | string[] | Names of other destinations sharing the same sync tracking group |
| `created` | boolean | *(only if auto-created)* `true` if the destination was newly created |

**Status codes:** 404 if destination not found and no `path` provided, 400 if creation or update fails

---

### POST /api/sync/destinations/resolve

Resolve a sync destination on the server. Finds an existing destination by name or path, or creates one from the given path and drive name. Returns the resolved destination and current sync status.

This endpoint moves destination resolution logic from clients to the server.

**Request body (at least `path` or `name` required):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | No | Destination path with scheme (e.g., `"usb:///Volumes/Lexar/RZR/Music"`) |
| `drive_name` | string | No | Drive display name, used when creating a new destination from path |
| `link_to` | string | No | Name of an existing destination to share tracking with |
| `name` | string | No | Name of an existing saved destination to resolve |
| `volume_id` | string | No | Filesystem UUID — if provided, used to match by UUID before path (allows re-identification after drive rename) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `destination` | object | Resolved destination |
| `destination.name` | string | Destination name |
| `destination.path` | string | Destination path with scheme |
| `destination.type` | string | Destination type: `"usb"`, `"folder"`, or `"web-client"` |
| `destination.available` | boolean | Whether the destination path is currently accessible |
| `destination.linked_destinations` | string[] | Names of other destinations sharing the same sync tracking group |
| `created` | boolean | `true` if a new destination was created, `false` if an existing one was found |
| `sync_status` | object | Sync status for the resolved destination's group |
| `sync_status.destinations` | string[] | All destination names in this tracking group |
| `sync_status.total_files` | integer | Total files in library |
| `sync_status.synced_files` | integer | Files synced to this group |
| `sync_status.new_files` | integer | Files not yet synced |
| `sync_status.playlists` | object[] | Per-playlist sync details (same structure as `GET /api/sync/status/<dest_name>`) |

**Status codes:** 400 if both `path` and `name` are missing

---

## Sync Operations

### POST /api/sync/run

Background task: sync MP3s to a destination with profile-specific tags applied on-the-fly.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `destination` | string | Yes | — | Destination name from config |
| `source_dir` | string | No | `library/audio/` | Source directory for MP3 files |
| `playlist_keys` | string[] | No | — | Playlist keys to sync. `null` or omitted = sync all playlists. Saves as the destination's playlist preference. |
| `playlist_key` | string | No | — | *(Deprecated)* Single playlist key — use `playlist_keys` instead. Accepts a single string for backward compatibility. |
| `profile` | string | No | config default | Output profile for tagging |
| `dry_run` | boolean | No | `false` | Preview without syncing |
| `verbose` | boolean | No | `false` | Enable verbose logging |
| `clean_destination` | boolean | No | server setting | When `true`, remove orphaned files at the destination (tracked in SyncTracker but no longer in the library). Overrides the `clean_sync_destination` server setting. |

**Response:** `{"task_id": "..."}` — see [Background Task Model](#background-task-model)

**Status codes:** 400 if destination missing or is a web-client, 404 if destination not found, 409 if busy

---

### GET /api/sync/status

Summary of sync status per destination group. Destinations sharing the same tracking are grouped together.

**Response:** Array of destination group summaries.

| Field | Type | Description |
|-------|------|-------------|
| `destinations` | string[] | Destination names in this tracking group |
| `group_name` | string | Human-readable group label (empty string if unset) |
| `last_sync_at` | number | Unix timestamp of last sync |
| `total_files` | integer | Total files in library |
| `synced_files` | integer | Files synced to this group |
| `new_files` | integer | Files not yet synced |
| `new_playlists` | integer | Playlists with no synced files |
| `orphaned_files` | integer | Sync records in SyncTracker whose source track no longer exists in the library |

---

### GET /api/sync/status/\<dest\_name\>

Per-playlist sync breakdown for a destination's tracking group.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `dest_name` | string | Destination name |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `destinations` | string[] | All destination names in this tracking group |
| `last_sync_at` | number | Unix timestamp of last sync |
| `playlists` | object[] | Per-playlist sync details |
| `playlists[].name` | string | Playlist key |
| `playlists[].total_files` | integer | Total files in playlist |
| `playlists[].synced_files` | integer | Files synced to this group |
| `playlists[].new_files` | integer | Files not yet synced |
| `playlists[].is_new_playlist` | boolean | `true` if no files synced yet |
| `total_files` | integer | Total files across all playlists |
| `synced_files` | integer | Total synced files |
| `new_files` | integer | Total unsynced files |
| `new_playlists` | integer | Count of new (unsynced) playlists |
| `playlist_prefs` | string[] \| null | Saved playlist selection for this group. `null` = sync all; array = only listed playlist keys |
| `orphaned_files` | integer | Sync records in SyncTracker whose source track no longer exists in the library |

---

### GET /api/sync/status/\<dest\_name\>/orphaned

Return detailed orphaned file list for a destination's sync group.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `dest_name` | string | Destination name |

**Response:**

```json
{
  "orphaned_files": [
    {
      "id": 42,
      "file_path": "Artist - Title.mp3",
      "playlist": "my_playlist",
      "track_uuid": "abc-123",
      "synced_at": 1709400000.0
    }
  ]
}
```

**Status codes:** 404 if destination not found

---

### PUT /api/sync/destinations/\<name\>/playlist-prefs

Save the playlist preference for a destination's tracking group without triggering a sync. This is the canonical way for clients to persist playlist selection independently of running a sync.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Destination name |

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `playlist_keys` | string[] \| null | Yes | Playlist keys to save. `null` resets to "sync all". |

**Response:** `{"ok": true}`

**Status codes:** 404 if destination not found

---

### POST /api/sync/destinations/\<name\>/reset

Reset all sync tracking for a destination's tracking group. Deletes all sync file records and resets the last-sync timestamp. The destination itself remains.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Destination name |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `reset` | boolean | `true` on success |
| `files_cleared` | integer | Number of sync tracking records deleted |

**Status codes:** 404 if destination not found

---

### PUT /api/sync/destinations/\<name\>/group-name

Set or clear the human-readable label for a destination's tracking group. The label is shared by all destinations in the group.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Any destination name in the group |

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | New group label. Send an empty string to clear the label (UI falls back to primary destination name). |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | `true` on success |

**Status codes:** 404 if destination not found, 400 if body is missing or `name` field absent

---

### POST /api/sync/client-record

Record files synced via client-side (browser or sync-client) sync for server-side tracking. If the destination does not exist, it can be auto-created by providing `dest_path` and optionally `dest_type`.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `destination` | string | Yes | Destination name |
| `playlist` | string | Yes | Playlist key |
| `files` | string[] | Yes | List of filenames that were synced |
| `dest_path` | string | No | Filesystem path for auto-creating the destination if it doesn't exist |
| `dest_type` | string | No | Type for auto-creation: `"usb"` or `"folder"` (default: `"folder"`) |
| `link_to` | string | No | Name of an existing destination to share tracking with (only used during auto-creation) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `recorded` | integer | Number of file records saved |

**Status codes:** 400 if required fields missing or sync tracker unavailable, 404 if destination not found and no `dest_path` provided

---

## Tasks and Operations

### GET /api/tasks

List all active (in-memory) background tasks.

**Response:** Array of task objects.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Task UUID |
| `operation` | string | Operation type (e.g., `"pipeline"`, `"convert"`, `"sync"`) |
| `description` | string | Human-readable description |
| `status` | string | `"pending"`, `"running"`, `"completed"`, `"failed"`, `"cancelled"` |
| `started_at` | number | Unix timestamp when task started |
| `progress` | object? | Current progress data (if available) |

---

### GET /api/tasks/\<id\>

Get details for a single task. Checks in-memory tasks first, then falls back to task history DB.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Task UUID |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Task UUID |
| `operation` | string | Operation type |
| `description` | string | Task description |
| `status` | string | Task status |
| `started_at` | number | Unix timestamp when started |
| `finished_at` | number? | Unix timestamp when finished |
| `result` | object? | Task result data (on completion) |
| `error` | string? | Error message (on failure) |
| `elapsed` | number? | Elapsed time in seconds (for running tasks) |

**Status codes:** 404 if task not found

---

### POST /api/tasks/\<id\>/cancel

Cancel a running background task.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Task UUID |

**Response:** `{"ok": true}`

**Status codes:** 404 if task not found or not running

---

### GET /api/tasks/history

Paginated task history with optional filters. See [Pagination](#pagination) for query parameters.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `entries` | object[] | Task history entries |
| `entries[].id` | string | Task UUID |
| `entries[].operation` | string | Operation type |
| `entries[].description` | string | Task description |
| `entries[].status` | string | Final status |
| `entries[].started_at` | string | ISO timestamp |
| `entries[].finished_at` | string? | ISO timestamp |
| `entries[].result` | object? | Task result data |
| `entries[].error` | string? | Error message |
| `entries[].elapsed` | number? | Elapsed seconds (live for running tasks) |
| `total` | integer | Total matching entries |
| `limit` | integer | Page size |
| `offset` | integer | Current offset |

---

### GET /api/tasks/stats

Aggregate task history statistics.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Total task history entries |
| `today` | integer | Tasks run today |
| `by_operation` | object | Counts keyed by operation type |
| `by_status` | object | Counts keyed by status |

---

### POST /api/tasks/clear

Delete old task history entries.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `confirm` | boolean | Yes | Must be `true` to confirm deletion |
| `before_date` | string | No | Delete entries before this ISO date (omit for all) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `deleted` | integer | Number of entries deleted |

**Status codes:** 400 if `confirm` not set, 503 if task history DB unavailable

---

## SSE Stream

### GET /api/stream/\<task\_id\>

Server-Sent Events stream for a background task. The connection stays open until the task completes or is cancelled. Each event is a JSON object on a `data:` line.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_id` | string | Task UUID from a background task endpoint |

**Response headers:**

- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no`

**Event format:** `data: {"type": "...", ...}\n\n`

**Event types:**

| Type | Fields | Description |
|------|--------|-------------|
| `log` | `level`, `message` | Log message. Level: `"INFO"`, `"OK"`, `"WARN"`, `"ERROR"`, `"SKIP"` |
| `progress` | `current`, `total`, `label` | Item-level progress (e.g., current file in conversion) |
| `overall_progress` | `current`, `total`, `label` | Multi-item overall progress (e.g., playlist 2 of 5) |
| `heartbeat` | *(none)* | Keep-alive sent every 30 seconds of inactivity |
| `done` | `status`, `result?`, `error?` | Task finished. Status: `"completed"`, `"failed"`, `"cancelled"` |

**Status codes:** 404 if task not found

---

## EQ Presets

### GET /api/eq

List EQ configurations, optionally filtered by profile.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profile` | string | — | Filter by profile name (omit for all profiles) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `eq_presets` | object[] | List of EQ configurations |
| `eq_presets[].profile` | string | Profile name |
| `eq_presets[].playlist` | string? | Playlist key (null for profile default) |
| `eq_presets[].loudnorm` | boolean | Loudness normalization enabled |
| `eq_presets[].bass_boost` | boolean | Bass boost enabled |
| `eq_presets[].treble_boost` | boolean | Treble boost enabled |
| `eq_presets[].compressor` | boolean | Compressor enabled |

---

### POST /api/eq

Set EQ config for a profile default or a profile+playlist override.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `profile` | string | Yes | — | Profile name |
| `playlist` | string | No | — | Playlist key (omit for profile default) |
| `loudnorm` | boolean | No | `false` | Enable loudness normalization |
| `bass_boost` | boolean | No | `false` | Enable bass boost |
| `treble_boost` | boolean | No | `false` | Enable treble boost |
| `compressor` | boolean | No | `false` | Enable compressor |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` on success |
| `eq` | object | The saved EQ config (same fields as above) |

**Status codes:** 400 if profile missing

---

### DELETE /api/eq

Delete an EQ config for a profile default or playlist override.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `profile` | string | Yes | Profile name |
| `playlist` | string | No | Playlist key (omit to delete profile default) |

**Response:** `{"success": true}`

**Status codes:** 400 if profile missing

---

### GET /api/eq/resolve

Resolve the effective EQ config for a profile+playlist combination. If a playlist-specific override exists, it is used; otherwise the profile default is returned.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile` | string | Yes | Profile name |
| `playlist` | string | No | Playlist key |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `eq` | object | Resolved EQ config (`loudnorm`, `bass_boost`, `treble_boost`, `compressor`) |
| `any_enabled` | boolean | Whether any EQ effect is enabled |
| `filter_chain` | string | FFmpeg filter chain string |
| `effects` | string[] | List of enabled effect names |

---

### GET /api/eq/effects

List available EQ effects with descriptions.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `effects` | object[] | Available effects |
| `effects[].name` | string | Effect identifier |
| `effects[].description` | string | Human-readable description |

---

## Pairing

### GET /api/pairing-qr

Generate a QR code (SVG) for iOS companion app pairing. Contains the server's host, port, and API key. Only available in API mode (not web mode).

**Response:** SVG image

- `Content-Type: image/svg+xml`
- `Cache-Control: no-store`

**Status codes:** 404 if in web mode, 500 if server info unavailable, 503 if `segno` not installed

---

### GET /api/pairing-info

JSON server pairing details for programmatic access. Only available in API mode.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `api_key` | string | Server API key |
| `host` | string | Server hostname/IP |
| `port` | integer | Server port |
| `address` | string | Full address (external URL if configured, otherwise `host:port`) |

**Status codes:** 404 if in web mode, 500 if server info unavailable

---

## Audit Log

### GET /api/audit

Paginated audit entries with optional filters. See [Pagination](#pagination) for query parameters.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `entries` | object[] | Audit log entries |
| `entries[].id` | integer | Entry ID |
| `entries[].timestamp` | string | ISO timestamp |
| `entries[].operation` | string | Operation type |
| `entries[].description` | string | Human-readable description |
| `entries[].params` | object? | Operation parameters (JSON) |
| `entries[].status` | string | Result status |
| `entries[].duration_s` | number? | Operation duration in seconds |
| `entries[].source` | string | Source: `"web"`, `"ios"`, or `"api"` |
| `total` | integer | Total matching entries |
| `limit` | integer | Page size |
| `offset` | integer | Current offset |

---

### GET /api/audit/stats

Aggregate audit log statistics.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Total audit entries |
| `today` | integer | Entries from today |
| `by_operation` | object | Counts keyed by operation type |
| `by_status` | object | Counts keyed by status |

---

### POST /api/audit/clear

Delete old audit entries. Logs the clear action itself as a new audit entry.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `confirm` | boolean | Yes | Must be `true` to confirm deletion |
| `before_date` | string | No | Delete entries before this ISO date (omit for all) |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `deleted` | integer | Number of entries deleted |

**Status codes:** 400 if `confirm` not set

---

## About

### GET /api/about

Server version and release notes.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Server version (e.g., `"2.37.0"`) |
| `release_notes` | string | Full release notes text from `release-notes.txt` |

```json
{
  "version": "2.37.0",
  "release_notes": "Version 2.37.0 (2026-03-01):\n• Added Sources page\n..."
}
```
