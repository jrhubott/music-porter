# Plan: Simplify Sync Keys/Destinations & Move Config Data to DB

## Context

The sync key/destination system has accumulated complexity: destinations live in config.yaml while their tracking state lives in the DB, the `effective_key` pattern creates indirection (fall back to `name` when no `sync_key` is set), and clients contain sync key resolution logic (prefix conventions, priority ordering) that belongs on the server. This plan moves playlists and destinations from config.yaml into the SQLite database, simplifies the sync key model so every destination always has an explicit `sync_key`, and adds a server-side destination resolution endpoint so clients don't need to generate sync key names.

**Sync key simplification:** Today, `sync_key` is optional on destinations — when null, the `effective_key` property falls back to the destination `name`. This creates indirection. The new model makes `sync_key` always explicit: when a destination is created, `sync_key` is auto-set to the destination name (or a generated key like `usbkey-Lexar`). Linking still works the same way — change `sync_key` to a shared key. Unlinking creates a new independent key instead of setting to null. The `effective_key` property goes away because `sync_key` IS the tracking key, always.

```
Example — two destinations sharing a key (linked):
  "Lexar-Mac"   → sync_key = "usbkey-Lexar"  (shared)
  "Lexar-Linux" → sync_key = "usbkey-Lexar"  (shared)

Unlinking "Lexar-Mac":
  "Lexar-Mac"   → sync_key = "Lexar-Mac"     (new independent key)
  "Lexar-Linux" → sync_key = "usbkey-Lexar"  (unchanged)
```

**Guiding principles:**
- Complexity on the server, clients kept simple
- All SRS-22 user needs preserved (shared sync keys for same-device tracking, destination linking, incremental sync)
- No backward compatibility concerns — all clients updated simultaneously
- All clients updated: web dashboard, sync client CLI, sync client GUI, iOS app

---

## SRS-22 Compliance

All SRS-22 user needs are preserved. One minor wording change needed:

- **22.2.1**: Update "saved persistently in configuration" → "saved persistently" (drop implementation detail, storage moves to DB but user experience is identical).

No other SRS-22 requirements are affected — all describe user-facing behaviors, not implementation details.

---

## Pre-work: Commit Dirty File

Before starting this feature branch, commit the existing modified file `sync-client/packages/cli/src/commands/sync.ts` on `dev` to ensure a clean starting point.

---

## Phase 0: Migration Infrastructure (Permanent Pattern)

**File:** `porter_core.py` — changes to `migrate_db_schema()` and `migrate_config_schema()`

### 0a: Pre-migration backup (runs on every migration)

Add backup logic to both `migrate_db_schema()` and `migrate_config_schema()` so that **any** migration automatically archives the current file before modifying it:

1. At the start of each migration function, read the current version from the file
2. If `current_version < CODE_VERSION` (migration needed):
   - Create `data/archive/` directory if it doesn't exist
   - Copy `data/config.yaml` → `data/archive/config.yaml.v{current_version}`
   - Copy `data/music-porter.db` → `data/archive/music-porter.db.v{current_version}`
   - Only copy if the archive file doesn't already exist (idempotent)
3. Then proceed with migrations as usual

This ensures every migration is rollback-safe — the user can always restore the pre-migration file.

### 0b: Version-too-new guard (startup error)

Add a check at the start of both migration functions: if the file's version is **higher** than the code's version constant, raise a startup error and refuse to run. This prevents running old code against a DB/config that was migrated by newer code.

```python
if current_version > DB_SCHEMA_VERSION:
    raise RuntimeError(
        f"Database schema version {current_version} is newer than this "
        f"software supports ({DB_SCHEMA_VERSION}). Update the software or "
        f"restore from data/archive/."
    )
```

Same pattern for config:
```python
if current_version > CONFIG_SCHEMA_VERSION:
    raise RuntimeError(
        f"Config schema version {current_version} is newer than this "
        f"software supports ({CONFIG_SCHEMA_VERSION}). Update the software or "
        f"restore from data/archive/."
    )
```

---

## Phase 1: Database Schema Migration (v6 → v7)

**File:** `porter_core.py` — `migrate_db_schema()`

Add `if current < 7:` block creating two new tables:

```sql
CREATE TABLE IF NOT EXISTS playlists (
    key TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS destinations (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    sync_key TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_destinations_sync_key ON destinations(sync_key);
```

- `destinations.sync_key` is always non-null — no more `effective_key` fallback
- No FK constraint on `sync_key` → `sync_keys.key_name` (managed in application code, avoids cascade/restrict issues)
- Increment `DB_SCHEMA_VERSION` to 7

---

## Phase 2: New DB Classes

**File:** `porter_core.py`

### 2a: `PlaylistDB` class

New class following the same thread-safe pattern as `SyncTracker`/`TrackDB` (write lock, WAL reads):

| Method | Purpose |
|--------|---------|
| `get(key)` | Get single playlist by key |
| `get_all()` | List all playlists (ordered by rowid for stable ordering) |
| `add(key, url, name)` | Insert playlist, validate key format |
| `update(key, url=None, name=None)` | Update url/name fields |
| `remove(key)` | Delete playlist by key |
| `count()` | Return total playlist count |

Constructor accepts `db_path`, `audit_logger`, `audit_source` (same pattern as ConfigManager audit integration).

### 2b: Destination methods on `SyncTracker`

Add destination CRUD to `SyncTracker` (destinations are tightly coupled with sync tracking):

| Method | Purpose |
|--------|---------|
| `add_destination(name, path, sync_key=None)` | Add destination; if no sync_key, auto-create one using name; also creates sync_keys row |
| `get_destination(name)` | Get single destination by name |
| `get_all_destinations()` | List all saved destinations |
| `remove_destination(name)` | Remove destination (does NOT delete sync key or tracking data) |
| `rename_destination(old_name, new_name)` | Rename destination (sync_key unchanged) |
| `find_destination_by_path(path)` | Look up destination by schemed path |
| `link_destination(name, sync_key)` | Set destination's sync_key; auto-create sync_keys row if needed |
| `unlink_destination(name)` | Create new sync_key = destination name, set it |
| `resolve_destination(path=None, name=None, drive_name=None, explicit_key=None)` | Server-side resolution: find or create destination + sync key; returns destination + sync status |

**`resolve_destination()` logic** (moves complexity from clients to server):
1. If `name` provided → look up saved destination
2. If `path` provided → look up by path
3. If not found → auto-create:
   - Generate name from `drive_name` or path basename
   - Generate sync_key: `usbkey-<drive_name>` for USB paths, `client-<dirname>` for folders
   - If `explicit_key` provided, use that instead
   - Save destination to DB + create sync_keys row
4. Return destination object + sync status

Move `USB_SYNC_KEY_PREFIX` / `CLIENT_SYNC_KEY_PREFIX` constants from sync client to `porter_core.py`.

### 2c: Simplify `SyncDestination` dataclass

- Remove `effective_key` property entirely (sync_key is always set, no fallback needed)
- Update `to_api_dict()`: remove `effective_key` from response, just emit `sync_key`
- `sync_key` field becomes non-optional (`str` not `str | None`)

---

## Phase 3: Config Schema Migration (v3 → v4)

**File:** `porter_core.py` — `migrate_config_schema()`

Add `if current < 4:` block that:
1. Opens DB connection (tables exist from Phase 1 migration which runs first)
2. Reads `playlists` list from config.yaml → inserts each into `playlists` table (INSERT OR IGNORE)
3. Reads `destinations` list from config.yaml → for each:
   - If `sync_key` is set → use it
   - If `sync_key` is null → set `sync_key = name`
   - Insert into `destinations` table (INSERT OR IGNORE)
   - Ensure sync_keys row exists (INSERT OR IGNORE into sync_keys)
4. Removes `playlists` and `destinations` keys from config.yaml
5. Sets schema_version to 4

**Migration ordering:** DB migrations run before config migrations (existing startup order). Phase 1 creates the tables, Phase 3 populates them.

**Fresh install:** Config has no playlists/destinations keys → migration is a no-op. Tables created empty by Phase 1.

Increment `CONFIG_SCHEMA_VERSION` to 4.

---

## Phase 4: Server-Side Destination Resolution Endpoint

**File:** `web_api.py`

### New endpoint: `POST /api/sync/destinations/resolve`

Request:
```json
{
  "path": "usb:///Volumes/Lexar/RZR/Music",
  "drive_name": "Lexar",
  "sync_key": "my-explicit-key",
  "name": "saved-dest-name"
}
```
All fields optional but at least `path` or `name` required.

Response:
```json
{
  "destination": { "name": "...", "path": "...", "sync_key": "...", "type": "...", "available": true },
  "created": false,
  "sync_status": { "sync_key": "...", "total_files": 100, "synced_files": 80, "new_files": 20, "playlists": [...] }
}
```

Delegates to `SyncTracker.resolve_destination()` (Phase 2b). Single endpoint replaces client-side `resolveSyncKey()` logic + separate sync status fetch.

---

## Phase 5: ConfigManager Cleanup

**File:** `porter_core.py`

Remove from `ConfigManager`:
- `self.playlists` list and `self.destinations` list (in-memory state)
- All playlist methods: `get_playlist_by_key()`, `add_playlist()`, `update_playlist()`, `remove_playlist()`, playlist validation in `_load_yaml()`
- All destination methods: `get_destination()`, `find_destination_by_path()`, `add_destination()`, `remove_destination()`, `update_destination_link()`, `ensure_destination()`, `rename_destination()`, `rename_sync_key_refs()`
- Playlist/destination serialization from `_save()`
- Destination loading from `_load_yaml()`

Keep: settings, output_types/profiles, api_key management, `_on_change` callback.

Update `_create_default()` to not include `playlists` or `destinations` sections.

Update `DependencyChecker.get_status()` to accept `playlist_count` parameter instead of accessing `config.playlists`.

### 5b: Remove dead code

After removing playlist/destination methods from ConfigManager, scan for and remove:
- `PlaylistConfig` dataclass if no longer used (playlists now represented as DB rows/dicts)
- Any helper methods that only existed to support playlist/destination config CRUD
- Unused imports that were only needed for the removed methods
- `effective_key` property and any references throughout `porter_core.py`, `web_api.py`, `web_ui.py`, and templates
- Any template JavaScript that references `effective_key` (replace with `sync_key`)
- Dead sync client code: `USB_SYNC_KEY_PREFIX`, `CLIENT_SYNC_KEY_PREFIX` constants and `resolveSyncKey()` method

### 5c: Consolidate redundant/duplicate code

Identify and consolidate duplicated patterns into shared helpers:
- DB classes (`SyncTracker`, `PlaylistDB`, `TrackDB`, `AuditLogger`, `TaskHistoryDB`, `EQConfigManager`) all share the same thread-safe SQLite setup pattern (WAL mode, write lock, connection management). Extract a shared base class or helper for DB initialization if not already present.
- Destination path scheme handling (`usb://`, `folder://`, `web-client://`) — ensure scheme parsing/construction is done in one place (on `SyncDestination` or a utility), not repeated across `web_api.py` endpoints
- Audit logging wiring — the pattern of accepting `audit_logger` + `audit_source` and calling `audit_logger.log()` is repeated across many classes. Ensure the new `PlaylistDB` and `SyncTracker` destination methods use the same pattern consistently without duplication.
- Any repeated validation logic (destination name format, playlist key format) should be in one place

---

## Phase 6: API & Web Layer Updates

### 6a: `web_ui.py` — AppContext

Add `playlist_db: PlaylistDB` field to `AppContext` dataclass. Initialize in `create_app()`.

Update `PipelineScheduler` to accept `playlist_db` instead of reading `config.playlists`.

### 6b: `web_api.py` — Endpoint updates

**Playlist endpoints** — switch from `config` to `ctx.playlist_db`:
- `GET /api/playlists` → `playlist_db.get_all()`
- `POST /api/playlists` → `playlist_db.add()`
- `PUT /api/playlists/<key>` → `playlist_db.update()`
- `DELETE /api/playlists/<key>` → `playlist_db.remove()`

**Destination endpoints** — switch from `config` to `ctx.sync_tracker`:
- `GET /api/sync/destinations` → `sync_tracker.get_all_destinations()` + USB auto-detection
- `POST /api/sync/destinations` → `sync_tracker.add_destination()`
- `DELETE /api/sync/destinations/<name>` → `sync_tracker.remove_destination()`
- `PUT /api/sync/destinations/<name>/link` → `sync_tracker.link_destination()` + merge
- `POST /api/sync/destinations/<name>/rename` → `sync_tracker.rename_destination()`
- `POST /api/sync/destinations/resolve` → NEW (Phase 4)

**Sync key rename** — update `POST /api/sync/keys/<key>/rename`:
- Instead of calling `config.rename_sync_key_refs()`, update `destinations` table directly via `SyncTracker`

**Client record** — `POST /api/sync/client-record`:
- Switch destination lookup from `config.find_destination_by_path()` to `sync_tracker.find_destination_by_path()`
- Auto-registration logic now creates DB entries instead of config entries

**Pipeline/sync endpoints** — update to use `playlist_db` for playlist lookup.

**Response shapes simplified** — `to_api_dict()` emits `sync_key` (no more `effective_key`). All clients updated to match.

---

## Phase 7: Client Updates

### 7a: Sync Client Core (`sync-client/packages/core/`)

**`api-client.ts`:**
- Add `resolveDestination(path?, name?, driveName?, syncKey?)` method → calls `POST /api/sync/destinations/resolve`

**`sync-engine.ts`:**
- Remove `resolveSyncKey()` private method (lines 596-610)
- Before sync: call `client.resolveDestination()` to get sync key from server
- Offline fallback: if server unreachable, read sync key from manifest (existing behavior)
- Remove import/usage of `USB_SYNC_KEY_PREFIX` and `CLIENT_SYNC_KEY_PREFIX`

**`constants.ts`:**
- Remove `USB_SYNC_KEY_PREFIX` and `CLIENT_SYNC_KEY_PREFIX` (moved to server)

**`types.ts`:**
- Add `ResolveDestinationResponse` interface

### 7b: Sync Client CLI (`sync-client/packages/cli/`)

**`commands/sync.ts`:**
- Keep `--key` flag as explicit override (passed to resolve endpoint)
- Remove client-side USB drive name → sync key generation
- Destination resolution now comes from server response

**`commands/destinations.ts`:**
- `link` command: no changes (already calls `client.linkDestination()`)
- `unlink` command: calls `client.linkDestination(name, null)` → server creates new key

### 7c: Sync Client GUI (`sync-client/packages/gui/`)

**`LinkDestinationModal.tsx`:**
- Remove `client-${destinationName}` default key generation (line 25)
- When mode is "new", let server generate the key name (don't pre-populate)
- Or: call resolve endpoint to get server-suggested key name
- Keep "use existing sync key" mode

**IPC/preload:** ensure `resolveDestination()` is exposed if sync page needs it.

### 7d: iOS App — Full Sync Feature Implementation (`ios/`)

**Goal:** Bring iOS sync features up to par with SRS-22, using the simplified server-side sync key model. iOS triggers server-side syncs and exports cached files via UIDocumentPicker — it cannot sync to arbitrary local folders due to sandbox restrictions.

#### 7d-i: Model Updates (`Models/USBSyncStatus.swift`)
- `SyncDestination.syncKey`: change from `String?` to `String` (always present)
- Remove `effectiveKey` field and its CodingKey entirely
- Add `ResolveDestinationResponse` model for the new resolve endpoint
- Update any views/services referencing `effectiveKey` to use `syncKey`

#### 7d-ii: New API Calls (`Services/APIClient.swift`)
- `resolveDestination(path:, name:, driveName:, syncKey:)` → `POST /api/sync/destinations/resolve`
- `linkDestination(name:, syncKey:)` → `PUT /api/sync/destinations/<name>/link`
- `unlinkDestination(name:)` → `PUT /api/sync/destinations/<name>/link` (with null sync_key)
- `renameSyncKey(oldKey:, newKey:)` → `POST /api/sync/keys/<key>/rename`
- `addDestination(name:, path:, syncKey:)` → `POST /api/sync/destinations`
- `renameDestination(oldName:, newName:)` → `POST /api/sync/destinations/<name>/rename`

#### 7d-iii: Destination Management View (NEW)
New `DestinationManagementView.swift` providing full CRUD:
- List all saved destinations with type, path, sync key, availability (22.2.4, 22.2.5)
- Add new destination with name and path (22.2.1)
- Remove destination via swipe action (22.2.2)
- Rename destination via context menu (22.2.3)
- Show sync key association for each destination
- Navigate to this view from SyncStatusView or Settings

#### 7d-iv: Destination Linking Sheet (NEW)
New `LinkDestinationSheet.swift` for sync key association (22.5.1-22.5.5):
- Two modes: "Create new sync key" (default) / "Use existing sync key"
- When "existing" selected, list all available sync keys with file/playlist counts
- Presented when user taps a destination's sync key, or on first sync to a new folder
- Calls `linkDestination()` API
- Unlink action creates independent key via `unlinkDestination()`
- Merge feedback shown if tracking data was consolidated

#### 7d-v: Sync Key Rename (22.4.6)
Add rename action to sync key swipe/context menu in `SyncStatusView.swift`:
- Present text input sheet for new key name
- Call `renameSyncKey()` API

#### 7d-vi: Sync Execution Improvements (22.1.x, 22.7.x)
- Destination selection before sync: present destination picker (saved + resolve endpoint)
- Profile selection before sync (22.8.1, 22.7.30)
- Real-time progress via SSE during sync (22.1.5, 22.7.9, 22.7.10) — already uses `OperationViewModel`
- Cancel sync in progress (22.1.8, 22.7.11)
- Summary after sync (22.1.7, 22.7.12)
- Force re-sync option (22.7.8)

#### 7d-vii: Recently Used Destinations (22.7.22)
- Track recently used destinations in local storage
- Show as dropdown/list for quick selection

#### 7d-viii: Settings Additions (22.7.30-22.7.32)
- Profile selector in Settings (if not already present)
- Server version and release notes display (22.7.32)

---

## Phase 8: SRS & Documentation

### 8a: Delete old SRS files
- Delete `SRS/SRS.md`
- Delete `SRS/SRS-20-ios-direct-export.md`
- Delete `SRS/SRS-21-ios-background-downloads.md`

### 8b: Update SRS-22

**Wording change:**
- 22.2.1: Change "saved persistently in configuration" → "saved persistently"

**iOS column audit — mark [x] for already-implemented items:**
- 22.4.2: View sync keys with file counts → `SyncStatusView.swift`
- 22.4.3: Delete sync key → `APIClient.deleteSyncKey()`
- 22.4.4: Remove playlist tracking from key → `APIClient.deleteSyncPlaylist()`
- 22.4.5: Prune stale records → `APIClient.pruneSyncKey()`
- 22.6.1-22.6.4: Sync status views → `SyncStatusView.swift`
- 22.7.1: Server auto-discovery (Bonjour) → implemented
- 22.7.2: Manual server URL + API key → implemented
- 22.7.3: Local-first, external-fallback → implemented
- 22.7.4: Reconnect/disconnect/offline controls → implemented
- 22.7.14-22.7.19: Offline caching → `AudioCacheManager`, `MetadataCache`, `PrefetchEngine`

**iOS column — mark N/A (iOS sandbox prevents these):**
- 22.3.1: USB auto-detection
- 22.3.2: Exclude system volumes
- 22.3.3: Cross-platform USB detection
- 22.3.4: Eject USB drive
- 22.7.20: USB drive auto-detection with free space
- 22.7.24: Eject USB from app
- 22.7.25: Auto-eject toggle
- 22.7.26: Auto-sync for USB drives

**iOS column — mark [x] after implementing in Phase 7d:**
- 22.1.1-22.1.8, 22.2.1-22.2.5, 22.4.1, 22.4.6, 22.5.1-22.5.5, 22.6.5, 22.7.5-22.7.13, 22.7.21-22.7.23, 22.7.30-22.7.32, 22.8.1-22.8.4, 22.9.x

### 8c: Update docs
- `docs/DB_SCHEMA.md` — Add `playlists` and `destinations` tables, update to schema v7
- `docs/SERVER_API.md` — Add `POST /api/sync/destinations/resolve` endpoint
- `docs/openapi.yaml` — Add resolve endpoint
- `CLAUDE.md` — Update DB schema section (v7, 9 tables), config schema section (v4, no playlists/destinations), update ConfigManager description, add PlaylistDB to class listing

---

## Verification

1. **Migration test:** Start with populated config.yaml (v3, with playlists + destinations). Run server. Verify:
   - DB has playlists/destinations tables with migrated data
   - config.yaml is v4, no `playlists` or `destinations` keys
   - `GET /api/playlists` returns all playlists
   - `GET /api/sync/destinations` returns all destinations with `sync_key` always set

2. **Fresh install test:** Delete config.yaml and DB. Start server. Verify:
   - config.yaml created with only settings + output_types
   - DB created with all tables, playlists/destinations empty
   - Adding playlist/destination via API works

3. **CRUD tests:** Add, update, delete playlists and destinations via API. Verify audit trail.

4. **Sync key simplification:** Add destination → verify sync_key auto-created. Link to different key → verify change. Unlink → verify new key created. Rename destination → verify sync_key unchanged.

5. **Resolve endpoint:** Call with USB path → verify `usbkey-` key generated. Call with folder → verify `client-` key. Call with existing destination name → verify lookup works.

6. **Sync client test:** Run `mporter-sync sync -d /some/folder` → verify it calls resolve endpoint, gets key from server, syncs files correctly.

7. **Lint:** `ruff check .` (Python), `npm run lint` in sync-client (TypeScript).

---

## Critical Files

| File | Changes |
|------|---------|
| `porter_core.py` | DB migration v7, config migration v4, PlaylistDB class, SyncTracker destination methods, SyncDestination simplification, ConfigManager cleanup |
| `web_api.py` | All playlist/destination endpoint updates, new resolve endpoint |
| `web_ui.py` | AppContext + PlaylistDB, PipelineScheduler update |
| `sync-client/packages/core/src/sync-engine.ts` | Remove resolveSyncKey, use server resolve |
| `sync-client/packages/core/src/api-client.ts` | Add resolveDestination method |
| `sync-client/packages/core/src/constants.ts` | Remove sync key prefix constants |
| `sync-client/packages/core/src/types.ts` | Add ResolveDestinationResponse |
| `sync-client/packages/gui/src/renderer/components/LinkDestinationModal.tsx` | Simplify key generation |
| `sync-client/packages/cli/src/commands/sync.ts` | Remove client-side key resolution |
| `ios/MusicPorter/MusicPorter/Models/USBSyncStatus.swift` | syncKey non-optional, remove effectiveKey, add ResolveDestinationResponse |
| `ios/MusicPorter/MusicPorter/Services/APIClient.swift` | Add resolveDestination, linkDestination, renameSyncKey, addDestination, renameDestination |
| `ios/MusicPorter/MusicPorter/Views/SyncStatusView.swift` | Update for new models, add rename sync key action |
| `ios/MusicPorter/MusicPorter/Views/DestinationManagementView.swift` | NEW — destination CRUD UI |
| `ios/MusicPorter/MusicPorter/Views/LinkDestinationSheet.swift` | NEW — link/unlink sync key UI |
| `docs/DB_SCHEMA.md` | New tables |
| `docs/SERVER_API.md` | New endpoint |
| `CLAUDE.md` | Schema updates |
