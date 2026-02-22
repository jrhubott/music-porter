# Completed SRS Documents

---

# SRS: Core Pipeline and Conversion Engine

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Provide the foundational pipeline that downloads Apple Music playlists, converts M4A files to MP3, applies tag updates, and optionally syncs to USB — all orchestrated through a unified CLI tool with professional subcommand architecture.

## 2. Requirements

### 2.1 Pipeline Orchestration

The `PipelineOrchestrator` class shall coordinate a four-stage workflow:

| Stage | Name | Description |
|-------|------|-------------|
| 1 | `download` | Download playlist from Apple Music via gamdl |
| 2 | `convert` | Convert M4A → MP3 via ffmpeg |
| 3 | `tag` | Apply album/artist tags and embed cover art |
| 4 | `usb-sync` | Copy files to USB drive (optional) |

- [x] Pipeline runs stages sequentially: download → convert → tag → USB sync
- [x] `PipelineStatistics` tracks `stages_completed`, `stages_failed`, and `stages_skipped` lists
- [x] Individual stage failures do not abort the entire pipeline (error recovery)
- [x] Pipeline supports single-playlist (`--playlist`), URL-based (`--url`), and batch (`--auto`) modes
- [x] `PlaylistResult` captures per-playlist results including `failed_stage` indicator
- [x] `AggregateStatistics` accumulates results across multiple playlists with `get_cumulative_stats()`

### 2.2 M4A-to-MP3 Conversion

The `Converter` class shall convert M4A files to MP3 using ffmpeg:

- [x] Uses `ffmpeg-python` library wrapping the system `ffmpeg` binary
- [x] Codec: `libmp3lame` (LAME MP3 encoder)
- [x] Runs with `quiet=True` to suppress ffmpeg output during batch processing
- [x] Catches `ffmpeg.Error` exceptions; logs details and continues processing remaining files
- [x] Existing MP3s are skipped unless `--force` flag is used
- [x] Force re-conversion increments `overwritten` counter (distinct from `converted`)
- [x] Output filenames: `"Artist - Title.mp3"` (configurable via output profile)
- [x] Invalid filename characters stripped: `/\:*?"<>|`

### 2.3 Quality Presets

Configurable quality presets via `QUALITY_PRESETS` dictionary and `--preset` flag:

| Preset | Mode | Value | Est. Bitrate |
|--------|------|-------|--------------|
| `lossless` | CBR | `b:a 320k` | 320 kbps |
| `high` | VBR | `q:a 2` | ~190–250 kbps |
| `medium` | VBR | `q:a 4` | ~165–210 kbps |
| `low` | VBR | `q:a 6` | ~115–150 kbps |
| `custom` | VBR | `q:a 0–9` | Variable |

- [x] Default preset: `lossless` (320 kbps CBR) via `DEFAULT_QUALITY_PRESET` constant
- [x] `--preset` flag accepts `lossless`, `high`, `medium`, `low`, `custom`
- [x] Custom VBR requires both `--preset custom` and `--quality 0-9`
- [x] `_get_quality_settings(preset)` resolves preset name to ffmpeg parameters
- [x] `--preset` flag available on both `convert` and `pipeline` subcommands

### 2.4 Multi-Threaded Conversion

- [x] Uses `concurrent.futures.ThreadPoolExecutor` for parallel file conversion
- [x] Default workers: `min(os.cpu_count(), MAX_DEFAULT_WORKERS)` where `MAX_DEFAULT_WORKERS = 6`
- [x] Configurable via `--workers N` global flag
- [x] `ConversionStatistics` is thread-safe with `threading.Lock`
- [x] Atomic progress counter via `next_progress()` method

### 2.5 Progress Bars

- [x] Uses `tqdm` library for progress display
- [x] `ProgressBar` context manager wraps tqdm with custom formatting
- [x] Terminal state saved/restored via `_save_terminal()` and `_restore_terminal()`
- [x] Logger integrates with progress bar via `register_bar()` / `unregister_bar()` for write routing
- [x] Progress bars disabled during `--dry-run` mode

### 2.6 Download Module

The `Downloader` class shall download playlists from Apple Music:

- [x] Executes gamdl as a subprocess via `subprocess.Popen()`
- [x] Command: `python -m gamdl --log-level INFO -o <output_path>/ <url>`
- [x] Line-buffered output (`bufsize=1`, `universal_newlines=True`)
- [x] `DownloadStatistics` tracks `playlist_total`, `downloaded`, `skipped`, and `failed`
- [x] Output organized in nested `Artist/Album/Track.m4a` directory structure

### 2.7 CLI Subcommand Architecture

The tool shall provide the following subcommands via `argparse`:

- [x] `pipeline` — Full download + convert + tag workflow
- [x] `download` — Download from Apple Music
- [x] `convert` — Convert M4A → MP3
- [x] `tag` — Update tags on existing MP3s
- [x] `restore` — Restore original tags from TXXX frames
- [x] `reset` — Reset tags from source M4A files
- [x] `sync-usb` — Copy files to USB drive
- [x] `cover-art` — Cover art management (embed, extract, update, strip, resize)
- [x] `summary` — Display export library statistics
- [x] `web` — Launch web dashboard

### 2.8 Batch Processing Statistics

- [x] `ConversionStatistics`: `total_found`, `converted`, `overwritten`, `skipped`, `errors`
- [x] `TagStatistics`: per-field counters for updated, stored, protected, restored, missing
- [x] `PipelineStatistics`: aggregates download, conversion, tagging, cover art, and USB stats per playlist
- [x] `PlaylistResult`: per-playlist success/failure with `failed_stage` and `duration`
- [x] `AggregateStatistics`: cumulative stats across all playlists with `get_cumulative_stats()`
- [x] Comprehensive summary report printed at pipeline completion

### 2.9 Dry-Run Mode

- [x] Global `--dry-run` flag passed through all operations
- [x] `logger.dry_run(message)` writes messages with `[DRY-RUN]` prefix
- [x] File write operations conditionally skipped when `dry_run=True`
- [x] Progress bars disabled during dry-run
- [x] No files created, modified, or deleted in dry-run mode

### 2.10 Logging System

The `Logger` class shall provide timestamped logging to console and file:

- [x] Log files stored in `logs/` directory with `%Y-%m-%d_%H-%M-%S.log` naming
- [x] Thread-safe writes via `threading.Lock`
- [x] Log methods: `info()`, `debug()`, `warn()`, `error()`, `success()`, `dry_run()`, `file_info()`
- [x] Console routing through `tqdm.write()` when progress bar is active
- [x] `--verbose` flag enables debug-level output
- [x] `--version` flag displays current version

### 2.11 Global Flags

- [x] `--dry-run` — Preview changes without modifying files
- [x] `--verbose` / `-v` — Enable verbose output
- [x] `--version` — Show version and exit
- [x] `--workers N` — Set parallel conversion workers
- [x] `--output-type TYPE` — Select output profile

### 2.12 Virtual Environment Auto-Activation

- [x] `_auto_activate_venv()` detects and re-execs under `.venv/bin/python` if available
- [x] Supports macOS/Linux (`.venv/bin/python`) and Windows (`.venv/Scripts/python.exe`)
- [x] Uses `os.execv()` for transparent re-launch

## 3. Edge Cases

- [x] FFmpeg not installed: `DependencyChecker` detects missing binary and provides install instructions per platform
- [x] Empty playlist directory: conversion reports 0 files found, no error
- [x] Individual file conversion failure: logged and counted as error, remaining files processed
- [x] Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics
- [x] gamdl subprocess failure: captured via return code and logged

---

# SRS: Tag Preservation and Management

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Provide a robust tag management system that preserves original metadata from source files using TXXX (user-defined text) ID3 frames with hard-gate protection, ensuring originals can always be restored even after multiple update cycles.

## 2. Requirements

### 2.1 TXXX Hard-Gate Protection

Original metadata shall be stored in TXXX frames that are written once and never overwritten:

| TXXX Frame | Constant | Stores |
|------------|----------|--------|
| `OriginalTitle` | `TXXX_ORIGINAL_TITLE` | Original track title |
| `OriginalArtist` | `TXXX_ORIGINAL_ARTIST` | Original artist name |
| `OriginalAlbum` | `TXXX_ORIGINAL_ALBUM` | Original album name |
| `OriginalCoverArtHash` | `TXXX_ORIGINAL_COVER_ART_HASH` | SHA-256 hash prefix of original cover art |

- [x] `_txxx_exists(tags, desc_name)` checks for frame existence by iterating `tags.values()` with `isinstance(frame, TXXX)`
- [x] `_get_txxx(tags, desc_name)` retrieves frame value by iterating frame types (not string key indexing)
- [x] `save_original_tag()` enforces hard-gate: skips write if `_txxx_exists()` returns True
- [x] Once written, TXXX protection frames are NEVER overwritten (except via explicit `reset` command)

### 2.2 Tag Operations

The `TaggerManager` class shall support three tag operations:

**Update** (`update_tags()`):
- [x] Updates album and/or artist tags on MP3 files
- [x] Saves original values to TXXX frames before overwriting (hard-gate protected)
- [x] `--album` and `--artist` flags for specifying new values
- [x] Statistics tracked per-field: `title_updated`, `album_updated`, `artist_updated`

**Restore** (`restore_tags()`):
- [x] Restores tags from TXXX protection frames to standard ID3 fields
- [x] `--all` flag restores all tags; `--album`, `--title`, `--artist` for selective restore
- [x] Reports missing TXXX frames (tracks `*_missing` counters)
- [x] Statistics tracked: `title_restored`, `album_restored`, `artist_restored`

**Reset** (`reset_tags_from_source()`):
- [x] Overwrites TXXX protection frames from source M4A files (destructive)
- [x] Requires confirmation prompt before proceeding
- [x] Takes both `input_dir` (M4A source) and `output_dir` (MP3 target) parameters

### 2.3 Title Formatting

- [x] `_strip_artist_prefix(title, artist)` prevents double-compounding of "Artist - " prefix
- [x] New titles built from protected originals: `f"{OriginalArtist} - {OriginalTitle}"`
- [x] Title format controlled by profile's `title_tag_format` field (`"artist_title"`)

### 2.4 ID3 Version and Cleanup

Default cleanup options applied via `_apply_cleanup()`:

- [x] ID3v2.3 output by default (older device compatibility), configurable per profile
- [x] ID3v1 tags stripped by default (`strip_id3v1: True`)
- [x] Duplicate frames automatically removed via key iteration
- [x] Overrides available: `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates`
- [x] Profile `id3_version` field: `3` for ID3v2.3, `4` for ID3v2.4

### 2.5 Tag Statistics

`TagStatistics` class tracks per-field counters:

- [x] Updated: `title_updated`, `album_updated`, `artist_updated`
- [x] Stored (TXXX): `title_stored`, `artist_stored`, `album_stored`
- [x] Protected (skipped): `title_protected`, `artist_protected`, `album_protected`
- [x] Restored: `title_restored`, `artist_restored`, `album_restored`
- [x] Missing: `title_missing`, `artist_missing`, `album_missing`

## 3. Edge Cases

- [x] Mutagen key indexing inconsistency after save/reload: mitigated by iterating `tags.values()` instead of string key lookup
- [x] Files without existing tags: creates new ID3 tag structure before writing
- [x] Multiple script runs: TXXX frames preserved across unlimited update cycles
- [x] Reset confirmation: requires interactive confirmation to prevent accidental TXXX overwrite

---

# SRS: Cover Art Management

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.5.0–v2.3.0

---

## 1. Purpose

Manage cover art across the MP3 library — embedding art from M4A sources during conversion, and providing standalone operations to embed, extract, update, strip, and resize artwork on existing MP3 files.

## 2. Requirements

### 2.1 Automatic Embedding During Conversion

- [x] Cover art automatically extracted from source M4A and embedded into MP3 during conversion
- [x] APIC frame with type `APIC_TYPE_FRONT_COVER` (3) and appropriate MIME type (`image/jpeg` or `image/png`)
- [x] SHA-256 hash prefix (first 16 chars) stored in `TXXX:OriginalCoverArtHash` with hard-gate protection
- [x] `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding
- [x] Profile-based resizing: `artwork_size > 0` resizes to max pixels, `0` embeds original, `-1` strips artwork

### 2.2 Cover Art Subcommands

The `CoverArtManager` class shall support five operations via `cover-art` subcommand:

**embed:**
- [x] Embeds cover art from matching M4A source files into existing MP3s
- [x] Auto-derives source directory from `export/` → `music/` path mapping
- [x] `--source` flag overrides auto-derivation
- [x] `--all` flag processes all configured playlists
- [x] `--force` flag re-embeds even if art already exists
- [x] Accepts `--dir-structure` and `--filename-format` flags for non-default layouts

**extract:**
- [x] Saves embedded cover art from MP3 files to image files
- [x] Default output directory: `<playlist>/cover-art/`
- [x] `--output` flag for custom output directory

**update:**
- [x] Replaces cover art on all MP3s from a single image file
- [x] `--image` flag (required) accepts `.jpg`, `.jpeg`, `.png` files
- [x] Detects MIME type from file extension

**strip:**
- [x] Removes all APIC frames from MP3s to reduce file size

**resize:**
- [x] Resizes existing embedded cover art to specified max pixel size
- [x] Available as interactive menu option (R)

### 2.3 Pillow Integration

- [x] Uses `PIL.Image` from Pillow library for image processing
- [x] Resize method: `img.thumbnail((max_size, max_size), Image.LANCZOS)` (high-quality downsampling)
- [x] Supports PNG and JPEG with proper color mode conversion
- [x] `ride-command` profile: 100px max artwork; `basic` profile: original size

### 2.4 Cover Art Statistics

- [x] Per-playlist tracking: `files_with_cover_art`, `files_without_cover_art`
- [x] Original vs. resized tracking: `files_with_original_cover_art`, `files_with_resized_cover_art`
- [x] Integrated into library summary display

## 3. Edge Cases

- [x] M4A source has no cover art: MP3 created without APIC frame, logged as warning
- [x] Source directory not found: clear error message with path displayed
- [x] Unsupported image format in `--image`: rejected with error

---

# SRS: Cookie Management

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.6.0–v2.3.0

---

## 1. Purpose

Validate and automatically refresh Apple Music authentication cookies, enabling unattended playlist downloads with graceful handling of expired sessions.

## 2. Requirements

### 2.1 Cookie Validation

The `CookieManager` class shall validate cookies at startup and before downloads:

- [x] Parses `cookies.txt` using `http.cookiejar.MozillaCookieJar` (Netscape format)
- [x] Checks for `media-user-token` cookie on `.music.apple.com` domain
- [x] Returns `CookieStatus` object with validation result
- [x] Displays expiration in days: "Cookies valid until YYYY-MM-DD (N days remaining)"
- [x] Supports session cookies (no expiration date)
- [x] `--skip-cookie-validation` flag bypasses checks (not recommended)

### 2.2 Automatic Refresh via Selenium

- [x] `auto_refresh(backup=True, browser=None)` method orchestrates refresh
- [x] `_extract_with_selenium(browser=None)` launches browser to extract cookies
- [x] Launches browser headless first; falls back to visible mode if login needed
- [x] Login detection: checks for sign-in button presence to determine authentication state
- [x] Converts Selenium cookies to `http.cookiejar.Cookie` objects
- [x] `--auto-refresh-cookies` flag for non-interactive refresh

### 2.3 Multi-Browser Support

- [x] `_detect_default_browser()` detects OS default browser
- [x] Platform-specific detection: LaunchServices (macOS), xdg-settings (Linux), registry (Windows)
- [x] Supported browsers: Chrome, Firefox, Safari, Edge
- [x] Automatic fallback to other browsers if default fails
- [x] `webdriver-manager` handles automatic browser driver installation

### 2.4 Backup Strategy

- [x] Creates `cookies.txt.backup` before overwriting existing cookies
- [x] Backup preserves last known working cookies
- [x] Backup creation controlled by `backup=True` parameter (default)

### 2.5 Interactive and Non-Interactive Modes

- [x] Interactive: expired cookies trigger prompt "Attempt automatic cookie refresh? [Y/n]"
- [x] Menu-level checks before batch operations; per-download checks for single operations
- [x] Non-interactive: fails immediately with clear error if cookies invalid (prevents hanging)

## 3. Edge Cases

- [x] No `cookies.txt` file: clear error with instructions to create one
- [x] Malformed cookie file: caught by MozillaCookieJar parser, reported as error
- [x] Browser not installed: automatic fallback to next available browser
- [x] Login required during headless extraction: falls back to visible browser for user interaction
- [x] Selenium not installed: provides manual refresh instructions as fallback

---

# SRS: USB Synchronization

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Detect connected USB drives, incrementally sync exported MP3 files, and optionally eject the drive — with platform-aware behavior for macOS, Linux, and Windows.

## 2. Requirements

### 2.1 Platform-Aware Drive Detection

The `USBManager` class shall detect USB drives based on the current platform:

| Platform | Detection Path | Excluded Volumes | Method |
|----------|---------------|-----------------|--------|
| macOS | `/Volumes/` | "Macintosh HD", "Macintosh HD - Data" | `_find_usb_drives_macos()` |
| Linux | `/media/$USER/`, `/mnt/` | "boot", "root" | `_find_usb_drives_linux()` |
| Windows | Drive letters A:–Z: | C: (system drive) | `_find_usb_drives_windows()` |

- [x] Platform auto-detected at startup via `platform.system()` (`IS_MACOS`, `IS_LINUX`, `IS_WINDOWS`)
- [x] Excluded volumes defined in `EXCLUDED_USB_VOLUMES` constant (platform-conditional)
- [x] Single drive auto-selected; multiple drives prompt user selection via `select_usb_drive()`

### 2.2 Incremental Sync

The `_should_copy_file()` method shall determine whether a file needs copying:

- [x] Compares file size between source and destination
- [x] Compares modification time with 2-second FAT32 tolerance
- [x] Returns True (needs copy) if size differs or mtime is newer beyond tolerance
- [x] Existing up-to-date files are skipped (not re-copied)

### 2.3 Auto-Eject

- [x] macOS: automatic eject via `diskutil eject /Volumes/<volume>`
- [x] Linux: automatic unmount via `udisksctl unmount` with fallback to `umount`
- [x] Windows: manual eject via Explorer (automatic eject not implemented; user notified)

### 2.4 USB Directory

- [x] Default USB subdirectory: `DEFAULT_USB_DIR = "RZR/Music"`
- [x] Configurable via `--usb-dir` flag or `usb_dir` setting in config.yaml
- [x] Creates subdirectory structure on target drive if needed

### 2.5 Progress Tracking

- [x] Reports files copied, skipped (up-to-date), and errors
- [x] Integrated into pipeline statistics (`usb_success`, `usb_destination`)
- [x] `--copy-to-usb` flag on `pipeline` command triggers USB sync as final stage

### 2.6 Standalone Sync

- [x] `sync-usb` subcommand for standalone USB sync without pipeline
- [x] Optional `source_dir` argument; defaults to entire profile export directory
- [x] Preserves directory structure (flat or nested) on target drive

## 3. Edge Cases

- [x] No USB drive detected: clear message to check mount status, with platform-specific instructions
- [x] USB drive removed during sync: file copy error caught and reported
- [x] Eject failure on Linux: `udisksctl` failure falls back to `umount`

---

# SRS: Configuration, Profiles, and Interactive Menu

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.7.0–v2.3.0

---

## 1. Purpose

Provide a YAML-based configuration system with output profiles that control conversion behavior, and an interactive menu for user-friendly operation without remembering CLI flags.

## 2. Requirements

### 2.1 YAML Configuration (ConfigManager)

The `ConfigManager` class shall manage `config.yaml`:

- [x] Reads and writes YAML format via PyYAML library
- [x] Auto-creates default `config.yaml` if missing (`_create_default()`)
- [x] Key methods: `get_setting()`, `update_setting()`, `_save()`, `_load_yaml()`
- [x] Playlist management: `get_playlist_by_key()`, `get_playlist_by_index()`, `add_playlist()`, `update_playlist()`, `remove_playlist()`
- [x] Playlist key lookup is case-insensitive
- [x] Duplicate key detection on `add_playlist()`

**Default settings:**
```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6
```

- [x] Default `output_type`: `DEFAULT_OUTPUT_TYPE = "ride-command"`
- [x] Default `usb_dir`: `DEFAULT_USB_DIR = "RZR/Music"`
- [x] Default `workers`: `DEFAULT_WORKERS = min(os.cpu_count(), 6)`

### 2.2 Settings Precedence

Settings shall follow a three-level precedence chain resolved by `resolve_config_settings()`:

1. **CLI flag** (highest priority)
2. **config.yaml setting**
3. **Hardcoded constant** (lowest priority)

- [x] Precedence chain implemented and documented
- [x] Each setting independently resolved (e.g., `--output-type` overrides config but config workers still apply)

### 2.3 Output Profiles (OutputProfile)

The `OutputProfile` dataclass shall define conversion behavior per profile:

**Fields:**
- [x] `name` — Profile identifier
- [x] `description` — Human-readable description
- [x] `directory_structure` — `"flat"`, `"nested-artist"`, or `"nested-artist-album"`
- [x] `filename_format` — `"full"` or `"title-only"`
- [x] `id3_version` — `3` (ID3v2.3) or `4` (ID3v2.4)
- [x] `strip_id3v1` — Remove ID3v1 tags (boolean)
- [x] `title_tag_format` — e.g., `"artist_title"`
- [x] `artwork_size` — `>0`=resize to max px, `0`=original, `-1`=strip
- [x] `quality_preset` — Default conversion quality
- [x] `pipeline_album` — `"playlist_name"` or `"original"`
- [x] `pipeline_artist` — `"various"` or `"original"`

**Built-in Profiles:**

| Profile | ID3 | Artwork | Quality | Album | Artist |
|---------|-----|---------|---------|-------|--------|
| `ride-command` | v2.3 | 100px | lossless | playlist name | "Various" |
| `basic` | v2.4 | original | lossless | original | original |

- [x] `ride-command` profile: default, optimized for Polaris Ride Command infotainment
- [x] `basic` profile: standard MP3 with original tags and artwork preserved
- [x] Profiles stored in `OUTPUT_PROFILES` dictionary

### 2.4 Profile-Scoped Export Directories

- [x] Export paths scoped by profile: `export/<profile>/<playlist>/`
- [x] `get_export_dir(profile_name, playlist_key=None)` helper builds paths
- [x] Without `playlist_key`: returns `export/<profile>/`
- [x] With `playlist_key`: returns `export/<profile>/<playlist_key>/`

### 2.5 Interactive Menu (InteractiveMenu)

The `InteractiveMenu` class shall provide a loop-based interface:

| Input | Action | Handler |
|-------|--------|---------|
| 1–N | Process numbered playlist | `_handle_playlist_selection()` |
| A | Process all playlists | `_handle_all_playlists()` |
| U | Enter URL for new playlist | `_handle_url_entry()` |
| C | Copy to USB only | USB sync handler |
| S | Show library summary | `_handle_summary()` |
| R | Resize all cover art | `_handle_resize_cover_art()` |
| P | Change output profile | `_handle_change_profile()` |
| X | Exit | Immediate exit |

- [x] `while True` loop returns to menu after each operation (except X)
- [x] Case-insensitive input handling
- [x] Post-processing prompts for USB copy after pipeline operations
- [x] Summary display with pause-to-review before returning to menu
- [x] Profile change persisted to config.yaml via `update_setting()`
- [x] New URLs saved to config.yaml via `add_playlist()`

## 3. Edge Cases

- [x] Missing `config.yaml`: auto-created with defaults on first run
- [x] Invalid profile name: rejected with error listing valid profiles
- [x] Duplicate playlist key on add: detected and reported
- [x] Empty Enter at menu: treated as Exit (X)

---

# SRS: Web Dashboard

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v2.0.0–v2.3.0

---

## 1. Purpose

Provide a browser-based dashboard with full feature parity to the CLI, enabling remote and visual operation of all music-porter capabilities with real-time progress streaming.

## 2. Requirements

### 2.1 Flask Application

- [x] Web dashboard implemented in `web_ui.py` as a Flask application
- [x] Launched via `music-porter web` subcommand with `--host` and `--port` flags
- [x] HTML templates served from `templates/` directory

### 2.2 Page Routes (9 pages)

| Route | Template | Purpose |
|-------|----------|---------|
| `GET /` | `dashboard.html` | Main dashboard with library stats and sortable table |
| `GET /playlists` | `playlists.html` | Playlist CRUD management |
| `GET /pipeline` | `pipeline.html` | Full pipeline workflow |
| `GET /convert` | `convert.html` | Conversion operations |
| `GET /tags` | `tags.html` | Tag update/restore/reset |
| `GET /cover-art` | `cover_art.html` | Cover art management |
| `GET /usb` | `usb_sync.html` | USB sync operations |
| `GET /settings` | `settings.html` | Configuration and profile management |
| `GET /operations` | `operations.html` | Task history and status |

- [x] All 9 pages implemented and accessible

### 2.3 API Endpoints (~26 endpoints)

**Status & Info:**
- [x] `GET /api/status` — System status, cookies, library stats, current profile
- [x] `GET /api/summary` — Export library statistics
- [x] `GET /api/library-stats` — Source music/ directory statistics

**Cookie Management:**
- [x] `GET /api/cookies/browsers` — Available browser list
- [x] `POST /api/cookies/refresh` — Auto-refresh cookies with browser selection

**Playlist CRUD:**
- [x] `GET /api/playlists` — List all playlists
- [x] `POST /api/playlists` — Add new playlist
- [x] `PUT /api/playlists/<key>` — Update existing playlist
- [x] `DELETE /api/playlists/<key>` — Remove playlist

**Settings:**
- [x] `GET /api/settings` — Get all settings, profiles, valid structures/formats
- [x] `POST /api/settings` — Update settings

**Directory Listings:**
- [x] `GET /api/directories/music` — List music/ playlists
- [x] `GET /api/directories/export` — List export/ playlists with file counts (uses rglob for nested dirs)

**Operations:**
- [x] `POST /api/pipeline/run` — Execute full pipeline (accepts `playlist`, `url`, `auto`, `dir_structure`, `filename_format`)
- [x] `POST /api/convert/run` — Convert M4A to MP3 (accepts `dir_structure`, `filename_format`)
- [x] `POST /api/tags/update` — Update album/artist tags
- [x] `POST /api/tags/restore` — Restore original tags
- [x] `POST /api/tags/reset` — Reset tags from source
- [x] `POST /api/cover-art/<action>` — Cover art: embed, extract, update, strip, resize

**USB:**
- [x] `GET /api/usb/drives` — List connected USB drives
- [x] `POST /api/usb/sync` — Sync files to USB

**Task Management & Streaming:**
- [x] `GET /api/tasks` — List all background tasks
- [x] `GET /api/tasks/<task_id>` — Get task details
- [x] `POST /api/tasks/<task_id>/cancel` — Cancel running task
- [x] `GET /api/stream/<task_id>` — SSE live log stream

### 2.4 Server-Sent Events (SSE) Live Streaming

- [x] `GET /api/stream/<task_id>` provides real-time log streaming
- [x] Long-polling with 30-second heartbeat timeout
- [x] Message types: `log`, `progress`, `heartbeat`, `done`
- [x] Progress events include: `current`, `total`, `stage`, `percent`
- [x] Sentinel (`None`) in queue indicates task completion
- [x] JSON-formatted SSE data payloads

### 2.5 Background Task Management

**TaskState dataclass:**
- [x] Fields: `id`, `operation`, `description`, `status`, `result`, `error`, `thread`, `cancel_event`, `log_queue`, `started_at`, `finished_at`
- [x] Status values: `pending`, `running`, `completed`, `failed`, `cancelled`
- [x] `elapsed()` method calculates task duration

**TaskManager class:**
- [x] `submit(operation, description, target)` spawns background thread, returns 12-char hex task_id
- [x] `get(task_id)` retrieves TaskState
- [x] `list_all()` returns all tasks as dicts
- [x] `cancel(task_id)` signals cancellation via `threading.Event`
- [x] `is_busy()` checks if any task is currently running

### 2.6 WebLogger

- [x] `WebLogger` subclass of `Logger` routes messages to SSE queue
- [x] `_write(level, message)` pushes to queue and writes to log file
- [x] `file_info(message)` sends per-file progress messages
- [x] `_make_progress_callback()` returns throttled progress event closure
- [x] `register_bar()` / `unregister_bar()` are no-ops (progress handled via SSE)

### 2.7 Feature Parity (CLI ↔ Web)

- [x] Every CLI operation has a corresponding API endpoint
- [x] Pipeline, convert, tag, restore, reset, cover-art, USB sync all accessible from web
- [x] Settings and profile management available in web UI
- [x] Library summary and statistics displayed on dashboard

## 3. Edge Cases

- [x] Task already running: `submit()` returns None, client informed of busy state
- [x] SSE stream for nonexistent task: handled gracefully
- [x] Concurrent access: TaskManager serializes operations

---

# SRS: Library Summary and Statistics

**Version:** 1.0
**Date:** 2026-02-20
**Status:** Complete
**Implemented in:** v1.4.0–v2.3.0

---

## 1. Purpose

Provide comprehensive library statistics covering both source (M4A) and export (MP3) collections, with tag integrity checking and multiple output modes for different use cases.

## 2. Requirements

### 2.1 Summary Command

The `summary` subcommand shall display export library statistics in three modes:

| Mode | Flag | Description |
|------|------|-------------|
| Default | (none) | Aggregate stats + tag integrity + cover art + per-playlist table |
| Quick | `--quick` | Aggregate statistics only, no per-playlist breakdown |
| Detailed | `--detailed` | Default + extended per-playlist information and metadata |

- [x] `generate_summary(export_dir, detailed, quick, ...)` main entry point
- [x] `--export-dir` flag for custom export directory
- [x] `--no-library` flag skips source music/ directory scan
- [x] Available in interactive menu as "S. Show library summary"

### 2.2 Source Library Statistics (MusicLibraryStats)

- [x] Scans nested `music/Artist/Album/Track.m4a` directory structure
- [x] Tracks: `total_playlists`, `total_files`, `total_size_bytes`
- [x] Cross-references against export: `total_exported`, `total_unconverted`
- [x] `scan_duration` records scan time in seconds
- [x] Per-playlist stats in `playlists` list

### 2.3 Export Playlist Analysis (PlaylistSummary)

Per-playlist statistics:

- [x] `file_count` — Number of MP3 files
- [x] `total_size_bytes` — Total playlist size
- [x] `avg_file_size_mb` — Average file size
- [x] `last_modified` — Most recent modification timestamp
- [x] Tag integrity: `sample_files_checked`, `sample_files_with_tags`
- [x] Cover art: `files_with_cover_art`, `files_without_cover_art`, `files_with_original_cover_art`, `files_with_resized_cover_art`

### 2.4 Aggregate Statistics (LibrarySummaryStatistics)

- [x] `total_playlists`, `total_files`, `total_size_bytes`, `scan_duration`
- [x] Tag integrity: `sample_size`, `files_with_protection_tags`, `files_missing_protection_tags`
- [x] Cover art: `files_with_cover_art`, `files_without_cover_art`
- [x] `playlists: list[PlaylistSummary]` for per-playlist breakdown

### 2.5 Tag Integrity Checking

- [x] `_check_tag_integrity()` scans ALL files (no sampling)
- [x] Checks for TXXX frames: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`
- [x] Checks for APIC (cover art) frames
- [x] Distinguishes original vs. resized artwork via `OriginalCoverArtHash` TXXX
- [x] Uses same TXXX detection methods as `TaggerManager` for consistency

### 2.6 Display and Output

- [x] Per-playlist table with files, tags, size, and last updated date
- [x] Export percentage and unconverted count from source library
- [x] Tag integrity percentages displayed
- [x] Cover art statistics integrated into summary
- [x] Graceful error handling: continues on permission errors, displays partial results

### 2.7 Web Dashboard Integration

- [x] `GET /api/summary` endpoint returns summary data
- [x] `GET /api/library-stats` endpoint returns source library stats
- [x] Dashboard page displays library stats with sortable table

## 3. Edge Cases

- [x] Empty export directory: reports 0 playlists, no error
- [x] Permission errors on individual files: caught and skipped, partial results displayed
- [x] Missing music/ directory: library stats section skipped with message

---

# SRS: Configurable Output Directory Structure & Filename Format

**Version:** 1.0
**Date:** 2026-02-19
**Status:** Complete
**Implemented in:** v2.3.0

---

## 1. Purpose

Extend the output-type profile system so that each profile controls how converted MP3 files are organized in the output directory (directory structure) and how output files are named (filename format). Users can override these settings via CLI flags or config.yaml.

## 2. Background

The `OutputProfile` dataclass already contains `directory_structure` and `filename_format` fields, but both existing profiles (`ride-command` and `basic`) use identical values: `"flat"` and `"artist_title"`. The codebase has placeholder comments indicating planned support for nested directories and alternative filename formats. This feature activates those extension points.

## 3. Requirements

### 3.1 Directory Structures

The system shall support three directory structure modes, configurable per output profile:

| Value | Layout | Example Path |
|-------|--------|-------------|
| `flat` | All MP3s in a single directory | `export/ride-command/Pop_Workout/Artist - Title.mp3` |
| `nested-artist` | Subdirectories per artist | `export/ride-command/Pop_Workout/Taylor Swift/Title.mp3` |
| `nested-artist-album` | Subdirectories per artist and album | `export/ride-command/Pop_Workout/Taylor Swift/1989/Title.mp3` |

- [x] `flat` directory structure works (existing behavior)
- [x] `nested-artist` directory structure creates artist subdirectories
- [x] `nested-artist-album` directory structure creates artist/album subdirectories
- [x] Artist and album directory names sanitized using existing `sanitize_filename()`
- [x] Subdirectories created automatically during conversion
- [x] Unknown artist defaults to `"Unknown Artist"` directory name
- [x] Unknown album defaults to `"Unknown Album"` directory name

### 3.2 Filename Formats

The system shall support two filename format modes, configurable per output profile:

| Value | Pattern | Example |
|-------|---------|---------|
| `full` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title-only` | `Title.mp3` | `Shake It Off.mp3` |

- [x] `full` filename format works (existing behavior)
- [x] `title-only` filename format produces title-only filenames

### 3.3 Configuration

Settings shall follow the existing precedence chain:

**CLI flag > config.yaml setting > profile default**

#### 3.3.1 CLI Flags

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `full`, `title-only` | Profile default |

- [x] `--dir-structure` flag added to `pipeline` subcommand
- [x] `--dir-structure` flag added to `convert` subcommand
- [x] `--filename-format` flag added to `pipeline` subcommand
- [x] `--filename-format` flag added to `convert` subcommand

#### 3.3.2 config.yaml Settings

```yaml
settings:
  dir_structure: flat              # optional
  filename_format: artist_title    # optional
```

- [x] `dir_structure` setting read from config.yaml
- [x] `filename_format` setting read from config.yaml
- [x] Omitted settings fall back to profile default

#### 3.3.3 Profile Defaults

Both existing profiles shall retain their current defaults:

| Profile | directory_structure | filename_format |
|---------|-------------------|-----------------|
| `ride-command` | `flat` | `full` |
| `basic` | `flat` | `full` |

- [x] `ride-command` profile defaults unchanged
- [x] `basic` profile defaults unchanged

### 3.4 Backward Compatibility

- [x] Default behavior identical to current behavior (zero regression)
- [x] `summary` command works with nested export directories
- [x] `cover-art` commands work with nested export directories
- [x] `sync-usb` preserves nested directory structure on target drive
- [x] `tag` command works with nested export directories
- [x] `restore` command works with nested export directories

### 3.5 Feature Parity (CLI & Web)

**CLI:**
- [x] `--dir-structure` flag on `pipeline` command
- [x] `--dir-structure` flag on `convert` command
- [x] `--filename-format` flag on `pipeline` command
- [x] `--filename-format` flag on `convert` command

**Web Dashboard:**
- [x] Convert page: Directory Layout dropdown
- [x] Convert page: Filename Format dropdown
- [x] Pipeline page: Directory Layout dropdown
- [x] Pipeline page: Filename Format dropdown
- [x] Settings page: Profile comparison table includes directory structure
- [x] Settings page: Profile comparison table includes filename format
- [x] `/api/pipeline/run` accepts `dir_structure` parameter
- [x] `/api/pipeline/run` accepts `filename_format` parameter
- [x] `/api/convert/run` accepts `dir_structure` parameter
- [x] `/api/convert/run` accepts `filename_format` parameter
- [x] `/api/settings` GET returns valid dir_structures and filename_formats lists
- [x] `/api/directories/export` uses rglob for nested directory file counts
- [x] `cover-art embed` subcommand accepts `--dir-structure` and `--filename-format` flags (discovered during testing)

### 3.6 Display

- [x] Startup banner displays active directory structure
- [x] Startup banner displays active filename format
- [x] Log files record active directory structure and filename format
- [x] `--dry-run` output shows full output path (including subdirectories for nested structures)
- [x] Display values are human-readable via `display_name()` helper with `DISPLAY_NAMES` lookup and title-case fallback
- [x] `full` format displays as "Artist - Title" (custom override via `DISPLAY_NAMES`)
- [x] Other values display as title-cased with spaces (e.g., "Nested Artist Album", "Title Only")
- [x] CLI flag values remain hyphenated (e.g., `nested-artist-album`, `title-only`)

## 4. Edge Cases

### 4.1 Filename Collisions

- [x] `title-only` format with duplicate titles: skip-if-exists behavior with warning suggesting `full` format

### 4.2 Special Characters in Directory Names

- [x] Artist/album directory names sanitized by `sanitize_filename()` (strips `/\:*?"<>|`)

### 4.3 Deeply Nested Paths

Very long artist + album + title combinations could exceed filesystem path length limits (255 chars on macOS/Linux). This is an existing limitation and is not addressed by this feature.

## 5. Validation

- [x] Invalid `--dir-structure` value produces clear error with valid choices and non-zero exit
- [x] Invalid `--filename-format` value produces clear error with valid choices and non-zero exit
- [x] Invalid config.yaml values validated and rejected with clear error

## 6. Testing

- [x] All 6 combinations (3 structures x 2 formats) tested with `--dry-run --verbose`
- [x] Default behavior unchanged (flat + artist_title)
- [x] CLI flag overrides config.yaml
- [x] config.yaml overrides profile default
- [x] `summary` command works with nested export directories
- [x] `cover-art embed` correctly matches files with non-default formats
- [x] `sync-usb` preserves nested structure on target drive
- [x] Filename collisions with `title-only` format handled correctly
- [x] Web UI dropdowns submit correct API parameters
