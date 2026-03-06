# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## User Preferences

### Git Commit Preferences

- **Never include** Co-Authored-By lines in commit messages
- Commits should be authored solely by the user

### README Future Features

- When implementing a future feature from the README list, **strikethrough** the item (~~text~~) with a note like "*(implemented in vX.Y.Z)*" instead of removing it
- Keep the original numbering intact

### Code Style

- **No magic numbers** — define named constants for numeric values; avoid bare literals in logic

## Architecture Principles

- **Keep complexity in the server code wherever possible.** Add/update API methods to simplify client operations. Clients should call simple endpoints; the server handles the heavy lifting.

## Requirements Handling

### Workflow

- Requirements (SRS) **must** be written and reviewed **before** implementation begins
- When asked to "work on requirements", **only** produce the SRS document — do not plan or begin implementation
- Implementation starts only after explicit user instruction
- These are separate phases — never combine them
- **Always use a feature branch** when adding or changing SRS requirements — never commit SRS changes directly to main or dev

### SRS Document Format

- Tables with columns: ID, Web, CLI, GUI, iOS, Requirement
- Client columns track implementation status: `[x]` = implemented, `[ ]` = not yet implemented, `N/A` = explicitly decided not applicable for that client
- New requirements start with `[ ]` in all client columns
- All SRS files use the 4 client columns for consistency
- Existing SRS files are migrated to the new format gradually (when next touched)
- Each requirement is written as a **user need** with an **acceptance criteria**: "As a user, I can ... so that .... Acceptance: ..."
- **IDs must be globally unique** across all SRS documents in `SRS/` — use the entry's sequential number as the first digit (e.g., entry 8 uses IDs `8.1.1`, `8.2.1`, etc.)
- When creating a new SRS, check existing files in `SRS/` for the highest entry number and use the next one
- Edge cases are the last subsection under Requirements
- Store individual SRS files in the `SRS/` directory
- Requirements documents **outside `SRS/`** (e.g. build tooling in `build/`) are not required to use the project SRS table format. They should define their own column schema appropriate to their domain and document it clearly at the top of the file.
- Organized by **user feature** (not by internal class or module)
- Each entry maps to a user-facing capability, aligned with API endpoints where applicable
- Cross-cutting concerns (logging, progress, server flags) go in the "Server & Runtime" entry
- Related features may be merged (e.g., cookie management is part of "Download & Authentication")
- Requirements must be detailed enough to **reimplement the software** from the SRS alone

### During Implementation

- Mark the relevant client columns `[x]` as each requirement is completed for that client
- Add new SRS items if requirements are discovered during design or implementation
- Update the SRS whenever the user requests changes — keep in sync with the current implementation

### SRS Lifecycle

- SRS validation is **not** enforced at merge time — implementation status is tracked by client columns for visibility, not as a gate
- SRS files remain in `SRS/` permanently — they are **not** archived or deleted after merge

## Project Overview

Music Porter is a server-based music playlist management and conversion tool. It downloads Apple Music playlists, converts them to MP3, stores metadata in a SQLite database, and syncs to destinations with profile-specific tags applied on-the-fly. All functionality is accessed via a web dashboard and REST API — there is no CLI interface.

## Architecture

### Core Workflow Pipeline

The system follows a DB-centric pipeline:

1. **Download** → Downloads Apple Music playlists as M4A files via gamdl into `library/source/gamdl/<playlist>/`
2. **Convert** → Converts M4A to MP3 using ffmpeg (libmp3lame, default: lossless 320kbps CBR). Each MP3 gets only a `TXXX:TrackUUID` tag; all metadata is stored in TrackDB
3. **Library** → MP3s stored as `<uuid>.mp3` in `library/audio/` (flat), cover art in `library/artwork/<uuid>.ext`, metadata in SQLite `tracks` table
4. **Sync** → TagApplicator applies profile-specific tags on-the-fly during download/sync. Output files get human-readable names (`Artist - Title.mp3`) at the destination

### Entry Point

**`music-porter`** (Python) — Server-only entry point. Starts the Flask web server with web dashboard and REST API.

```bash
./music-porter                  # Start server (default: 0.0.0.0:5555)
./music-porter server           # Explicit server subcommand
./music-porter server --port 8080 --show-api-key
./music-porter --version
```

Server flags: `--host`, `--port`, `--show-api-key`, `--no-bonjour`, `--behind-proxy`, `--proxy-count`, `--no-venv`.

### Library Storage Model

Library MP3s are **clean** — they carry only a `TXXX:TrackUUID` identifier tag. All human-readable metadata lives in TrackDB (SQLite):

- **Source M4As on disk:** `library/source/gamdl/<playlist>/` — nested by Artist/Album (gamdl structure)
- **Output MP3s on disk:** `library/audio/<uuid>.mp3` — UUID-named, flat, no artist/title in filename
- **Cover art on disk:** `library/artwork/<uuid>.ext` — flat, extracted from M4A source during conversion
- **Metadata in DB:** `tracks` table with uuid (PK), playlist, file\_path, title, artist, album, cover\_art\_path, cover\_art\_hash, duration\_s, file\_size\_bytes, source\_m4a\_path, genre, track\_number, track\_total, disc\_number, disc\_total, year, composer, album\_artist, bpm, comment, compilation, grouping, lyrics, copyright, created\_at, updated\_at
- **Duplicate detection:** TrackDB lookup by `source_m4a_path` (indexed) — no file-exists check needed

### TagApplicator

Applies profile-specific ID3 tags on-the-fly during sync and download. Library MP3s are never modified.

- `build_tagged_stream()` — Returns (id3\_bytes, audio\_offset, total\_size) for HTTP streaming. The server prepends profile-tagged ID3 header to the raw audio data
- `apply_tags_to_file()` — Writes a fully-tagged copy to an output path (for physical sync)
- `build_output_filename()` — Builds human-readable filename from profile's `filename` template (e.g., `{artist} - {title}`)
- `build_output_subdir()` — Builds subdirectory from profile's `directory` template

### Output Type Profiles

Profiles are defined in `data/profiles.yaml` under the `output` key. Applied at sync/download time by TagApplicator, not at conversion time.

| Profile | ID3 | Artwork | Album Tag | Artist Tag | Genre | Filename |
|---------|-----|---------|-----------|------------|-------|----------|
| `ride-command` (default) | v2.3 | 100px | playlist name | "Various" | "Playlist" | `{artist} - {title}` |
| `basic` | v2.4 | original | original | original | (none) | `{artist} - {title}` |

Profile fields: `id3_title`, `id3_artist`, `id3_album`, `id3_genre`, `id3_extra` (ID3 tag templates), `id3_versions` (list), `artwork_size` (px, 0=original, -1=strip), `filename`, `directory` (output path templates), `usb_dir`.

### MP3 Quality Presets

Quality is set at conversion time (not per-profile). Presets: `lossless` (default, CBR 320kbps), `high` (VBR q2, ~190-250kbps), `medium` (VBR q4, ~165-210kbps), `low` (VBR q6, ~115-150kbps).

## Development Setup

### Platform Support

Supports **macOS**, **Linux**, and **Windows** (auto-detected at startup). Platform-specific USB detection, ejection, and ffmpeg installation.

### Prerequisites & Setup

- Python 3.8+, ffmpeg (system binary), and pip dependencies in venv
- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Pip packages: gamdl, mutagen, ffmpeg-python, selenium, webdriver-manager, Pillow, PyYAML, flask
- `config.yaml` auto-created on first run

### Linting

Uses **Ruff** (Python), **PyMarkdown** (Markdown), **djLint** (Jinja2/HTML). Config in `pyproject.toml`. Install: `source .venv/bin/activate && pip install -r requirements-dev.txt`.

```bash
source .venv/bin/activate
ruff check .                                                 # Python (lint)
ruff check --fix .                                           # Python (auto-fix)
pymarkdown scan -r --respect-gitignore .                     # Markdown
djlint server/templates/ --lint                              # Templates (lint)
djlint server/templates/ --reformat                          # Templates (auto-fix)
```

All three must pass clean before merging to main. Linting is recommended but not enforced at `/merge-to-dev` time.

**Important:** Always run `ruff check` without `--select` overrides. Using `--select` bypasses the `ignore` list in `pyproject.toml` and surfaces intentionally suppressed rules. Never use `--select` unless explicitly asked.

### Branch Workflow (3-Tier)

The project uses a 3-tier branch model: **feature -> dev -> main**.

- **`main`** = stable releases only. Every commit on main is tagged with a version. Never commit directly to main.
- **`dev`** = persistent integration branch. VERSION always has a `-dev` suffix (e.g., `"2.31.0-dev"`). Multiple features are tested together here before release.
- **Feature branches** = short-lived, for individual features/fixes. Branch from `dev` (not main).

**Branch naming:** `feature/`, `bugfix/`, `refactor/`, `docs/` prefix + lowercase-hyphenated description (2-4 words). Examples: `feature/playlist-search`, `bugfix/tag-double-prefix`.

**Creating:** Start from dev, create branch, set `VERSION = "X.Y.Z-branch-name"` in `server/core/constants.py` (base version from dev, replacing `-dev` with `-branch-name`) as first commit.

**Planning mode — CRITICAL:** After a plan is approved, the **absolute first step** before doing ANYTHING is to ask the user which branch to use via `AskUserQuestion`. This is **non-negotiable** — do NOT start reading code, editing files, or any other action. The branch question MUST be the very first thing after plan approval:
- **Feature branch** (default, recommended) — creates `feature/<name>` branch from dev
- **Bugfix branch** — creates `bugfix/<name>` branch from dev
- **Stay on dev** — no branch created, work directly on dev

If a branch is created, set the branch version in `server/core/constants.py` as the first commit, then begin implementation. Never modify implementation files before the branch question is answered.

**Working:** Keep branch version throughout development. For long-lived branches, rebase on `origin/dev` periodically.

**Small fixes:** Single-commit fixes, docs, and config changes can go directly to dev (never directly to main).

**Merging to dev:** Use `/merge-to-dev` skill — fast and fully automatic, no user prompts, no SRS validation, no version bump.

**Merging to main:** Use `/merge-dev-to-main` skill (must be on dev) — full validation: version bump, tagging, release notes, sets next `-dev` version, offers branch cleanup, pushes both main and dev.

**Pre-merge checklist (for main):** Clean working tree, no debug code, up to date with remote, README future features updated.

### Version Management

Version defined in `server/core/constants.py`. Uses semantic versioning (MAJOR.MINOR.PATCH).

**On `dev` branch:** `VERSION = "X.Y.Z-dev+<hash>"` (e.g., `"2.31.0-dev+a425c6c"`). The `-dev` suffix is always present on dev, with `+<short-hash>` SemVer build metadata appended by merge-to-dev.

**On feature branches:** `VERSION = "X.Y.Z-branch-name"` (e.g., `"2.31.0-cookie-management"`). Base version comes from dev (strip the `-dev+hash` suffix), replacing with `-branch-name`. Set as first commit.

**merge-to-dev:** Restores the `-dev` suffix and appends `+<short-hash>` of the merge commit (SemVer build metadata).

**merge-dev-to-main:** Remove `-dev+hash` suffix, bump version (PATCH/MINOR/MAJOR), create git tag (`git tag vX.Y.Z`). After tagging, sync dev with main and set the next PATCH dev version (e.g., 2.34.0 → 2.34.1-dev) on dev (no hash — the next merge-to-dev adds it).

**Release notes:** When bumping the version, prepend a new entry to the top of `release-notes.txt` (project root) summarizing the changes in that release. Format: `Version X.Y.Z (YYYY-MM-DD):` header followed by bullet points (`• description`). This is displayed in the web About page.

**Display:** Shown in startup banner, `--version` flag, and log files.

### Common Gotchas

**Cookies:** Requires `cookies.txt` with Apple Music session cookies. Auto-validates at startup; expired cookies trigger interactive refresh via Selenium (Chrome/Firefox/Safari/Edge). Backup at `cookies.txt.backup`. See `docs/COOKIE-MANAGEMENT-GUIDE.md`.

**Virtual Environment:** Must activate before running: `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\activate` (Windows).

**Temp Directories:** `gamdl_temp_*` directories safe to delete after downloads.

**USB Detection:** Auto-detects by platform — macOS: `/Volumes/`, Linux: `/media/$USER/` + `/mnt/`, Windows: drive letters. Eject: automatic on macOS/Linux, manual on Windows.

**JS `onclick` string arguments:** When building HTML strings in JS template literals, never use `JSON.stringify()` for string arguments inside `onclick="..."` attributes — `JSON.stringify` wraps the value in double quotes, which terminates the attribute early and silently breaks the handler. Use single-quote wrapping instead, with `&apos;` to escape any literal single quotes in the value:
```javascript
onclick="myFn('${primaryDest}', '${label.replace(/'/g, '&apos;')}')"
```

## Directory Structure

**Key files:** `music-porter` (entry point), `server/core/` (split business logic modules), `server/web_ui.py` (Flask app factory, classes, page routes), `server/web_api.py` (REST API blueprint — all `/api/*` routes), `data/config.yaml` (playlists + settings), `data/cookies.txt` (auth), `data/music-porter.db` (SQLite — tracks, audit, tasks, sync, EQ, scheduling).

**Directories:** `library/source/gamdl/<playlist>/` (M4A downloads, nested by artist/album), `library/audio/` (all MPs as `<uuid>.mp3`, flat), `library/artwork/` (all cover art as `<uuid>.ext`, flat), `server/templates/` (Jinja2), `logs/`, `data/` (config, cookies, DB), `SRS/`, `clients/ios/` (companion app — see `clients/ios/CLAUDE.md`), `clients/sync-client/` (desktop sync client — see `clients/sync-client/CLAUDE.md`), `docker/` (Docker infrastructure).

## Web Dashboard & Server

### Overview

The web dashboard (`web_ui.py`) provides a browser-based interface for all music-porter operations. Built with Flask and Bootstrap 5.3.3 (dark theme), it uses Server-Sent Events (SSE) for real-time progress streaming and a background task model that runs one major operation at a time.

### Launch

```bash
./music-porter                                  # Start server (0.0.0.0:5555, auth + Bonjour)
./music-porter server --host 127.0.0.1          # Local-only binding
./music-porter server --port 8080               # Custom port
./music-porter server --show-api-key            # Display the API key on startup
./music-porter server --behind-proxy            # Trust X-Forwarded-* headers (behind nginx, etc.)
./music-porter server --behind-proxy --proxy-count 2  # Two proxy hops
./music-porter server --no-bonjour              # Disable mDNS advertisement
```

### Pages & Templates

11 Jinja2 templates in `server/templates/` using Bootstrap 5.3.3 dark theme (CDN from jsDelivr). `base.html` provides shared layout (sidebar, log panel, SSE handler). Pages: `/login`, `/` (dashboard), `/playlists`, `/pipeline`, `/convert`, `/sync`, `/settings`, `/operations`, `/audit`, `/about`.

### API Endpoints (~60)

All API routes are defined in `server/web_api.py` as a Flask Blueprint.

- **Auth:** `POST /api/auth/validate`, `GET /api/server-info`
- **Status:** `GET /api/status`, `/api/summary`, `/api/library-stats`
- **Cookies:** `GET /api/cookies/browsers`, `POST /api/cookies/refresh`
- **Playlists CRUD:** `GET|POST /api/playlists`, `PUT|DELETE /api/playlists/<key>`, `POST /api/playlists/<key>/delete-data`
- **Settings:** `GET|POST /api/settings`
- **Config:** `GET /api/config/verify`, `POST /api/config/reset`
- **Scheduler:** `GET /api/scheduler/status`, `POST /api/scheduler/config`, `POST /api/scheduler/run-now`
- **Directories:** `GET /api/directories/music`, `GET /api/directories/export`
- **Operations:** `POST /api/pipeline/run`, `/api/convert/run`, `/api/convert/batch`, `/api/library/backfill-metadata`
- **Files:** `GET /api/files/<key>` (list with `display_filename`), `/<key>/<filename>` (download with Content-Disposition), `/<key>/<filename>/artwork`, `/<key>/sync-status`, `/<key>/download-all` (ZIP), `POST /api/files/download-zip`
- **Sync:** `GET /api/sync/destinations`, `POST /api/sync/destinations`, `DELETE /api/sync/destinations/<name>`, `PUT /api/sync/destinations/<name>/link`, `POST /api/sync/destinations/<name>/reset`, `POST /api/sync/destinations/resolve`, `POST /api/sync/run`, `GET /api/sync/status`, `GET /api/sync/status/<dest_name>`, `POST /api/sync/client-record`
- **EQ:** `GET /api/eq`, `POST /api/eq`, `DELETE /api/eq`, `GET /api/eq/resolve`, `GET /api/eq/effects`
- **Tasks:** `GET /api/tasks`, `/api/tasks/<id>`, `POST /api/tasks/<id>/cancel`, `GET /api/stream/<id>` (SSE), `GET /api/tasks/history`, `GET /api/tasks/stats`, `POST /api/tasks/clear`
- **Pairing:** `GET /api/pairing-qr`, `GET /api/pairing-info`
- **Audit:** `GET /api/audit`, `GET /api/audit/stats`, `POST /api/audit/clear`
- **About:** `GET /api/about`

### Architecture

**Key classes in `web_ui.py`:** `WebLogger` (routes to SSE queue), `WebDisplayHandler` (SSE progress), `WebPromptHandler` (auto-confirm for web), `TaskState` (dataclass), `TaskManager` (one-at-a-time with `RLock`), `AppContext` (shared state for routes).

**AppContext pattern:** Shared state (`task_manager`, `audit_logger`, `api_key`, `project_root`, `track_db`, `sync_tracker`) stored in `app.config['CTX']`. API routes in `web_api.py` access it via `current_app.config['CTX']`. Helper methods: `detect_source()`, `client_info()`, `make_logger()`, `make_display_handler()`, `get_config()`, `get_output_profile()`, `get_server_name()`, `safe_dir()`.

**Background task model:** POST submits task -> `task_manager.submit()` -> returns `task_id` (409 if busy). Background thread runs with `WebLogger`. Frontend subscribes to `GET /api/stream/<task_id>` for SSE events (`log`/`progress`/`heartbeat`/`done`).

**Security:** `safe_dir()` validates directories within project root. Server uses Bearer token auth (`Authorization: Bearer <api_key>`). API key generated via `secrets.token_urlsafe(32)`, persisted in `config.yaml`.

### Limitations

- One background task at a time (HTTP 409 if busy)
- No custom VBR quality via web UI (only named presets)
- Proxy headers (`X-Forwarded-For`, etc.) are only trusted when `--behind-proxy` is set

## iOS Companion App

See `clients/ios/CLAUDE.md` for full iOS companion app documentation (architecture, models, services, views, Bonjour, pairing flow).

**Quick reference:** Native SwiftUI app (iOS 17+) connecting to `./music-porter server` over local network. Requires API key auth, Bonjour discovery, and file serving endpoints. The iOS app has its own independent version (`MusicPorterApp.appVersion`) — `/merge-dev-to-main` automatically detects `clients/ios/` changes and prompts for an iOS version bump.

## Sync Client (Desktop)

See `clients/sync-client/CLAUDE.md` for full sync client documentation (architecture, core library, CLI, Electron GUI).

**Quick reference:** Cross-platform standalone sync client (`clients/sync-client/` subdirectory) connecting to `./music-porter server` via API. Provides both a CLI tool (`mporter-sync`) and an Electron desktop app. Built with TypeScript as an npm workspaces monorepo (`@mporter/core`, `@mporter/cli`, `@mporter/gui`). The sync client has its own independent version (`VERSION` in `clients/sync-client/packages/core/src/constants.ts`) — `/merge-dev-to-main` automatically detects `clients/sync-client/` changes and prompts for a sync client version bump.

## Shared Cache Model

Both the iOS companion app and the sync client implement the same cache model for offline audio file caching and API response metadata. JSON file formats, schema versions, and cache invalidation behavior must stay in sync between the two implementations.

- **iOS implementation:** `clients/ios/MusicPorter/MusicPorter/Services/Cache/` (Swift actors)
- **Sync client implementation:** `clients/sync-client/packages/core/src/cache/` (TypeScript classes)
- **JSON formats:** `metadata-cache.json` (camelCase), `cache-index.json` (snake\_case)
- **Schema version:** `metadataCacheVersion = 1` (shared constant)

When modifying cache logic, types, or file formats in either implementation, update the other to match.

## Important Implementation Notes

### File Naming

- **Library files:** `<uuid>.mp3` (UUID-named, flat in `library/audio/`)
- **M4A sources:** nested directory structure in `library/source/gamdl/<playlist>/`
- **API responses:** include both `filename` (UUID on disk) and `display_filename` (human-readable `Artist - Title.mp3`)
- **Downloads/sync:** Content-Disposition header and sync client use `display_filename` for output
- **ZIP archives:** entries use human-readable names from TrackDB
- **Duplicate detection:** TrackDB lookup by `source_m4a_path`, not file-exists check

### Cookie Management (CookieManager class)

Uses `MozillaCookieJar` for validation, Selenium for auto-refresh (headless first, visible fallback). Detects default browser per platform. Creates `.backup` before overwriting. Key methods: `validate()`, `auto_refresh()`, `_extract_with_selenium()`, `_detect_default_browser()`.

### Error Handling

Continues on individual file errors (batch processing). Logs to timestamped files. Cookie errors fail fast. Summary stats at completion.

### FFmpeg Integration

Uses `ffmpeg-python` wrapper (requires system `ffmpeg` binary). Catches `ffmpeg.Error`, logs details, continues batch. Uses `quiet=True`.

## Configuration

### Data Directory (`data/`)

All persistent state lives in `data/`: `config.yaml`, `cookies.txt`, `music-porter.db` (SQLite). Auto-created on first run; legacy files migrated from project root via `migrate_data_dir()`.

### config.yaml

YAML file with `settings` (output\_type, workers, server\_name, quality\_preset) only. Profiles are in `data/profiles.yaml` (git-tracked). Playlists and destinations are stored in the SQLite database (moved from config in schema v4). Path: `data/config.yaml`. Auto-created if missing.

### profiles.yaml

YAML file at `data/profiles.yaml` (git-tracked via `.gitignore` exception). Profiles nested under `output` key. Read-only at runtime — edit manually to add or customise profiles. Loaded by `ConfigManager._load_profiles()` at startup. Falls back to built-in `DEFAULT_OUTPUT_PROFILES` if file is missing.

### Schema Versioning

All three persistent stores have explicit version tracking with sequential migrations:

- **Config:** `CONFIG_SCHEMA_VERSION` constant in `server/core/constants.py`. Version stored as `schema_version` key in `config.yaml`. Migrations run in `migrate_config_schema()` (`server/core/migrations.py`).
- **Profiles:** `PROFILES_SCHEMA_VERSION` constant in `server/core/constants.py`. Version stored as `schema_version` key in `data/profiles.yaml`. Migrations run in `migrate_profiles_schema()` (`server/core/migrations.py`).
- **Database:** `DB_SCHEMA_VERSION` constant in `server/core/constants.py`. Version stored as SQLite `PRAGMA user_version`. Migrations run in `migrate_db_schema()` (`server/core/migrations.py`).

All three functions are called at startup before any DB class or ConfigManager is instantiated (in `music-porter` main() and `web_ui.py` module level).

**When changing config.yaml structure or DB tables/columns:**

1. Increment the relevant constant (`CONFIG_SCHEMA_VERSION` or `DB_SCHEMA_VERSION`)
2. Add a new `if current < N:` migration case in the corresponding function
3. Migrations must be idempotent and sequential (version 0→1→2→…)
4. **Never modify existing version blocks** — each `if current < N:` block sets the version to exactly N (not `DB_SCHEMA_VERSION`/`CONFIG_SCHEMA_VERSION`). New changes go exclusively in a new `if current < N:` block. Fresh installs run through all migrations sequentially (0→1→2→…N). This applies to both DB and config migrations.

**Current DB schema (version 8) — 9 tables:**

- `audit_entries`: id, timestamp, operation, description, params, status, duration\_s, source
- `task_history`: id, operation, description, status, result, error, started\_at, finished\_at, source
- `sync_keys`: key\_name (internal UUID), last\_sync\_at, created\_at
- `sync_files`: id, sync\_key (internal UUID FK → sync\_keys), file\_path, playlist, synced\_at
- `eq_presets`: id, profile, playlist, loudnorm, bass\_boost, treble\_boost, compressor, updated\_at (UNIQUE profile+playlist)
- `scheduled_jobs`: job\_name (PK), next\_run\_time, last\_run\_time, last\_run\_status, last\_run\_error, on\_missed, updated\_at
- `tracks`: uuid (PK), playlist, file\_path, title, artist, album, cover\_art\_path, cover\_art\_hash, duration\_s, file\_size\_bytes, source\_m4a\_path, genre, track\_number, track\_total, disc\_number, disc\_total, year, composer, album\_artist, bpm, comment, compilation, grouping, lyrics, copyright, created\_at, updated\_at (indexes: playlist, file\_path, source\_m4a\_path)
- `playlists`: key (PK), url, name, created\_at, updated\_at
- `destinations`: name (PK), path, sync\_key (internal UUID, NOT NULL), created\_at, updated\_at (index: sync\_key). Multiple destinations sharing the same sync\_key form a linked group with shared tracking.

**Current config schema (version 5) — top-level keys:**

- `schema_version` (integer)
- `settings` (output\_type, workers, server\_name, quality\_preset)

**Current profiles schema (version 1) — `data/profiles.yaml` top-level keys:**

- `schema_version` (integer)
- `output` (profile name → description, id3\_title, id3\_artist, id3\_album, id3\_genre, id3\_extra, id3\_versions, artwork\_size, filename, directory, usb\_dir)

### USB Drive Exclusions

Constant `EXCLUDED_USB_VOLUMES` in `server/core/constants.py` — platform-specific (macOS: `"Macintosh HD"`, `"Macintosh HD - Data"`; Windows: `"C:"`; Linux: `"boot"`, `"root"`).

## Implementation Details

### Key Classes (split across `server/core/` modules)

Organized by module and concern:

**`constants.py`:** VERSION, all DEFAULT\_\* constants, EQ\_EFFECTS, QUALITY\_PRESETS, M4A\_TAG\_\*, schema versions, platform flags, `get_os_display_name()`

**`models.py`:** `EQConfig`, `OutputProfile`, `SyncDestination`, `_DisplayProgress`; result dataclasses: `ConversionResult`, `DownloadResult`, `SyncResult`, `SyncStatusResult`, `DeleteResult`, `PipelineResult`, `AggregateResult`, `AggregateStatistics`, `DependencyCheckResult`

**`protocols.py`:** `UserPromptHandler`, `DisplayHandler` (Protocol classes)

**`logging.py`:** `Logger`, `ProgressBar`, `MigrationEvent`

**`database.py`:** `AuditLogger`, `TaskHistoryDB`, `ScheduledJobsDB`, `SyncTracker`, `TrackDB`, `EQConfigManager`, `PlaylistDB`

**`config.py`:** `ConfigManager`, `DependencyChecker`, `NonInteractivePromptHandler`, `NullDisplayHandler`, `SafeTemplateDict`, `load_output_profiles()`, `validate_config()`

**`migrations.py`:** `migrate_db_schema()`, `migrate_config_schema()`, `migrate_profiles_schema()`, `migrate_data_dir()`, `flush_migration_events()`

**`utils.py`:** `sanitize_filename()`, `deduplicate_filenames()`, `apply_template()`, `display_name()`, `read_m4a_tags()`, `read_m4a_cover_art()`, `resize_cover_art_bytes()`, path helpers, `prune_*()`, `_init_third_party()`

**`tagging.py`:** `TagApplicator`

**`converter.py`:** `ConversionStatistics`, `Converter`

**`downloader.py`:** `DownloadStatistics`, `Downloader`, `CookieStatus`, `CookieManager`

**`sync.py`:** `USBSyncStatistics`, `SyncManager`, `detect_removed_tracks()`, `cleanup_removed_tracks()`

**`pipeline.py`:** `MusicLibraryStats`, `SummaryManager`, `DataManager`, `PipelineStatistics`, `PlaylistResult`, `PipelineOrchestrator`, `backfill_track_metadata()`, `audit_library()`

### TrackDB

- SQLite-backed metadata for every MP3 in the library (`tracks` table)
- Thread-safe writes via `Lock`, lockless reads via WAL mode
- Key read methods: `get_track(uuid)`, `get_track_by_path(file_path)`, `get_track_by_source_m4a(source_m4a_path)`, `get_tracks_by_playlist(playlist)`, `get_all_playlists()`, `get_playlist_stats()`, `get_track_count()`, `get_all_tracks()`
- Key write methods: `insert_track(...)`, `update_track_metadata(...)`, `delete_track(uuid)`, `delete_tracks_by_playlist(playlist)`

### TagApplicator

- Reads track metadata from TrackDB, builds profile-specific ID3 tags
- Template variables: `{title}`, `{artist}`, `{album}`, `{genre}`, `{track_number}`, `{track_total}`, `{disc_number}`, `{disc_total}`, `{year}`, `{composer}`, `{album_artist}`, `{bpm}`, `{comment}`, `{compilation}`, `{grouping}`, `{lyrics}`, `{copyright}`, `{playlist}`, `{playlist_key}` — resolved from track metadata
- Supports both streaming (HTTP) and file-based (physical sync) tag application
- `_build_id3_tags()` constructs the full ID3 tag set with profile-configured frames (TIT2, TPE1, TALB, APIC, etc.)

### Library Directory

- Paths: `library/source/gamdl/<playlist>/` for M4A downloads, `library/audio/` for MP3s (flat), `library/artwork/` for cover art (flat)
- Helpers: `get_library_dir()` returns `"library"`, `get_source_dir(playlist_key)` returns `"library/source/gamdl/<playlist>"`, `get_audio_dir()` returns `"library/audio"`, `get_artwork_dir()` returns `"library/artwork"`
- Constants: `SOURCE_SUBDIR = "source"`, `AUDIO_SUBDIR = "audio"`, `ARTWORK_SUBDIR = "artwork"`, `DEFAULT_IMPORTER = "gamdl"`
- Files: `<uuid>.mp3` (flat in audio/, no subdirectories)

### Cover Art

- Extracted from M4A source during conversion (in `Converter._extract_cover_art_to_disk()`)
- Stored as `library/artwork/<uuid>.ext` (jpg or png)
- SHA-256 hash (truncated to 16 chars) stored in TrackDB `cover_art_hash` column
- Served via `GET /api/files/<playlist>/<filename>/artwork`

### Data Management (DataManager)

- Deletes source M4A (`music/<key>/`) and/or library MP3 (`library/<key>/`) directories
- Counts files and sizes before deletion for confirmation prompt and reporting
- Uses `confirm_destructive()` from prompt handler (web auto-confirms)
- Optional `remove_config` flag to also remove the playlist from `config.yaml`
- Returns `DeleteResult` dataclass with stats (files_deleted, bytes_freed, etc.)

### ConfigManager

- Reads/writes `config.yaml` using PyYAML; auto-creates if missing
- Key methods: `get_setting()`, `update_setting()`, `_save()`, `_create_default()`
- IMPORT_MAP includes `'PyYAML': 'yaml'` for dependency checking

### Audit Trail (AuditLogger)

- SQLite-backed persistent audit log in `data/music-porter.db`
- Thread-safe writes via `RLock`, lockless reads via WAL mode
- Schema: `audit_entries` table with `id`, `timestamp`, `operation`, `description`, `params` (JSON), `status`, `duration_s`, `source`
- Source field: `'web'`, `'ios'`, or `'api'` — set by caller
- Business classes accept `audit_logger` and `audit_source` params — audit logging is wired at the call site, not inside the class
- Web dashboard: `/audit` page with filtering, pagination, stats cards, and clear tool

### Task History (TaskHistoryDB)

- SQLite-backed persistent task history in `data/music-porter.db` (`task_history` table)
- Thread-safe writes via `Lock`, lockless reads via WAL mode (same pattern as `AuditLogger`)
- Startup recovery: marks stale `running`/`pending` rows as `failed` on init
- Wired into `TaskManager` — all background tasks are persisted automatically
- Web dashboard: `/operations` page with stats cards, filters, pagination, active task SSE viewer, and clear tool

## Additional Resources

- **README.md** - Project overview, quick start guide, and future features roadmap
- **docs/COOKIE-MANAGEMENT-GUIDE.md** - Cookie validation, auto-refresh, and troubleshooting
- **docs/IOS-COMPANION-GUIDE.md** - iOS companion app setup, pairing, and usage guide
- **docs/DB_SCHEMA.md** - SQLite database schema reference (tables, columns, indexes, migrations)
- **docs/SERVER_API.md** - REST API endpoint reference (~60 endpoints)

### Keeping Docs in Sync

- When modifying the database schema, update `docs/DB_SCHEMA.md` to reflect the current state.
- When modifying API endpoints in `web_api.py`, update `docs/SERVER_API.md` and `docs/openapi.yaml` to reflect the current state.
- When planning implementation work, consult `docs/DB_SCHEMA.md` and `docs/SERVER_API.md` as references for the current database schema and API surface.
