# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## User Preferences

### Git Commit Preferences

- **Never include** Co-Authored-By lines in commit messages
- Commits should be authored solely by the user

### README Future Features

- When implementing a future feature from the README list, **strikethrough** the item (~~text~~) with a note like "*(implemented in vX.Y.Z)*" instead of removing it
- Keep the original numbering intact

## Requirements Handling

### Workflow

- Requirements (SRS) **must** be written and reviewed **before** implementation begins
- When asked to "work on requirements", **only** produce the SRS document — do not plan or begin implementation
- Implementation starts only after explicit user instruction
- These are separate phases — never combine them
- **Always use a feature branch** when adding or changing SRS requirements — never commit SRS changes directly to main or dev

### SRS Document Format

- Tables with columns: ID, Version, Tested, Requirement
- New requirements start with `[ ]` in the Tested column — mark `[x]` when implemented and tested
- **IDs must be globally unique** across all SRS documents in `SRS/` — use the entry's sequential number as the first digit (e.g., entry 8 uses IDs `8.1.1`, `8.2.1`, etc.)
- When creating a new SRS, check existing files in `SRS/` for the highest entry number and use the next one
- Edge cases are the last subsection under Requirements
- Store individual SRS files in the `SRS/` directory
- Organized by **user feature** (not by internal class or module)
- Each entry maps to a user-facing capability, aligned with CLI subcommands where applicable
- Cross-cutting concerns (logging, progress, CLI flags) go in the "CLI & Runtime" entry
- Related features may be merged (e.g., cookie management is part of "Download & Authentication")
- Requirements must be detailed enough to **reimplement the software** from the SRS alone

### During Implementation

- Mark Tested cells `[x]` as each requirement is completed
- Add new SRS items if requirements are discovered during design or implementation
- Update the SRS whenever the user requests changes — keep in sync with the current implementation

### Merge Gate

- **All** Tested cells must be `[x]` before merging to main — `/merge-to-main` enforces this
- SRS validation is **not** enforced at `/merge-to-dev` time — it is deferred to `/merge-to-main`
- SRS files remain in `SRS/` permanently — they are **not** archived or deleted after merge

## Project Overview

RideCommandMP3Export is a music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format, and optionally copies them to USB drives. The system preserves original tag metadata while allowing customization for device compatibility.

## Architecture

### Core Workflow Pipeline

The system follows an integrated pipeline:

1. **Download** → Downloads Apple Music playlists as M4A files via gamdl
2. **Convert** → Converts M4A to MP3 using ffmpeg (libmp3lame, default: lossless 320kbps CBR)
3. **Tag** → Updates and preserves tags with TXXX frame protection
4. **Sync** → Optionally syncs to destinations (USB drives, saved paths, custom paths)

### Key Scripts

**music-porter** (python) - **RECOMMENDED**
- Unified tool combining all functionality in a single command
- Professional subcommand architecture: `pipeline`, `download`, `convert`, `tag`, `restore`, `reset`, `delete`, `sync`, `cover-art`, `summary`, `list`, `config`, `web`, `server`, `about`, `tasks`
- Interactive menu for easy operation
- Comprehensive error handling and statistics
- Full pipeline orchestration (download → convert → tag → USB)
- Modular design with 21 classes
- 4,270 lines of production-ready Python code
- See `MUSIC-PORTER-GUIDE.md` for complete documentation

**do-it-all** and **ride-command-mp3-export** are deprecated wrappers — both call `music-porter` internally.

### Tag Preservation System

The codebase uses a "hard gate" protection system for original metadata:

- Original tags are stored in TXXX (user-defined text) ID3 frames
- Frame names: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`, `OriginalCoverArtHash`
- Once written, these frames are NEVER overwritten (enforced via `_txxx_exists()` checks)
- This ensures true originals are preserved even across multiple script runs
- Restoration is always possible via `--restore-*` flags

### ID3 Tag Standards

- Default output: ID3v2.3 (older device compatibility)
- ID3v1 tags are stripped by default (clean metadata)
- Duplicate frames are automatically removed
- Override with `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates`

## Common Commands

### Quick Start

```bash
# Interactive menu (easiest way to start)
./music-porter

# Full pipeline for one playlist
./music-porter pipeline --playlist "Pop_Workout"

# Process all playlists automatically
./music-porter pipeline --auto

# Get help
./music-porter --help
./music-porter [command] --help
```

## MP3 Quality Presets

Presets via `--preset` flag: `lossless` (default, CBR 320kbps), `high` (VBR q2, ~190-250kbps), `medium` (VBR q4, ~165-210kbps), `low` (VBR q6, ~115-150kbps), `custom` (requires `--quality 0-9`).

### Subcommands Reference

```bash
# Pipeline (download → convert → tag)
./music-porter pipeline --playlist "Pop_Workout"    # Single playlist
./music-porter pipeline --playlist 1                # By number
./music-porter pipeline --url "https://..."         # Direct URL
./music-porter pipeline --auto                      # All playlists
./music-porter pipeline --playlist X --preset high  # Quality preset
./music-porter pipeline --playlist X --sync-dest nas-backup  # Sync to saved destination

# Download
./music-porter download --playlist "Pop_Workout"
./music-porter download --url "https://music.apple.com/..."

# Convert (M4A → MP3)
./music-porter convert music/Pop_Workout                          # Default lossless
./music-porter convert music/Pop_Workout --preset high            # VBR preset
./music-porter convert music/Pop_Workout --preset custom --quality 0  # Custom VBR
./music-porter convert music/Pop_Workout --force                  # Re-convert existing

# Tags
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout" --artist "Various"
./music-porter restore export/ride-command/Pop_Workout --all      # Restore originals
./music-porter reset music/Pop_Workout export/ride-command/Pop_Workout  # Reset from source

# Delete playlist data
./music-porter delete Pop_Workout                    # Delete both source + export
./music-porter delete Pop_Workout --source-only      # Only source M4A files
./music-porter delete Pop_Workout --export-only      # Only export MP3 files
./music-porter delete Pop_Workout --remove-config    # Also remove from config.yaml

# Sync (destinations)
./music-porter sync                                          # Interactive destination picker
./music-porter sync --dest nas-backup                        # Sync to saved destination
./music-porter sync --dest /path/to/folder                   # Sync to path
./music-porter sync --list-destinations                      # List saved destinations
./music-porter sync --add-dest NAME PATH                     # Save a destination
./music-porter sync --remove-dest NAME                       # Remove a saved destination
./music-porter sync --rename-dest OLD NEW                    # Rename a saved destination
./music-porter sync --status                                 # Show sync tracking

# Summary
./music-porter summary              # Default (balanced)
./music-porter summary --quick      # Aggregate only
./music-porter summary --detailed   # Extended info

# List
./music-porter list unconverted                          # All playlists
./music-porter list unconverted --playlist "Pop_Workout"  # Single playlist
./music-porter list diff                                  # All playlists
./music-porter list diff --playlist 1                     # By number

# Cover Art
./music-porter cover-art embed export/ride-command/Pop_Workout    # From M4A sources
./music-porter cover-art extract export/ride-command/Pop_Workout  # To image files
./music-porter cover-art update export/ride-command/Pop_Workout --image artwork.jpg
./music-porter cover-art strip export/ride-command/Pop_Workout    # Remove APIC frames

# Config
./music-porter config                  # Show config format reference
./music-porter config verify           # Validate config.yaml integrity
./music-porter config reset            # Reset to defaults (backs up first)
./music-porter config reset --force    # Reset without confirmation

# Tasks (view persistent task history)
./music-porter tasks                           # Recent task history (last 20)
./music-porter tasks --stats                   # Aggregate statistics
./music-porter tasks --limit 50                # Show more entries
./music-porter tasks --status failed           # Filter by status
./music-porter tasks --operation pipeline      # Filter by operation
```

### Global Flags

- `--dry-run` — Preview changes without modifying files
- `--verbose` — Detailed output for debugging
- `--version` — Show version
- Combine: `./music-porter --dry-run --verbose convert music/Pop_Workout`

### Output Type Profiles

Use `--output-type` to select. CLI flags override profile defaults.

| Profile | ID3 | Artwork | Quality | Album Tag | Artist Tag |
|---------|-----|---------|---------|-----------|------------|
| `ride-command` (default) | v2.3 | 100px | lossless | playlist name | "Various" |
| `basic` | v2.4 | original | lossless | original | original |

Profile fields: `artwork_size` (px, 0=original, -1=strip), `quality_preset`, `pipeline_album` ("playlist\_name"/"original"), `pipeline_artist` ("various"/"original").

### Legacy Commands (Deprecated)

`do-it-all` and `ride-command-mp3-export` still work as wrappers but show deprecation warnings. Replace with `music-porter`.

## Development Setup

### Platform Support

Supports **macOS**, **Linux**, and **Windows** (auto-detected at startup). Platform-specific USB detection, ejection, and ffmpeg installation.

### Prerequisites & Setup

- Python 3.8+, ffmpeg (system binary), and pip dependencies in venv
- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Pip packages: gamdl, mutagen, ffmpeg-python, selenium, webdriver-manager, Pillow, PyYAML
- `config.yaml` auto-created on first run

### Testing

Use `--dry-run` to preview, `--verbose` to inspect tag transformations. Test tag preservation by running updates multiple times.

### Linting

Uses **Ruff** (Python), **PyMarkdown** (Markdown), **djLint** (Jinja2/HTML). Config in `pyproject.toml`. Install: `source .venv/bin/activate && pip install -r requirements-dev.txt`.

```bash
source .venv/bin/activate
ruff check .                                                 # Python (lint)
ruff check --fix .                                           # Python (auto-fix)
pymarkdown scan -r --respect-gitignore .                     # Markdown
djlint templates/ --lint                                     # Templates (lint)
djlint templates/ --reformat                                 # Templates (auto-fix)
```

All three must pass clean before merging to main. Linting is recommended but not enforced at `/merge-to-dev` time.

### Branch Workflow (3-Tier)

The project uses a 3-tier branch model: **feature -> dev -> main**.

- **`main`** = stable releases only. Every commit on main is tagged with a version. Never commit directly to main.
- **`dev`** = persistent integration branch. VERSION always has a `-dev` suffix (e.g., `"2.31.0-dev"`). Multiple features are tested together here before release.
- **Feature branches** = short-lived, for individual features/fixes. Branch from `dev` (not main).

**Branch naming:** `feature/`, `bugfix/`, `refactor/`, `docs/` prefix + lowercase-hyphenated description (2-4 words). Examples: `feature/playlist-search`, `bugfix/tag-double-prefix`.

**Creating:** Start from dev, create branch, set `VERSION = "X.Y.Z-branch-name"` in `porter_core.py` line 50 (base version from dev, replacing `-dev` with `-branch-name`) as first commit.

**Planning mode:** When planning mode is used from the `dev` branch, a feature branch must always be created before implementation begins.

**Working:** Keep branch version throughout development. For long-lived branches, rebase on `origin/dev` periodically.

**Small fixes:** Single-commit fixes, docs, and config changes can go directly to dev (never directly to main).

**Merging to dev:** Use `/merge-to-dev` skill — fast and fully automatic, no user prompts, no SRS validation, no version bump.

**Merging to main:** Use `/merge-to-main` skill (must be on dev) — full validation: SRS gate, version bump, tagging, release notes, sets next `-dev` version, offers branch cleanup, pushes both main and dev.

**Pre-merge checklist (for main):** Clean working tree, tested with `--dry-run`/`--verbose`, no debug code, up to date with remote, README future features updated, all SRS `[x]`.

### Version Management

Version defined in `porter_core.py` line 50. Uses semantic versioning (MAJOR.MINOR.PATCH).

**On `dev` branch:** `VERSION = "X.Y.Z-dev+<hash>"` (e.g., `"2.31.0-dev+a425c6c"`). The `-dev` suffix is always present on dev, with `+<short-hash>` SemVer build metadata appended by merge-to-dev.

**On feature branches:** `VERSION = "X.Y.Z-branch-name"` (e.g., `"2.31.0-cookie-management"`). Base version comes from dev (strip the `-dev+hash` suffix), replacing with `-branch-name`. Set as first commit.

**merge-to-dev:** Restores the `-dev` suffix and appends `+<short-hash>` of the merge commit (SemVer build metadata).

**merge-to-main:** Remove `-dev+hash` suffix, bump version (PATCH/MINOR/MAJOR), create git tag (`git tag vX.Y.Z`). After tagging, sync dev with main and set the next `X.Y.Z-dev` version on dev (no hash — the next merge-to-dev adds it).

**Release notes:** When bumping the version, prepend a new entry to the top of `release-notes.txt` (project root) summarizing the changes in that release. Format: `Version X.Y.Z (YYYY-MM-DD):` header followed by bullet points (`• description`). This is displayed in the web About page and `./music-porter about` CLI command. Generate the release notes by reviewing all commits since the previous version tag.

**Display:** Shown in startup banner, `--version` flag, and log files.

### Common Gotchas

**Cookies:** Requires `cookies.txt` with Apple Music session cookies. Auto-validates at startup; expired cookies trigger interactive refresh via Selenium (Chrome/Firefox/Safari/Edge). Backup at `cookies.txt.backup`. Flags: `--auto-refresh-cookies`, `--skip-cookie-validation`. See `COOKIE-MANAGEMENT-GUIDE.md`.

**Virtual Environment:** Must activate before running: `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\activate` (Windows).

**Temp Directories:** `gamdl_temp_*` directories safe to delete after downloads.

**USB Detection:** Auto-detects by platform — macOS: `/Volumes/`, Linux: `/media/$USER/` + `/mnt/`, Windows: drive letters. Eject: automatic on macOS/Linux, manual on Windows.

## Directory Structure

**Key files:** `music-porter` (CLI), `porter_core.py` (business logic), `web_ui.py` (web dashboard — app factory, classes, page routes), `web_api.py` (REST API blueprint — all `/api/*` routes), `config.yaml` (playlists + settings), `cookies.txt` (auth), `data/music-porter.db` (SQLite audit trail + task history).

**Directories:** `music/` (M4A downloads, nested by artist/album), `export/<profile>/<playlist>/` (MP3s, flat "Artist - Title.mp3"), `templates/` (Jinja2), `logs/`, `data/` (config, cookies, audit DB), `SRS/`, `ios/` (companion app — see `ios/CLAUDE.md`).

## Web Dashboard

### Overview

The web dashboard (`web_ui.py`) provides a browser-based interface with full feature parity to the CLI. Built with Flask and Bootstrap 5.3.3 (dark theme), it uses Server-Sent Events (SSE) for real-time progress streaming and a background task model that runs one major operation at a time.

### Launch

```bash
./music-porter web                              # Local browser UI (127.0.0.1:5555, no auth)
./music-porter web --host 0.0.0.0 --port 8080   # Network access
./music-porter server                            # API server (0.0.0.0, auth + Bonjour, for iOS)
./music-porter server --show-api-key             # Display API key on startup
./music-porter server --behind-proxy             # Trust X-Forwarded-* headers (behind nginx, etc.)
./music-porter server --behind-proxy --proxy-count 2  # Two proxy hops
```

**`web` vs `server`:** `web` is local-only, no auth. `server` enables API key auth, Bonjour/mDNS, QR pairing, and iOS app support.

### Pages & Templates

12 Jinja2 templates in `templates/` using Bootstrap 5.3.3 dark theme (CDN from jsDelivr). `base.html` provides shared layout (sidebar, log panel, SSE handler). Pages: `/` (dashboard), `/playlists`, `/pipeline`, `/convert`, `/tags`, `/cover-art`, `/sync`, `/settings`, `/operations`, `/audit`, `/about`.

### API Endpoints (~42)

All API routes are defined in `web_api.py` as a Flask Blueprint.

- **Status:** `GET /api/status`, `/api/summary`, `/api/library-stats`
- **List:** `GET /api/list/unconverted`, `GET /api/list/diff`
- **Auth (server only):** `POST /api/auth/validate`, `GET /api/server-info`
- **Cookies:** `GET /api/cookies/browsers`, `POST /api/cookies/refresh`
- **Playlists CRUD:** `GET|POST /api/playlists`, `PUT|DELETE /api/playlists/<key>`, `POST /api/playlists/<key>/delete-data`
- **Settings:** `GET|POST /api/settings`
- **Config:** `GET /api/config/verify`, `POST /api/config/reset`
- **Directories:** `GET /api/directories/music`, `GET /api/directories/export`
- **Operations:** `POST /api/pipeline/run`, `/api/convert/run`, `/api/convert/batch`, `/api/tags/update`, `/api/tags/restore`, `/api/tags/reset`, `/api/cover-art/<action>`
- **Files:** `GET /api/files/<key>`, `/<key>/<filename>`, `/<key>/<filename>/artwork`, `/<key>/download-all`
- **Sync:** `GET /api/sync/destinations`, `POST /api/sync/destinations`, `DELETE /api/sync/destinations/<name>`, `POST /api/sync/destinations/<name>/rename`, `POST /api/sync/run`, `GET /api/sync/status`, `GET /api/sync/status/<key>`, `GET|DELETE /api/sync/keys/<key>`, `DELETE /api/sync/keys/<key>/playlists/<playlist>`, `POST /api/sync/keys/<key>/prune`
- **Tasks:** `GET /api/tasks`, `/api/tasks/<id>`, `POST /api/tasks/<id>/cancel`, `GET /api/stream/<id>` (SSE), `GET /api/tasks/history`, `GET /api/tasks/stats`, `POST /api/tasks/clear`
- **iOS Pairing:** `GET /api/pairing-qr`, `GET /api/pairing-info`
- **Audit:** `GET /api/audit`, `GET /api/audit/stats`, `POST /api/audit/clear`
- **About:** `GET /api/about`

### Architecture

**Key classes in `web_ui.py`:** `WebLogger` (routes to SSE queue), `WebDisplayHandler` (SSE progress), `WebPromptHandler` (auto-confirm for web), `TaskState` (dataclass), `TaskManager` (one-at-a-time with `RLock`), `AppContext` (shared state for routes).

**AppContext pattern:** Shared state (`task_manager`, `audit_logger`, `api_key`, `project_root`) stored in `app.config['CTX']`. API routes in `web_api.py` access it via `current_app.config['CTX']`. Helper methods: `detect_source()`, `client_info()`, `make_logger()`, `make_display_handler()`, `get_config()`, `get_output_profile()`, `get_server_name()`, `safe_dir()`.

**Background task model:** POST submits task -> `task_manager.submit()` -> returns `task_id` (409 if busy). Background thread runs with `WebLogger`. Frontend subscribes to `GET /api/stream/<task_id>` for SSE events (`log`/`progress`/`heartbeat`/`done`).

**Security:** `safe_dir()` validates directories within project root. `web` has no auth; `server` uses Bearer token auth.

### Limitations

- One background task at a time (HTTP 409 if busy)
- No custom VBR quality via web UI (only named presets)
- `web` command has no auth — use `server` for network access
- Proxy headers (`X-Forwarded-For`, etc.) are only trusted when `--behind-proxy` is set

## iOS Companion App

See `ios/CLAUDE.md` for full iOS companion app documentation (architecture, models, services, views, Bonjour, pairing flow).

**Quick reference:** Native SwiftUI app (iOS 17+) connecting to `./music-porter server` over local network. Requires `server` command (not `web`) for API key auth, Bonjour discovery, and file serving endpoints.

## Important Implementation Notes

### CLI / Web Feature Parity

- Any feature added to the CLI **must** also be added to the Web dashboard (API endpoint + UI)
- Any feature added to the Web dashboard **must** also be added to the CLI
- Both interfaces should expose the same functionality — neither should have exclusive features

### TXXX Frame Handling

- Always iterate through `tags.values()` to check frame types with `isinstance(frame, TXXX)`
- Never rely on string key format like `TXXX:OriginalTitle` for existence checks
- Mutagen's key indexing can be inconsistent after save/reload cycles
- Use `_txxx_exists()` and `_get_txxx()` helper functions

### Title Format Handling

- Prevents double-compounding: strips existing "Artist - " prefix before reformatting
- Uses `_strip_artist_prefix()` to clean titles before applying new format
- Always builds titles from protected originals (OriginalArtist, OriginalTitle)

### File Naming

- Output files: "Artist - Title.mp3" (flat, no subdirectories)
- Invalid filename characters are stripped: `/\:*?"<>|`
- M4A sources remain in nested directory structure
- Existing MP3s are skipped unless `--force` is used

### Cookie Management (CookieManager class)

Uses `MozillaCookieJar` for validation, Selenium for auto-refresh (headless first, visible fallback). Detects default browser per platform. Creates `.backup` before overwriting. Key methods: `validate()`, `auto_refresh()`, `_extract_with_selenium()`, `_detect_default_browser()`.

### Error Handling

Continues on individual file errors (batch processing). Logs to timestamped files. Cookie errors fail fast. Summary stats at completion.

### FFmpeg Integration

Uses `ffmpeg-python` wrapper (requires system `ffmpeg` binary). Catches `ffmpeg.Error`, logs details, continues batch. Uses `quiet=True`.

## Configuration

### Data Directory (`data/`)

All persistent state lives in `data/`: `config.yaml`, `cookies.txt`, `music-porter.db` (audit). Auto-created on first run; legacy files migrated from project root via `migrate_data_dir()`.

### config.yaml

YAML file with `settings` (output\_type, workers), `playlists` (key, url, name), and `destinations` (name, path with `usb://` or `folder://` scheme) for saved sync destinations. Path: `data/config.yaml`. Auto-created if missing. **Precedence:** CLI flag > config.yaml > hardcoded constant.

### Schema Versioning

Both persistent stores have explicit version tracking with sequential migrations:

- **Config:** `CONFIG_SCHEMA_VERSION` constant in `porter_core.py` (~line 63). Version stored as `schema_version` key in `config.yaml`. Migrations run in `migrate_config_schema()`.
- **Database:** `DB_SCHEMA_VERSION` constant in `porter_core.py` (~line 64). Version stored as SQLite `PRAGMA user_version`. Migrations run in `migrate_db_schema()`.

Both functions are called at startup before any DB class or ConfigManager is instantiated (in `music-porter` main(), `web_ui.py` module level, and `_handle_tasks_command()`).

**When changing config.yaml structure or DB tables/columns:**

1. Increment the relevant constant (`CONFIG_SCHEMA_VERSION` or `DB_SCHEMA_VERSION`)
2. Add a new `if current < N:` migration case in the corresponding function
3. Migrations must be idempotent and sequential (version 0→1→2→…)

**Current DB schema (version 1) — 4 tables:**

- `audit_entries`: id, timestamp, operation, description, params, status, duration\_s, source
- `task_history`: id, operation, description, status, result, error, started\_at, finished\_at, source
- `sync_keys`: key\_name, last\_sync\_at, created\_at
- `sync_files`: id, sync\_key, file\_path, playlist, synced\_at (FK → sync\_keys)

**Current config schema (version 1) — top-level keys:**

- `schema_version` (integer)
- `settings` (output\_type, workers, server\_name)
- `output_types` (profile name → profile fields)
- `playlists` (list of key, url, name)
- `destinations` (list of name, path with scheme, optional sync\_key)

### USB Drive Exclusions

Constant `EXCLUDED_USB_VOLUMES` in `music-porter`: `["Macintosh HD", "Macintosh HD - Data"]`.

## Implementation Details

### Key Classes in `porter_core.py`

25 classes organized by concern: `Logger`, `PlaylistConfig`, `SyncDestination`, `ConfigManager`, `DependencyChecker`, `TagStatistics`, `TaggerManager`, `ConversionStatistics`, `Converter`, `Downloader`, `CookieStatus`, `CookieManager`, `SyncManager`, `PlaylistSummary`, `LibrarySummaryStatistics`, `SummaryManager`, `DataManager`, `PipelineStatistics`, `PipelineOrchestrator`, `InteractiveMenu`, `PlaylistResult`, `AggregateStatistics`, `CoverArtManager`, `AuditLogger`, `TaskHistoryDB`.

### ConfigManager

- Reads/writes `config.yaml` using PyYAML; auto-creates if missing
- Key methods: `get_setting()`, `update_setting()`, `_save()`, `_create_default()`
- Settings precedence: CLI flag > config.yaml > hardcoded constant
- IMPORT_MAP includes `'PyYAML': 'yaml'` for dependency checking

### Profile-Scoped Export Directories

- Paths scoped by profile: `export/<profile>/<playlist>/`
- Helper: `get_export_dir(profile_name, playlist_key=None)`

### Interactive Menu

- Numbered playlist selection (1-N) + letter actions: A (all), U (URL), C (sync to destination), S (summary), R (resize art), P (profile), D (delete data), X (exit)
- Returns to menu after each operation; saves new URLs to config

### Cover Art (CoverArtManager)

- Actions: `embed` (from M4A source), `extract` (to files), `update` (from image), `strip` (remove APIC)
- SHA-256 hash stored in `TXXX:OriginalCoverArtHash` with hard-gate protection
- `--no-cover-art` flag on `convert` and `pipeline` to skip embedding

### Data Management (DataManager)

- Deletes source M4A (`music/<key>/`) and/or export MP3 (`export/<profile>/<key>/`) directories
- Counts files and sizes before deletion for confirmation prompt and reporting
- Uses `confirm_destructive()` from prompt handler (CLI requires typing "yes", web auto-confirms)
- Optional `remove_config` flag to also remove the playlist from `config.yaml`
- Returns `DeleteResult` dataclass with stats (files_deleted, bytes_freed, etc.)

### Audit Trail (AuditLogger)

- SQLite-backed persistent audit log in `data/music-porter.db`
- Thread-safe writes via `RLock`, lockless reads via WAL mode
- Schema: `audit_entries` table with `id`, `timestamp`, `operation`, `description`, `params` (JSON), `status`, `duration_s`, `source`
- Source field: `'cli'`, `'web'`, `'ios'`, or `'api'` — set by caller
- Audited operations: `login`, `logout`, `auth_denied`, `auth_validate`, `settings_update`, `playlist_add`, `playlist_update`, `playlist_delete`, `playlist_delete_data`, `tag_update`, `tag_restore`, `tag_reset`, `convert`, `cover_art`, `cookie_refresh`, `pipeline`, `audit_clear`, `destination_rename`
- Business classes accept `audit_logger` and `audit_source` params — audit logging is wired at the call site, not inside the class
- Web dashboard: `/audit` page with filtering, pagination, stats cards, and clear tool
- No dedicated CLI subcommand — audit log is populated by all operations but viewed/managed via web only

### Task History (TaskHistoryDB)

- SQLite-backed persistent task history in `data/music-porter.db` (`task_history` table)
- Thread-safe writes via `Lock`, lockless reads via WAL mode (same pattern as `AuditLogger`)
- Schema: `task_history` table with `id` (TEXT PK), `operation`, `description`, `status`, `result` (JSON), `error`, `started_at` (epoch), `finished_at` (epoch), `source`
- Startup recovery: marks stale `running`/`pending` rows as `failed` on init
- Wired into `TaskManager` — all background tasks are persisted automatically
- Web dashboard: `/operations` page with stats cards, filters, pagination, active task SSE viewer, and clear tool
- CLI: `./music-porter tasks` subcommand for viewing history and stats

## Additional Resources

- **README.md** - Project overview, quick start guide, and future features roadmap
- **MUSIC-PORTER-GUIDE.md** - Complete usage guide with examples
- **COOKIE-MANAGEMENT-GUIDE.md** - Cookie validation, auto-refresh, and troubleshooting
- **IOS-COMPANION-GUIDE.md** - iOS companion app setup, pairing, and usage guide
