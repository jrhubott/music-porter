# Database Schema Reference

SQLite database stored at `data/music-porter.db`. Current version: **DB_SCHEMA_VERSION = 6** (defined in `porter_core.py` ~line 71).

## PRAGMA Settings

All connections use:

- `journal_mode=WAL` — Write-Ahead Logging for concurrent read access
- `user_version` — Stores the schema version integer
- `foreign_keys=ON` — Enforced only in `SyncTracker` class

## Thread Safety Model

All DB classes follow the same pattern:

- **Write lock:** `threading.Lock()` protects all insert/update/delete operations
- **Reads:** Lockless (WAL mode allows concurrent readers)
- **Connections:** New connection per method call (`check_same_thread=False`)
- **Row factory:** `sqlite3.Row` for dictionary-style access

---

## Tables

### audit\_entries

Persistent audit trail for all operations. Added in **migration 0 -> 1**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-generated row ID |
| timestamp | TEXT | NOT NULL | ISO 8601 timestamp |
| operation | TEXT | NOT NULL | Operation type (download, convert, sync, etc.) |
| description | TEXT | NOT NULL | Human-readable description |
| params | TEXT | | JSON string of operation parameters |
| status | TEXT | NOT NULL | pending, completed, or failed |
| duration\_s | REAL | | Execution time in seconds |
| source | TEXT | NOT NULL DEFAULT 'cli' | Origin: cli, web, ios, or api |

**Indexes:** `idx_audit_timestamp(timestamp)`, `idx_audit_operation(operation)`, `idx_audit_status(status)`

**Class:** `AuditLogger`

---

### task\_history

Background task tracking with persistence across restarts. Added in **migration 0 -> 1**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | TEXT | PRIMARY KEY | UUID string identifier |
| operation | TEXT | NOT NULL | Operation type (pipeline, convert, etc.) |
| description | TEXT | NOT NULL | Task description |
| status | TEXT | NOT NULL DEFAULT 'pending' | pending, running, completed, or failed |
| result | TEXT | | JSON string of operation result |
| error | TEXT | NOT NULL DEFAULT '' | Error message if failed |
| started\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch timestamp |
| finished\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch timestamp |
| source | TEXT | NOT NULL DEFAULT 'web' | Origin: web, ios, or api |

**Indexes:** `idx_task_status(status)`, `idx_task_operation(operation)`, `idx_task_started_at(started_at)`

**Startup recovery:** All rows with status `running` or `pending` are marked `failed` with error "Server restarted during execution".

**Class:** `TaskHistoryDB`

---

### sync\_keys

Sync destination metadata for tracking file synchronization. Added in **migration 0 -> 1**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| key\_name | TEXT | PRIMARY KEY | Unique sync destination identifier |
| last\_sync\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch of last sync |
| created\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch of creation |

**Child table:** `sync_files` (FK with ON DELETE CASCADE)

**Class:** `SyncTracker`

---

### sync\_files

Per-file sync records. Added in **migration 0 -> 1**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-generated row ID |
| sync\_key | TEXT | NOT NULL, FK -> sync\_keys(key\_name) ON DELETE CASCADE | Destination identifier |
| file\_path | TEXT | NOT NULL | Relative path to audio file |
| playlist | TEXT | NOT NULL | Playlist identifier |
| synced\_at | REAL | NOT NULL | Unix epoch of sync |

**Constraints:** `UNIQUE(sync_key, file_path, playlist)`

**Indexes:** `idx_sync_files_key(sync_key)`, `idx_sync_files_playlist(sync_key, playlist)`

**Class:** `SyncTracker`

---

### eq\_presets

Audio EQ configuration per profile with optional per-playlist overrides. Added in **migration 1 -> 2**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-generated row ID |
| profile | TEXT | NOT NULL | Output profile name |
| playlist | TEXT | | Playlist key (NULL = profile default) |
| loudnorm | INTEGER | NOT NULL DEFAULT 0 | Boolean: loudness normalization |
| bass\_boost | INTEGER | NOT NULL DEFAULT 0 | Boolean: bass boost |
| treble\_boost | INTEGER | NOT NULL DEFAULT 0 | Boolean: treble boost |
| compressor | INTEGER | NOT NULL DEFAULT 0 | Boolean: compressor |
| updated\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch timestamp |

**Constraints:** `UNIQUE(profile, playlist)`

**Indexes:** `idx_eq_profile(profile)`, `idx_eq_profile_playlist(profile, playlist)`

**Precedence:** playlist-specific overrides profile default, which overrides no EQ.

**Class:** `EQConfigManager`

---

### scheduled\_jobs

Persistent scheduler state. Added in **migration 2 -> 3**.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| job\_name | TEXT | PRIMARY KEY | Unique job identifier |
| next\_run\_time | REAL | | Unix epoch for next execution |
| last\_run\_time | REAL | | Unix epoch of last execution |
| last\_run\_status | TEXT | NOT NULL DEFAULT '' | Status of last run |
| last\_run\_error | TEXT | NOT NULL DEFAULT '' | Error from last run |
| on\_missed | TEXT | NOT NULL DEFAULT 'run' | Missed run policy: run or skip |
| updated\_at | REAL | NOT NULL DEFAULT 0 | Unix epoch timestamp |

**Indexes:** `idx_scheduled_jobs_next(next_run_time)`

**Class:** `ScheduledJobsDB`

---

### tracks

Library metadata for all MP3s. Core table added in **migration 3 -> 4**, source\_m4a\_path index added in **migration 4 -> 5**, 14 metadata columns added in **migration 5 -> 6**.

| Column | Type | Constraints | Added | Description |
|--------|------|-------------|-------|-------------|
| uuid | TEXT | PRIMARY KEY | v4 | Matches TXXX:TrackUUID tag in MP3 |
| playlist | TEXT | NOT NULL | v4 | Playlist key |
| file\_path | TEXT | NOT NULL | v4 | Path to MP3 file |
| title | TEXT | NOT NULL | v4 | Song title |
| artist | TEXT | NOT NULL | v4 | Artist name |
| album | TEXT | NOT NULL | v4 | Album name |
| cover\_art\_path | TEXT | | v4 | Path to cover art file |
| cover\_art\_hash | TEXT | | v4 | SHA-256 hash (16 chars) |
| duration\_s | REAL | | v4 | Duration in seconds |
| file\_size\_bytes | INTEGER | | v4 | File size in bytes |
| source\_m4a\_path | TEXT | | v4 | Original M4A path (duplicate detection) |
| genre | TEXT | | v6 | Genre |
| track\_number | INTEGER | | v6 | Track position |
| track\_total | INTEGER | | v6 | Total tracks in album |
| disc\_number | INTEGER | | v6 | Disc position |
| disc\_total | INTEGER | | v6 | Total discs |
| year | TEXT | | v6 | Release year |
| composer | TEXT | | v6 | Composer/songwriter |
| album\_artist | TEXT | | v6 | Album artist |
| bpm | INTEGER | | v6 | Beats per minute |
| comment | TEXT | | v6 | Comments/notes |
| compilation | INTEGER | | v6 | Boolean: is compilation |
| grouping | TEXT | | v6 | Grouping metadata |
| lyrics | TEXT | | v6 | Lyrics text |
| copyright | TEXT | | v6 | Copyright info |
| created\_at | REAL | NOT NULL | v4 | Unix epoch timestamp |
| updated\_at | REAL | NOT NULL | v4 | Unix epoch timestamp |

**Indexes:** `idx_tracks_playlist(playlist)` (v4), `idx_tracks_file_path(file_path)` (v4), `idx_tracks_source_m4a(source_m4a_path)` (v5)

**UPSERT:** `INSERT ... ON CONFLICT(uuid) DO UPDATE SET` for atomic insert-or-update.

**Class:** `TrackDB`

---

## Migration History

| From | To | Changes |
|------|----|---------|
| 0 | 1 | Created `audit_entries`, `task_history`, `sync_keys`, `sync_files` with indexes. Legacy rename: `usb_keys` -> `sync_keys`, `usb_sync_files` -> `sync_files`. |
| 1 | 2 | Added `eq_presets` table with UNIQUE(profile, playlist). |
| 2 | 3 | Added `scheduled_jobs` table. |
| 3 | 4 | Added `tracks` table with playlist and file\_path indexes. |
| 4 | 5 | Added `idx_tracks_source_m4a` index on `tracks(source_m4a_path)`. |
| 5 | 6 | Added 14 metadata columns to `tracks` (genre through copyright). Restructured library directories and updated file paths in existing rows. |

## Notes

- Migrations run sequentially at startup via `migrate_db_schema()` before any DB class is instantiated.
- Each `if current < N:` block is idempotent and sets the version to exactly N.
- Fresh installs run through all migrations 0 -> 1 -> 2 -> ... -> 6.
- Never modify existing migration blocks; always add a new `if current < N:` block.
