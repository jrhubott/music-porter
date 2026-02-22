# Completed SRS Documents

---

# SRS: Core Pipeline and Conversion Engine

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Pipeline runs stages sequentially: download → convert → tag → USB sync | v1.0.0 | [x] |
| 2.1.2 | `PipelineStatistics` tracks `stages_completed`, `stages_failed`, and `stages_skipped` lists | v1.0.0 | [x] |
| 2.1.3 | Individual stage failures do not abort the entire pipeline (error recovery) | v1.0.0 | [x] |
| 2.1.4 | Pipeline supports single-playlist (`--playlist`), URL-based (`--url`), and batch (`--auto`) modes | v1.0.0 | [x] |
| 2.1.5 | `PlaylistResult` captures per-playlist results including `failed_stage` indicator | v1.0.0 | [x] |
| 2.1.6 | `AggregateStatistics` accumulates results across multiple playlists with `get_cumulative_stats()` | v1.0.0 | [x] |

### 2.2 M4A-to-MP3 Conversion

The `Converter` class shall convert M4A files to MP3 using ffmpeg:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | Uses `ffmpeg-python` library wrapping the system `ffmpeg` binary | v1.0.0 | [x] |
| 2.2.2 | Codec: `libmp3lame` (LAME MP3 encoder) | v1.0.0 | [x] |
| 2.2.3 | Runs with `quiet=True` to suppress ffmpeg output during batch processing | v1.0.0 | [x] |
| 2.2.4 | Catches `ffmpeg.Error` exceptions; logs details and continues processing remaining files | v1.0.0 | [x] |
| 2.2.5 | Existing MP3s are skipped unless `--force` flag is used | v1.0.0 | [x] |
| 2.2.6 | Force re-conversion increments `overwritten` counter (distinct from `converted`) | v1.0.0 | [x] |
| 2.2.7 | Output filenames: `"Artist - Title.mp3"` (configurable via output profile) | v1.0.0 | [x] |
| 2.2.8 | Invalid filename characters stripped: `/\:*?"<>\|` | v1.0.0 | [x] |

### 2.3 Quality Presets

Configurable quality presets via `QUALITY_PRESETS` dictionary and `--preset` flag:

| Preset | Mode | Value | Est. Bitrate |
|--------|------|-------|--------------|
| `lossless` | CBR | `b:a 320k` | 320 kbps |
| `high` | VBR | `q:a 2` | ~190–250 kbps |
| `medium` | VBR | `q:a 4` | ~165–210 kbps |
| `low` | VBR | `q:a 6` | ~115–150 kbps |
| `custom` | VBR | `q:a 0–9` | Variable |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | Default preset: `lossless` (320 kbps CBR) via `DEFAULT_QUALITY_PRESET` constant | v1.0.0 | [x] |
| 2.3.2 | `--preset` flag accepts `lossless`, `high`, `medium`, `low`, `custom` | v1.0.0 | [x] |
| 2.3.3 | Custom VBR requires both `--preset custom` and `--quality 0-9` | v1.0.0 | [x] |
| 2.3.4 | `_get_quality_settings(preset)` resolves preset name to ffmpeg parameters | v1.0.0 | [x] |
| 2.3.5 | `--preset` flag available on both `convert` and `pipeline` subcommands | v1.0.0 | [x] |

### 2.4 Multi-Threaded Conversion

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Uses `concurrent.futures.ThreadPoolExecutor` for parallel file conversion | v1.0.0 | [x] |
| 2.4.2 | Default workers: `min(os.cpu_count(), MAX_DEFAULT_WORKERS)` where `MAX_DEFAULT_WORKERS = 6` | v1.0.0 | [x] |
| 2.4.3 | Configurable via `--workers N` global flag | v1.0.0 | [x] |
| 2.4.4 | `ConversionStatistics` is thread-safe with `threading.Lock` | v1.0.0 | [x] |
| 2.4.5 | Atomic progress counter via `next_progress()` method | v1.0.0 | [x] |

### 2.5 Progress Bars

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | Uses `tqdm` library for progress display | v1.0.0 | [x] |
| 2.5.2 | `ProgressBar` context manager wraps tqdm with custom formatting | v1.0.0 | [x] |
| 2.5.3 | Terminal state saved/restored via `_save_terminal()` and `_restore_terminal()` | v1.0.0 | [x] |
| 2.5.4 | Logger integrates with progress bar via `register_bar()` / `unregister_bar()` for write routing | v1.0.0 | [x] |
| 2.5.5 | Progress bars disabled during `--dry-run` mode | v1.0.0 | [x] |

### 2.6 Download Module

The `Downloader` class shall download playlists from Apple Music:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | Executes gamdl as a subprocess via `subprocess.Popen()` | v1.0.0 | [x] |
| 2.6.2 | Command: `python -m gamdl --log-level INFO -o <output_path>/ <url>` | v1.0.0 | [x] |
| 2.6.3 | Line-buffered output (`bufsize=1`, `universal_newlines=True`) | v1.0.0 | [x] |
| 2.6.4 | `DownloadStatistics` tracks `playlist_total`, `downloaded`, `skipped`, and `failed` | v1.0.0 | [x] |
| 2.6.5 | Output organized in nested `Artist/Album/Track.m4a` directory structure | v1.0.0 | [x] |

### 2.7 CLI Subcommand Architecture

The tool shall provide the following subcommands via `argparse`:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.7.1 | `pipeline` — Full download + convert + tag workflow | v1.0.0 | [x] |
| 2.7.2 | `download` — Download from Apple Music | v1.0.0 | [x] |
| 2.7.3 | `convert` — Convert M4A → MP3 | v1.0.0 | [x] |
| 2.7.4 | `tag` — Update tags on existing MP3s | v1.0.0 | [x] |
| 2.7.5 | `restore` — Restore original tags from TXXX frames | v1.0.0 | [x] |
| 2.7.6 | `reset` — Reset tags from source M4A files | v1.0.0 | [x] |
| 2.7.7 | `sync-usb` — Copy files to USB drive | v1.0.0 | [x] |
| 2.7.8 | `cover-art` — Cover art management (embed, extract, update, strip, resize) | v1.5.0 | [x] |
| 2.7.9 | `summary` — Display export library statistics | v1.4.0 | [x] |
| 2.7.10 | `web` — Launch web dashboard | v2.0.0 | [x] |

### 2.8 Batch Processing Statistics

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.8.1 | `ConversionStatistics`: `total_found`, `converted`, `overwritten`, `skipped`, `errors` | v1.0.0 | [x] |
| 2.8.2 | `TagStatistics`: per-field counters for updated, stored, protected, restored, missing | v1.0.0 | [x] |
| 2.8.3 | `PipelineStatistics`: aggregates download, conversion, tagging, cover art, and USB stats per playlist | v1.0.0 | [x] |
| 2.8.4 | `PlaylistResult`: per-playlist success/failure with `failed_stage` and `duration` | v1.0.0 | [x] |
| 2.8.5 | `AggregateStatistics`: cumulative stats across all playlists with `get_cumulative_stats()` | v1.0.0 | [x] |
| 2.8.6 | Comprehensive summary report printed at pipeline completion | v1.0.0 | [x] |

### 2.9 Dry-Run Mode

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.9.1 | Global `--dry-run` flag passed through all operations | v1.0.0 | [x] |
| 2.9.2 | `logger.dry_run(message)` writes messages with `[DRY-RUN]` prefix | v1.0.0 | [x] |
| 2.9.3 | File write operations conditionally skipped when `dry_run=True` | v1.0.0 | [x] |
| 2.9.4 | Progress bars disabled during dry-run | v1.0.0 | [x] |
| 2.9.5 | No files created, modified, or deleted in dry-run mode | v1.0.0 | [x] |

### 2.10 Logging System

The `Logger` class shall provide timestamped logging to console and file:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.10.1 | Log files stored in `logs/` directory with `%Y-%m-%d_%H-%M-%S.log` naming | v1.0.0 | [x] |
| 2.10.2 | Thread-safe writes via `threading.Lock` | v1.0.0 | [x] |
| 2.10.3 | Log methods: `info()`, `debug()`, `warn()`, `error()`, `success()`, `dry_run()`, `file_info()` | v1.0.0 | [x] |
| 2.10.4 | Console routing through `tqdm.write()` when progress bar is active | v1.0.0 | [x] |
| 2.10.5 | `--verbose` flag enables debug-level output | v1.0.0 | [x] |
| 2.10.6 | `--version` flag displays current version | v1.0.0 | [x] |

### 2.11 Global Flags

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.11.1 | `--dry-run` — Preview changes without modifying files | v1.0.0 | [x] |
| 2.11.2 | `--verbose` / `-v` — Enable verbose output | v1.0.0 | [x] |
| 2.11.3 | `--version` — Show version and exit | v1.0.0 | [x] |
| 2.11.4 | `--workers N` — Set parallel conversion workers | v1.0.0 | [x] |
| 2.11.5 | `--output-type TYPE` — Select output profile | v1.7.0 | [x] |

### 2.12 Virtual Environment Auto-Activation

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.12.1 | `_auto_activate_venv()` detects and re-execs under `.venv/bin/python` if available | v1.0.0 | [x] |
| 2.12.2 | Supports macOS/Linux (`.venv/bin/python`) and Windows (`.venv/Scripts/python.exe`) | v1.0.0 | [x] |
| 2.12.3 | Uses `os.execv()` for transparent re-launch | v1.0.0 | [x] |

### 2.13 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.13.1 | FFmpeg not installed: `DependencyChecker` detects missing binary and provides install instructions per platform | v1.0.0 | [x] |
| 2.13.2 | Empty playlist directory: conversion reports 0 files found, no error | v1.0.0 | [x] |
| 2.13.3 | Individual file conversion failure: logged and counted as error, remaining files processed | v1.0.0 | [x] |
| 2.13.4 | Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics | v1.0.0 | [x] |
| 2.13.5 | gamdl subprocess failure: captured via return code and logged | v1.0.0 | [x] |

---

# SRS: Tag Preservation and Management

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | `_txxx_exists(tags, desc_name)` checks for frame existence by iterating `tags.values()` with `isinstance(frame, TXXX)` | v1.0.0 | [x] |
| 2.1.2 | `_get_txxx(tags, desc_name)` retrieves frame value by iterating frame types (not string key indexing) | v1.0.0 | [x] |
| 2.1.3 | `save_original_tag()` enforces hard-gate: skips write if `_txxx_exists()` returns True | v1.0.0 | [x] |
| 2.1.4 | Once written, TXXX protection frames are NEVER overwritten (except via explicit `reset` command) | v1.0.0 | [x] |

### 2.2 Tag Operations

The `TaggerManager` class shall support three tag operations:

**Update** (`update_tags()`):

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | Updates album and/or artist tags on MP3 files | v1.0.0 | [x] |
| 2.2.2 | Saves original values to TXXX frames before overwriting (hard-gate protected) | v1.0.0 | [x] |
| 2.2.3 | `--album` and `--artist` flags for specifying new values | v1.0.0 | [x] |
| 2.2.4 | Statistics tracked per-field: `title_updated`, `album_updated`, `artist_updated` | v1.0.0 | [x] |

**Restore** (`restore_tags()`):

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.5 | Restores tags from TXXX protection frames to standard ID3 fields | v1.0.0 | [x] |
| 2.2.6 | `--all` flag restores all tags; `--album`, `--title`, `--artist` for selective restore | v1.0.0 | [x] |
| 2.2.7 | Reports missing TXXX frames (tracks `*_missing` counters) | v1.0.0 | [x] |
| 2.2.8 | Statistics tracked: `title_restored`, `album_restored`, `artist_restored` | v1.0.0 | [x] |

**Reset** (`reset_tags_from_source()`):

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.9 | Overwrites TXXX protection frames from source M4A files (destructive) | v1.0.0 | [x] |
| 2.2.10 | Requires confirmation prompt before proceeding | v1.0.0 | [x] |
| 2.2.11 | Takes both `input_dir` (M4A source) and `output_dir` (MP3 target) parameters | v1.0.0 | [x] |

### 2.3 Title Formatting

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | `_strip_artist_prefix(title, artist)` prevents double-compounding of "Artist - " prefix | v1.0.0 | [x] |
| 2.3.2 | New titles built from protected originals: `f"{OriginalArtist} - {OriginalTitle}"` | v1.0.0 | [x] |
| 2.3.3 | Title format controlled by profile's `title_tag_format` field (`"artist_title"`) | v1.7.0 | [x] |

### 2.4 ID3 Version and Cleanup

Default cleanup options applied via `_apply_cleanup()`:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | ID3v2.3 output by default (older device compatibility), configurable per profile | v1.0.0 | [x] |
| 2.4.2 | ID3v1 tags stripped by default (`strip_id3v1: True`) | v1.0.0 | [x] |
| 2.4.3 | Duplicate frames automatically removed via key iteration | v1.0.0 | [x] |
| 2.4.4 | Overrides available: `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates` | v1.0.0 | [x] |
| 2.4.5 | Profile `id3_version` field: `3` for ID3v2.3, `4` for ID3v2.4 | v1.7.0 | [x] |

### 2.5 Tag Statistics

`TagStatistics` class tracks per-field counters:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | Updated: `title_updated`, `album_updated`, `artist_updated` | v1.0.0 | [x] |
| 2.5.2 | Stored (TXXX): `title_stored`, `artist_stored`, `album_stored` | v1.0.0 | [x] |
| 2.5.3 | Protected (skipped): `title_protected`, `artist_protected`, `album_protected` | v1.0.0 | [x] |
| 2.5.4 | Restored: `title_restored`, `artist_restored`, `album_restored` | v1.0.0 | [x] |
| 2.5.5 | Missing: `title_missing`, `artist_missing`, `album_missing` | v1.0.0 | [x] |

### 2.6 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | Mutagen key indexing inconsistency after save/reload: mitigated by iterating `tags.values()` instead of string key lookup | v1.0.0 | [x] |
| 2.6.2 | Files without existing tags: creates new ID3 tag structure before writing | v1.0.0 | [x] |
| 2.6.3 | Multiple script runs: TXXX frames preserved across unlimited update cycles | v1.0.0 | [x] |
| 2.6.4 | Reset confirmation: requires interactive confirmation to prevent accidental TXXX overwrite | v1.0.0 | [x] |

---

# SRS: Cover Art Management

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.5.0–v2.3.0

---

## 1. Purpose

Manage cover art across the MP3 library — embedding art from M4A sources during conversion, and providing standalone operations to embed, extract, update, strip, and resize artwork on existing MP3 files.

## 2. Requirements

### 2.1 Automatic Embedding During Conversion

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Cover art automatically extracted from source M4A and embedded into MP3 during conversion | v1.5.0 | [x] |
| 2.1.2 | APIC frame with type `APIC_TYPE_FRONT_COVER` (3) and appropriate MIME type (`image/jpeg` or `image/png`) | v1.5.0 | [x] |
| 2.1.3 | SHA-256 hash prefix (first 16 chars) stored in `TXXX:OriginalCoverArtHash` with hard-gate protection | v1.5.0 | [x] |
| 2.1.4 | `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding | v1.5.0 | [x] |
| 2.1.5 | Profile-based resizing: `artwork_size > 0` resizes to max pixels, `0` embeds original, `-1` strips artwork | v1.7.0 | [x] |

### 2.2 Cover Art Subcommands

The `CoverArtManager` class shall support five operations via `cover-art` subcommand:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | **embed:** Embeds cover art from matching M4A source files into existing MP3s | v1.5.0 | [x] |
| 2.2.2 | **embed:** Auto-derives source directory from `export/` → `music/` path mapping | v1.5.0 | [x] |
| 2.2.3 | **embed:** `--source` flag overrides auto-derivation | v1.5.0 | [x] |
| 2.2.4 | **embed:** `--all` flag processes all configured playlists | v1.5.0 | [x] |
| 2.2.5 | **embed:** `--force` flag re-embeds even if art already exists | v1.5.0 | [x] |
| 2.2.6 | **embed:** Accepts `--dir-structure` and `--filename-format` flags for non-default layouts | v2.3.0 | [x] |
| 2.2.7 | **extract:** Saves embedded cover art from MP3 files to image files | v1.5.0 | [x] |
| 2.2.8 | **extract:** Default output directory: `<playlist>/cover-art/` | v1.5.0 | [x] |
| 2.2.9 | **extract:** `--output` flag for custom output directory | v1.5.0 | [x] |
| 2.2.10 | **update:** Replaces cover art on all MP3s from a single image file | v1.5.0 | [x] |
| 2.2.11 | **update:** `--image` flag (required) accepts `.jpg`, `.jpeg`, `.png` files | v1.5.0 | [x] |
| 2.2.12 | **update:** Detects MIME type from file extension | v1.5.0 | [x] |
| 2.2.13 | **strip:** Removes all APIC frames from MP3s to reduce file size | v1.5.0 | [x] |
| 2.2.14 | **resize:** Resizes existing embedded cover art to specified max pixel size | v1.5.0 | [x] |
| 2.2.15 | **resize:** Available as interactive menu option (R) | v1.7.0 | [x] |

### 2.3 Pillow Integration

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | Uses `PIL.Image` from Pillow library for image processing | v1.5.0 | [x] |
| 2.3.2 | Resize method: `img.thumbnail((max_size, max_size), Image.LANCZOS)` (high-quality downsampling) | v1.5.0 | [x] |
| 2.3.3 | Supports PNG and JPEG with proper color mode conversion | v1.5.0 | [x] |
| 2.3.4 | `ride-command` profile: 100px max artwork; `basic` profile: original size | v1.7.0 | [x] |

### 2.4 Cover Art Statistics

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Per-playlist tracking: `files_with_cover_art`, `files_without_cover_art` | v1.5.0 | [x] |
| 2.4.2 | Original vs. resized tracking: `files_with_original_cover_art`, `files_with_resized_cover_art` | v1.5.0 | [x] |
| 2.4.3 | Integrated into library summary display | v1.5.0 | [x] |

### 2.5 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | M4A source has no cover art: MP3 created without APIC frame, logged as warning | v1.5.0 | [x] |
| 2.5.2 | Source directory not found: clear error message with path displayed | v1.5.0 | [x] |
| 2.5.3 | Unsupported image format in `--image`: rejected with error | v1.5.0 | [x] |

---

# SRS: Cookie Management

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.6.0–v2.3.0

---

## 1. Purpose

Validate and automatically refresh Apple Music authentication cookies, enabling unattended playlist downloads with graceful handling of expired sessions.

## 2. Requirements

### 2.1 Cookie Validation

The `CookieManager` class shall validate cookies at startup and before downloads:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Parses `cookies.txt` using `http.cookiejar.MozillaCookieJar` (Netscape format) | v1.6.0 | [x] |
| 2.1.2 | Checks for `media-user-token` cookie on `.music.apple.com` domain | v1.6.0 | [x] |
| 2.1.3 | Returns `CookieStatus` object with validation result | v1.6.0 | [x] |
| 2.1.4 | Displays expiration in days: "Cookies valid until YYYY-MM-DD (N days remaining)" | v1.6.0 | [x] |
| 2.1.5 | Supports session cookies (no expiration date) | v1.6.0 | [x] |
| 2.1.6 | `--skip-cookie-validation` flag bypasses checks (not recommended) | v1.6.0 | [x] |

### 2.2 Automatic Refresh via Selenium

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | `auto_refresh(backup=True, browser=None)` method orchestrates refresh | v1.6.0 | [x] |
| 2.2.2 | `_extract_with_selenium(browser=None)` launches browser to extract cookies | v1.6.0 | [x] |
| 2.2.3 | Launches browser headless first; falls back to visible mode if login needed | v1.6.0 | [x] |
| 2.2.4 | Login detection: checks for sign-in button presence to determine authentication state | v1.6.0 | [x] |
| 2.2.5 | Converts Selenium cookies to `http.cookiejar.Cookie` objects | v1.6.0 | [x] |
| 2.2.6 | `--auto-refresh-cookies` flag for non-interactive refresh | v1.6.0 | [x] |

### 2.3 Multi-Browser Support

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | `_detect_default_browser()` detects OS default browser | v1.6.0 | [x] |
| 2.3.2 | Platform-specific detection: LaunchServices (macOS), xdg-settings (Linux), registry (Windows) | v1.6.0 | [x] |
| 2.3.3 | Supported browsers: Chrome, Firefox, Safari, Edge | v1.6.0 | [x] |
| 2.3.4 | Automatic fallback to other browsers if default fails | v1.6.0 | [x] |
| 2.3.5 | `webdriver-manager` handles automatic browser driver installation | v1.6.0 | [x] |

### 2.4 Backup Strategy

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Creates `cookies.txt.backup` before overwriting existing cookies | v1.6.0 | [x] |
| 2.4.2 | Backup preserves last known working cookies | v1.6.0 | [x] |
| 2.4.3 | Backup creation controlled by `backup=True` parameter (default) | v1.6.0 | [x] |

### 2.5 Interactive and Non-Interactive Modes

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | Interactive: expired cookies trigger prompt "Attempt automatic cookie refresh? [Y/n]" | v1.6.0 | [x] |
| 2.5.2 | Menu-level checks before batch operations; per-download checks for single operations | v1.6.0 | [x] |
| 2.5.3 | Non-interactive: fails immediately with clear error if cookies invalid (prevents hanging) | v1.6.0 | [x] |

### 2.6 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | No `cookies.txt` file: clear error with instructions to create one | v1.6.0 | [x] |
| 2.6.2 | Malformed cookie file: caught by MozillaCookieJar parser, reported as error | v1.6.0 | [x] |
| 2.6.3 | Browser not installed: automatic fallback to next available browser | v1.6.0 | [x] |
| 2.6.4 | Login required during headless extraction: falls back to visible browser for user interaction | v1.6.0 | [x] |
| 2.6.5 | Selenium not installed: provides manual refresh instructions as fallback | v1.6.0 | [x] |

---

# SRS: USB Synchronization

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Platform auto-detected at startup via `platform.system()` (`IS_MACOS`, `IS_LINUX`, `IS_WINDOWS`) | v1.0.0 | [x] |
| 2.1.2 | Excluded volumes defined in `EXCLUDED_USB_VOLUMES` constant (platform-conditional) | v1.0.0 | [x] |
| 2.1.3 | Single drive auto-selected; multiple drives prompt user selection via `select_usb_drive()` | v1.0.0 | [x] |

### 2.2 Incremental Sync

The `_should_copy_file()` method shall determine whether a file needs copying:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | Compares file size between source and destination | v1.0.0 | [x] |
| 2.2.2 | Compares modification time with 2-second FAT32 tolerance | v1.0.0 | [x] |
| 2.2.3 | Returns True (needs copy) if size differs or mtime is newer beyond tolerance | v1.0.0 | [x] |
| 2.2.4 | Existing up-to-date files are skipped (not re-copied) | v1.0.0 | [x] |

### 2.3 Auto-Eject

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | macOS: automatic eject via `diskutil eject /Volumes/<volume>` | v1.0.0 | [x] |
| 2.3.2 | Linux: automatic unmount via `udisksctl unmount` with fallback to `umount` | v1.0.0 | [x] |
| 2.3.3 | Windows: manual eject via Explorer (automatic eject not implemented; user notified) | v1.0.0 | [x] |

### 2.4 USB Directory

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Default USB subdirectory: `DEFAULT_USB_DIR = "RZR/Music"` | v1.0.0 | [x] |
| 2.4.2 | Configurable via `--usb-dir` flag or `usb_dir` setting in config.yaml | v1.0.0 | [x] |
| 2.4.3 | Creates subdirectory structure on target drive if needed | v1.0.0 | [x] |

### 2.5 Progress Tracking

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | Reports files copied, skipped (up-to-date), and errors | v1.0.0 | [x] |
| 2.5.2 | Integrated into pipeline statistics (`usb_success`, `usb_destination`) | v1.0.0 | [x] |
| 2.5.3 | `--copy-to-usb` flag on `pipeline` command triggers USB sync as final stage | v1.0.0 | [x] |

### 2.6 Standalone Sync

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | `sync-usb` subcommand for standalone USB sync without pipeline | v1.0.0 | [x] |
| 2.6.2 | Optional `source_dir` argument; defaults to entire profile export directory | v1.0.0 | [x] |
| 2.6.3 | Preserves directory structure (flat or nested) on target drive | v1.0.0 | [x] |

### 2.7 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.7.1 | No USB drive detected: clear message to check mount status, with platform-specific instructions | v1.0.0 | [x] |
| 2.7.2 | USB drive removed during sync: file copy error caught and reported | v1.0.0 | [x] |
| 2.7.3 | Eject failure on Linux: `udisksctl` failure falls back to `umount` | v1.0.0 | [x] |

---

# SRS: Configuration, Profiles, and Interactive Menu

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.7.0–v2.3.0

---

## 1. Purpose

Provide a YAML-based configuration system with output profiles that control conversion behavior, and an interactive menu for user-friendly operation without remembering CLI flags.

## 2. Requirements

### 2.1 YAML Configuration (ConfigManager)

The `ConfigManager` class shall manage `config.yaml`:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Reads and writes YAML format via PyYAML library | v1.7.0 | [x] |
| 2.1.2 | Auto-creates default `config.yaml` if missing (`_create_default()`) | v1.7.0 | [x] |
| 2.1.3 | Key methods: `get_setting()`, `update_setting()`, `_save()`, `_load_yaml()` | v1.7.0 | [x] |
| 2.1.4 | Playlist management: `get_playlist_by_key()`, `get_playlist_by_index()`, `add_playlist()`, `update_playlist()`, `remove_playlist()` | v1.7.0 | [x] |
| 2.1.5 | Playlist key lookup is case-insensitive | v1.7.0 | [x] |
| 2.1.6 | Duplicate key detection on `add_playlist()` | v1.7.0 | [x] |

Default settings:

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6
```

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.7 | Default `output_type`: `DEFAULT_OUTPUT_TYPE = "ride-command"` | v1.7.0 | [x] |
| 2.1.8 | Default `usb_dir`: `DEFAULT_USB_DIR = "RZR/Music"` | v1.7.0 | [x] |
| 2.1.9 | Default `workers`: `DEFAULT_WORKERS = min(os.cpu_count(), 6)` | v1.7.0 | [x] |

### 2.2 Settings Precedence

Settings shall follow a three-level precedence chain resolved by `resolve_config_settings()`:

1. **CLI flag** (highest priority)
2. **config.yaml setting**
3. **Hardcoded constant** (lowest priority)

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | Precedence chain implemented and documented | v1.7.0 | [x] |
| 2.2.2 | Each setting independently resolved (e.g., `--output-type` overrides config but config workers still apply) | v1.7.0 | [x] |

### 2.3 Output Profiles (OutputProfile)

The `OutputProfile` dataclass shall define conversion behavior per profile:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | Field: `name` — Profile identifier | v1.7.0 | [x] |
| 2.3.2 | Field: `description` — Human-readable description | v1.7.0 | [x] |
| 2.3.3 | Field: `directory_structure` — `"flat"`, `"nested-artist"`, or `"nested-artist-album"` | v2.3.0 | [x] |
| 2.3.4 | Field: `filename_format` — `"full"` or `"title-only"` | v2.3.0 | [x] |
| 2.3.5 | Field: `id3_version` — `3` (ID3v2.3) or `4` (ID3v2.4) | v1.7.0 | [x] |
| 2.3.6 | Field: `strip_id3v1` — Remove ID3v1 tags (boolean) | v1.7.0 | [x] |
| 2.3.7 | Field: `title_tag_format` — e.g., `"artist_title"` | v1.7.0 | [x] |
| 2.3.8 | Field: `artwork_size` — `>0`=resize to max px, `0`=original, `-1`=strip | v1.7.0 | [x] |
| 2.3.9 | Field: `quality_preset` — Default conversion quality | v1.7.0 | [x] |
| 2.3.10 | Field: `pipeline_album` — `"playlist_name"` or `"original"` | v1.7.0 | [x] |
| 2.3.11 | Field: `pipeline_artist` — `"various"` or `"original"` | v1.7.0 | [x] |

Built-in profiles:

| Profile | ID3 | Artwork | Quality | Album | Artist |
|---------|-----|---------|---------|-------|--------|
| `ride-command` | v2.3 | 100px | lossless | playlist name | "Various" |
| `basic` | v2.4 | original | lossless | original | original |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.12 | `ride-command` profile: default, optimized for Polaris Ride Command infotainment | v1.7.0 | [x] |
| 2.3.13 | `basic` profile: standard MP3 with original tags and artwork preserved | v1.7.0 | [x] |
| 2.3.14 | Profiles stored in `OUTPUT_PROFILES` dictionary | v1.7.0 | [x] |

### 2.4 Profile-Scoped Export Directories

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Export paths scoped by profile: `export/<profile>/<playlist>/` | v1.7.0 | [x] |
| 2.4.2 | `get_export_dir(profile_name, playlist_key=None)` helper builds paths | v1.7.0 | [x] |
| 2.4.3 | Without `playlist_key`: returns `export/<profile>/` | v1.7.0 | [x] |
| 2.4.4 | With `playlist_key`: returns `export/<profile>/<playlist_key>/` | v1.7.0 | [x] |

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | `while True` loop returns to menu after each operation (except X) | v1.7.0 | [x] |
| 2.5.2 | Case-insensitive input handling | v1.7.0 | [x] |
| 2.5.3 | Post-processing prompts for USB copy after pipeline operations | v1.7.0 | [x] |
| 2.5.4 | Summary display with pause-to-review before returning to menu | v1.7.0 | [x] |
| 2.5.5 | Profile change persisted to config.yaml via `update_setting()` | v1.7.0 | [x] |
| 2.5.6 | New URLs saved to config.yaml via `add_playlist()` | v1.7.0 | [x] |

### 2.6 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | Missing `config.yaml`: auto-created with defaults on first run | v1.7.0 | [x] |
| 2.6.2 | Invalid profile name: rejected with error listing valid profiles | v1.7.0 | [x] |
| 2.6.3 | Duplicate playlist key on add: detected and reported | v1.7.0 | [x] |
| 2.6.4 | Empty Enter at menu: treated as Exit (X) | v1.7.0 | [x] |

---

# SRS: Web Dashboard

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v2.0.0–v2.3.0

---

## 1. Purpose

Provide a browser-based dashboard with full feature parity to the CLI, enabling remote and visual operation of all music-porter capabilities with real-time progress streaming.

## 2. Requirements

### 2.1 Flask Application

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | Web dashboard implemented in `web_ui.py` as a Flask application | v2.0.0 | [x] |
| 2.1.2 | Launched via `music-porter web` subcommand with `--host` and `--port` flags | v2.0.0 | [x] |
| 2.1.3 | HTML templates served from `templates/` directory | v2.0.0 | [x] |

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | All 9 pages implemented and accessible | v2.0.0 | [x] |

### 2.3 API Endpoints (~26 endpoints)

**Status & Info:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | `GET /api/status` — System status, cookies, library stats, current profile | v2.0.0 | [x] |
| 2.3.2 | `GET /api/summary` — Export library statistics | v2.0.0 | [x] |
| 2.3.3 | `GET /api/library-stats` — Source music/ directory statistics | v2.0.0 | [x] |

**Cookie Management:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.4 | `GET /api/cookies/browsers` — Available browser list | v2.0.0 | [x] |
| 2.3.5 | `POST /api/cookies/refresh` — Auto-refresh cookies with browser selection | v2.0.0 | [x] |

**Playlist CRUD:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.6 | `GET /api/playlists` — List all playlists | v2.0.0 | [x] |
| 2.3.7 | `POST /api/playlists` — Add new playlist | v2.0.0 | [x] |
| 2.3.8 | `PUT /api/playlists/<key>` — Update existing playlist | v2.0.0 | [x] |
| 2.3.9 | `DELETE /api/playlists/<key>` — Remove playlist | v2.0.0 | [x] |

**Settings:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.10 | `GET /api/settings` — Get all settings, profiles, valid structures/formats | v2.0.0 | [x] |
| 2.3.11 | `POST /api/settings` — Update settings | v2.0.0 | [x] |

**Directory Listings:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.12 | `GET /api/directories/music` — List music/ playlists | v2.0.0 | [x] |
| 2.3.13 | `GET /api/directories/export` — List export/ playlists with file counts (uses rglob for nested dirs) | v2.3.0 | [x] |

**Operations:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.14 | `POST /api/pipeline/run` — Execute full pipeline (accepts `playlist`, `url`, `auto`, `dir_structure`, `filename_format`) | v2.0.0 | [x] |
| 2.3.15 | `POST /api/convert/run` — Convert M4A to MP3 (accepts `dir_structure`, `filename_format`) | v2.0.0 | [x] |
| 2.3.16 | `POST /api/tags/update` — Update album/artist tags | v2.0.0 | [x] |
| 2.3.17 | `POST /api/tags/restore` — Restore original tags | v2.0.0 | [x] |
| 2.3.18 | `POST /api/tags/reset` — Reset tags from source | v2.0.0 | [x] |
| 2.3.19 | `POST /api/cover-art/<action>` — Cover art: embed, extract, update, strip, resize | v2.0.0 | [x] |

**USB:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.20 | `GET /api/usb/drives` — List connected USB drives | v2.0.0 | [x] |
| 2.3.21 | `POST /api/usb/sync` — Sync files to USB | v2.0.0 | [x] |

**Task Management & Streaming:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.22 | `GET /api/tasks` — List all background tasks | v2.0.0 | [x] |
| 2.3.23 | `GET /api/tasks/<task_id>` — Get task details | v2.0.0 | [x] |
| 2.3.24 | `POST /api/tasks/<task_id>/cancel` — Cancel running task | v2.0.0 | [x] |
| 2.3.25 | `GET /api/stream/<task_id>` — SSE live log stream | v2.0.0 | [x] |

### 2.4 Server-Sent Events (SSE) Live Streaming

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | `GET /api/stream/<task_id>` provides real-time log streaming | v2.0.0 | [x] |
| 2.4.2 | Long-polling with 30-second heartbeat timeout | v2.0.0 | [x] |
| 2.4.3 | Message types: `log`, `progress`, `heartbeat`, `done` | v2.0.0 | [x] |
| 2.4.4 | Progress events include: `current`, `total`, `stage`, `percent` | v2.0.0 | [x] |
| 2.4.5 | Sentinel (`None`) in queue indicates task completion | v2.0.0 | [x] |
| 2.4.6 | JSON-formatted SSE data payloads | v2.0.0 | [x] |

### 2.5 Background Task Management

**TaskState dataclass:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | Fields: `id`, `operation`, `description`, `status`, `result`, `error`, `thread`, `cancel_event`, `log_queue`, `started_at`, `finished_at` | v2.0.0 | [x] |
| 2.5.2 | Status values: `pending`, `running`, `completed`, `failed`, `cancelled` | v2.0.0 | [x] |
| 2.5.3 | `elapsed()` method calculates task duration | v2.0.0 | [x] |

**TaskManager class:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.4 | `submit(operation, description, target)` spawns background thread, returns 12-char hex task_id | v2.0.0 | [x] |
| 2.5.5 | `get(task_id)` retrieves TaskState | v2.0.0 | [x] |
| 2.5.6 | `list_all()` returns all tasks as dicts | v2.0.0 | [x] |
| 2.5.7 | `cancel(task_id)` signals cancellation via `threading.Event` | v2.0.0 | [x] |
| 2.5.8 | `is_busy()` checks if any task is currently running | v2.0.0 | [x] |

### 2.6 WebLogger

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | `WebLogger` subclass of `Logger` routes messages to SSE queue | v2.0.0 | [x] |
| 2.6.2 | `_write(level, message)` pushes to queue and writes to log file | v2.0.0 | [x] |
| 2.6.3 | `file_info(message)` sends per-file progress messages | v2.0.0 | [x] |
| 2.6.4 | `_make_progress_callback()` returns throttled progress event closure | v2.0.0 | [x] |
| 2.6.5 | `register_bar()` / `unregister_bar()` are no-ops (progress handled via SSE) | v2.0.0 | [x] |

### 2.7 Feature Parity (CLI <-> Web)

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.7.1 | Every CLI operation has a corresponding API endpoint | v2.0.0 | [x] |
| 2.7.2 | Pipeline, convert, tag, restore, reset, cover-art, USB sync all accessible from web | v2.0.0 | [x] |
| 2.7.3 | Settings and profile management available in web UI | v2.0.0 | [x] |
| 2.7.4 | Library summary and statistics displayed on dashboard | v2.0.0 | [x] |

### 2.8 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.8.1 | Task already running: `submit()` returns None, client informed of busy state | v2.0.0 | [x] |
| 2.8.2 | SSE stream for nonexistent task: handled gracefully | v2.0.0 | [x] |
| 2.8.3 | Concurrent access: TaskManager serializes operations | v2.0.0 | [x] |

---

# SRS: Library Summary and Statistics

**Version:** 1.0  |  **Date:** 2026-02-20  |  **Status:** Complete  |  **Implemented in:** v1.4.0–v2.3.0

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

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | `generate_summary(export_dir, detailed, quick, ...)` main entry point | v1.4.0 | [x] |
| 2.1.2 | `--export-dir` flag for custom export directory | v1.4.0 | [x] |
| 2.1.3 | `--no-library` flag skips source music/ directory scan | v1.4.0 | [x] |
| 2.1.4 | Available in interactive menu as "S. Show library summary" | v1.7.0 | [x] |

### 2.2 Source Library Statistics (MusicLibraryStats)

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | Scans nested `music/Artist/Album/Track.m4a` directory structure | v1.4.0 | [x] |
| 2.2.2 | Tracks: `total_playlists`, `total_files`, `total_size_bytes` | v1.4.0 | [x] |
| 2.2.3 | Cross-references against export: `total_exported`, `total_unconverted` | v1.4.0 | [x] |
| 2.2.4 | `scan_duration` records scan time in seconds | v1.4.0 | [x] |
| 2.2.5 | Per-playlist stats in `playlists` list | v1.4.0 | [x] |

### 2.3 Export Playlist Analysis (PlaylistSummary)

Per-playlist statistics:

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | `file_count` — Number of MP3 files | v1.4.0 | [x] |
| 2.3.2 | `total_size_bytes` — Total playlist size | v1.4.0 | [x] |
| 2.3.3 | `avg_file_size_mb` — Average file size | v1.4.0 | [x] |
| 2.3.4 | `last_modified` — Most recent modification timestamp | v1.4.0 | [x] |
| 2.3.5 | Tag integrity: `sample_files_checked`, `sample_files_with_tags` | v1.4.0 | [x] |
| 2.3.6 | Cover art: `files_with_cover_art`, `files_without_cover_art`, `files_with_original_cover_art`, `files_with_resized_cover_art` | v1.5.0 | [x] |

### 2.4 Aggregate Statistics (LibrarySummaryStatistics)

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | `total_playlists`, `total_files`, `total_size_bytes`, `scan_duration` | v1.4.0 | [x] |
| 2.4.2 | Tag integrity: `sample_size`, `files_with_protection_tags`, `files_missing_protection_tags` | v1.4.0 | [x] |
| 2.4.3 | Cover art: `files_with_cover_art`, `files_without_cover_art` | v1.5.0 | [x] |
| 2.4.4 | `playlists: list[PlaylistSummary]` for per-playlist breakdown | v1.4.0 | [x] |

### 2.5 Tag Integrity Checking

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | `_check_tag_integrity()` scans ALL files (no sampling) | v1.4.0 | [x] |
| 2.5.2 | Checks for TXXX frames: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum` | v1.4.0 | [x] |
| 2.5.3 | Checks for APIC (cover art) frames | v1.5.0 | [x] |
| 2.5.4 | Distinguishes original vs. resized artwork via `OriginalCoverArtHash` TXXX | v1.5.0 | [x] |
| 2.5.5 | Uses same TXXX detection methods as `TaggerManager` for consistency | v1.4.0 | [x] |

### 2.6 Display and Output

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | Per-playlist table with files, tags, size, and last updated date | v1.4.0 | [x] |
| 2.6.2 | Export percentage and unconverted count from source library | v1.4.0 | [x] |
| 2.6.3 | Tag integrity percentages displayed | v1.4.0 | [x] |
| 2.6.4 | Cover art statistics integrated into summary | v1.5.0 | [x] |
| 2.6.5 | Graceful error handling: continues on permission errors, displays partial results | v1.4.0 | [x] |

### 2.7 Web Dashboard Integration

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.7.1 | `GET /api/summary` endpoint returns summary data | v2.0.0 | [x] |
| 2.7.2 | `GET /api/library-stats` endpoint returns source library stats | v2.0.0 | [x] |
| 2.7.3 | Dashboard page displays library stats with sortable table | v2.0.0 | [x] |

### 2.8 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.8.1 | Empty export directory: reports 0 playlists, no error | v1.4.0 | [x] |
| 2.8.2 | Permission errors on individual files: caught and skipped, partial results displayed | v1.4.0 | [x] |
| 2.8.3 | Missing music/ directory: library stats section skipped with message | v1.4.0 | [x] |

---

# SRS: Configurable Output Directory Structure & Filename Format

**Version:** 1.0  |  **Date:** 2026-02-19  |  **Status:** Complete  |  **Implemented in:** v2.3.0

---

## 1. Purpose

Extend the output-type profile system so that each profile controls how converted MP3 files are organized in the output directory (directory structure) and how output files are named (filename format). Users can override these settings via CLI flags or config.yaml.

The `OutputProfile` dataclass already contains `directory_structure` and `filename_format` fields, but both existing profiles (`ride-command` and `basic`) use identical values: `"flat"` and `"artist_title"`. The codebase has placeholder comments indicating planned support for nested directories and alternative filename formats. This feature activates those extension points.

## 2. Requirements

### 2.1 Directory Structures

The system shall support three directory structure modes, configurable per output profile:

| Value | Layout | Example Path |
|-------|--------|-------------|
| `flat` | All MP3s in a single directory | `export/ride-command/Pop_Workout/Artist - Title.mp3` |
| `nested-artist` | Subdirectories per artist | `export/ride-command/Pop_Workout/Taylor Swift/Title.mp3` |
| `nested-artist-album` | Subdirectories per artist and album | `export/ride-command/Pop_Workout/Taylor Swift/1989/Title.mp3` |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.1.1 | `flat` directory structure works (existing behavior) | v2.3.0 | [x] |
| 2.1.2 | `nested-artist` directory structure creates artist subdirectories | v2.3.0 | [x] |
| 2.1.3 | `nested-artist-album` directory structure creates artist/album subdirectories | v2.3.0 | [x] |
| 2.1.4 | Artist and album directory names sanitized using existing `sanitize_filename()` | v2.3.0 | [x] |
| 2.1.5 | Subdirectories created automatically during conversion | v2.3.0 | [x] |
| 2.1.6 | Unknown artist defaults to `"Unknown Artist"` directory name | v2.3.0 | [x] |
| 2.1.7 | Unknown album defaults to `"Unknown Album"` directory name | v2.3.0 | [x] |

### 2.2 Filename Formats

The system shall support two filename format modes, configurable per output profile:

| Value | Pattern | Example |
|-------|---------|---------|
| `full` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title-only` | `Title.mp3` | `Shake It Off.mp3` |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.2.1 | `full` filename format works (existing behavior) | v2.3.0 | [x] |
| 2.2.2 | `title-only` filename format produces title-only filenames | v2.3.0 | [x] |

### 2.3 Configuration

Settings shall follow the existing precedence chain: **CLI flag > config.yaml setting > profile default**

**CLI Flags:**

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `full`, `title-only` | Profile default |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.1 | `--dir-structure` flag added to `pipeline` subcommand | v2.3.0 | [x] |
| 2.3.2 | `--dir-structure` flag added to `convert` subcommand | v2.3.0 | [x] |
| 2.3.3 | `--filename-format` flag added to `pipeline` subcommand | v2.3.0 | [x] |
| 2.3.4 | `--filename-format` flag added to `convert` subcommand | v2.3.0 | [x] |

**config.yaml Settings:**

```yaml
settings:
  dir_structure: flat              # optional
  filename_format: artist_title    # optional
```

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.5 | `dir_structure` setting read from config.yaml | v2.3.0 | [x] |
| 2.3.6 | `filename_format` setting read from config.yaml | v2.3.0 | [x] |
| 2.3.7 | Omitted settings fall back to profile default | v2.3.0 | [x] |

**Profile Defaults:**

Both existing profiles shall retain their current defaults:

| Profile | directory_structure | filename_format |
|---------|-------------------|-----------------|
| `ride-command` | `flat` | `full` |
| `basic` | `flat` | `full` |

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.3.8 | `ride-command` profile defaults unchanged | v2.3.0 | [x] |
| 2.3.9 | `basic` profile defaults unchanged | v2.3.0 | [x] |

### 2.4 Backward Compatibility

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.4.1 | Default behavior identical to current behavior (zero regression) | v2.3.0 | [x] |
| 2.4.2 | `summary` command works with nested export directories | v2.3.0 | [x] |
| 2.4.3 | `cover-art` commands work with nested export directories | v2.3.0 | [x] |
| 2.4.4 | `sync-usb` preserves nested directory structure on target drive | v2.3.0 | [x] |
| 2.4.5 | `tag` command works with nested export directories | v2.3.0 | [x] |
| 2.4.6 | `restore` command works with nested export directories | v2.3.0 | [x] |

### 2.5 Feature Parity (CLI & Web)

**CLI:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.1 | `--dir-structure` flag on `pipeline` command | v2.3.0 | [x] |
| 2.5.2 | `--dir-structure` flag on `convert` command | v2.3.0 | [x] |
| 2.5.3 | `--filename-format` flag on `pipeline` command | v2.3.0 | [x] |
| 2.5.4 | `--filename-format` flag on `convert` command | v2.3.0 | [x] |

**Web Dashboard:**

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.5.5 | Convert page: Directory Layout dropdown | v2.3.0 | [x] |
| 2.5.6 | Convert page: Filename Format dropdown | v2.3.0 | [x] |
| 2.5.7 | Pipeline page: Directory Layout dropdown | v2.3.0 | [x] |
| 2.5.8 | Pipeline page: Filename Format dropdown | v2.3.0 | [x] |
| 2.5.9 | Settings page: Profile comparison table includes directory structure | v2.3.0 | [x] |
| 2.5.10 | Settings page: Profile comparison table includes filename format | v2.3.0 | [x] |
| 2.5.11 | `/api/pipeline/run` accepts `dir_structure` parameter | v2.3.0 | [x] |
| 2.5.12 | `/api/pipeline/run` accepts `filename_format` parameter | v2.3.0 | [x] |
| 2.5.13 | `/api/convert/run` accepts `dir_structure` parameter | v2.3.0 | [x] |
| 2.5.14 | `/api/convert/run` accepts `filename_format` parameter | v2.3.0 | [x] |
| 2.5.15 | `/api/settings` GET returns valid dir_structures and filename_formats lists | v2.3.0 | [x] |
| 2.5.16 | `/api/directories/export` uses rglob for nested directory file counts | v2.3.0 | [x] |
| 2.5.17 | `cover-art embed` subcommand accepts `--dir-structure` and `--filename-format` flags (discovered during testing) | v2.3.0 | [x] |

### 2.6 Display

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.6.1 | Startup banner displays active directory structure | v2.3.0 | [x] |
| 2.6.2 | Startup banner displays active filename format | v2.3.0 | [x] |
| 2.6.3 | Log files record active directory structure and filename format | v2.3.0 | [x] |
| 2.6.4 | `--dry-run` output shows full output path (including subdirectories for nested structures) | v2.3.0 | [x] |
| 2.6.5 | Display values are human-readable via `display_name()` helper with `DISPLAY_NAMES` lookup and title-case fallback | v2.3.0 | [x] |
| 2.6.6 | `full` format displays as "Artist - Title" (custom override via `DISPLAY_NAMES`) | v2.3.0 | [x] |
| 2.6.7 | Other values display as title-cased with spaces (e.g., "Nested Artist Album", "Title Only") | v2.3.0 | [x] |
| 2.6.8 | CLI flag values remain hyphenated (e.g., `nested-artist-album`, `title-only`) | v2.3.0 | [x] |

### 2.7 Validation

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.7.1 | Invalid `--dir-structure` value produces clear error with valid choices and non-zero exit | v2.3.0 | [x] |
| 2.7.2 | Invalid `--filename-format` value produces clear error with valid choices and non-zero exit | v2.3.0 | [x] |
| 2.7.3 | Invalid config.yaml values validated and rejected with clear error | v2.3.0 | [x] |

### 2.8 Testing

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.8.1 | All 6 combinations (3 structures x 2 formats) tested with `--dry-run --verbose` | v2.3.0 | [x] |
| 2.8.2 | Default behavior unchanged (flat + artist_title) | v2.3.0 | [x] |
| 2.8.3 | CLI flag overrides config.yaml | v2.3.0 | [x] |
| 2.8.4 | config.yaml overrides profile default | v2.3.0 | [x] |
| 2.8.5 | `summary` command works with nested export directories | v2.3.0 | [x] |
| 2.8.6 | `cover-art embed` correctly matches files with non-default formats | v2.3.0 | [x] |
| 2.8.7 | `sync-usb` preserves nested structure on target drive | v2.3.0 | [x] |
| 2.8.8 | Filename collisions with `title-only` format handled correctly | v2.3.0 | [x] |
| 2.8.9 | Web UI dropdowns submit correct API parameters | v2.3.0 | [x] |

### 2.9 Edge Cases

| ID | Requirement | Version | Tested |
|----|-------------|---------|--------|
| 2.9.1 | `title-only` format with duplicate titles: skip-if-exists behavior with warning suggesting `full` format | v2.3.0 | [x] |
| 2.9.2 | Artist/album directory names sanitized by `sanitize_filename()` (strips `/\:*?"<>\|`) | v2.3.0 | [x] |

Deeply nested paths: Very long artist + album + title combinations could exceed filesystem path length limits (255 chars on macOS/Linux). This is an existing limitation and is not addressed by this feature.
