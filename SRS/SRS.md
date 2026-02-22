# Completed SRS Documents

---

# SRS: Pipeline

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Orchestrate the multi-stage workflow that downloads Apple Music playlists, converts them to MP3, applies tags, and optionally syncs to USB — coordinating stages, tracking statistics, and handling batch processing across multiple playlists.

## 2. Requirements

### 2.1 Pipeline Orchestration

The `PipelineOrchestrator` class shall coordinate a four-stage workflow:

| Stage | Name | Description |
|-------|------|-------------|
| 1 | `download` | Download playlist from Apple Music via gamdl |
| 2 | `convert` | Convert M4A → MP3 via ffmpeg |
| 3 | `tag` | Apply album/artist tags and embed cover art |
| 4 | `usb-sync` | Copy files to USB drive (optional) |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | Pipeline runs stages sequentially: download → convert → tag → USB sync |
| 2.1.2 | v1.0.0 | [x] | Individual stage failures do not abort the entire pipeline (error recovery) |
| 2.1.3 | v1.0.0 | [x] | Pipeline supports single-playlist (`--playlist`), URL-based (`--url`), and batch (`--auto`) modes |
| 2.1.4 | v1.7.0 | [x] | Post-pipeline USB prompt in interactive mode: offers to copy results to USB after completion |

### 2.2 Batch Processing Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.0.0 | [x] | `PipelineStatistics` tracks `stages_completed`, `stages_failed`, and `stages_skipped` lists |
| 2.2.2 | v1.0.0 | [x] | `PipelineStatistics` aggregates download, conversion, tagging, cover art, and USB stats per playlist |
| 2.2.3 | v1.0.0 | [x] | `PlaylistResult` captures per-playlist results including `failed_stage` indicator and `duration` |
| 2.2.4 | v1.0.0 | [x] | `AggregateStatistics` accumulates results across multiple playlists with `get_cumulative_stats()` |
| 2.2.5 | v1.0.0 | [x] | Comprehensive summary report printed at pipeline completion |

### 2.3 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | Empty playlist directory: conversion reports 0 files found, no error |
| 2.3.2 | v1.0.0 | [x] | gamdl subprocess failure: captured via return code and logged |
| 2.3.3 | v1.0.0 | [x] | Individual file conversion failure during pipeline: logged and counted as error, remaining files processed |

---

# SRS: Download & Authentication

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Download Apple Music playlists via gamdl and manage the cookie-based authentication required for access — including validation, automatic browser-based refresh, multi-browser support, and graceful handling of expired sessions.

## 2. Requirements

### 2.1 Download Module

The `Downloader` class shall download playlists from Apple Music:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | Executes gamdl as a subprocess via `subprocess.Popen()` |
| 2.1.2 | v1.0.0 | [x] | Command: `python -m gamdl --log-level INFO -o <output_path>/ <url>` |
| 2.1.3 | v1.0.0 | [x] | Line-buffered output (`bufsize=1`, `universal_newlines=True`) |
| 2.1.4 | v1.0.0 | [x] | `DownloadStatistics` tracks `playlist_total`, `downloaded`, `skipped`, and `failed` |
| 2.1.5 | v1.0.0 | [x] | Output organized in nested `Artist/Album/Track.m4a` directory structure |

### 2.2 Cookie Validation

The `CookieManager` class shall validate cookies at startup and before downloads:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.6.0 | [x] | Parses `cookies.txt` using `http.cookiejar.MozillaCookieJar` (Netscape format) |
| 2.2.2 | v1.6.0 | [x] | Checks for `media-user-token` cookie on `.music.apple.com` domain |
| 2.2.3 | v1.6.0 | [x] | Returns `CookieStatus` object with validation result |
| 2.2.4 | v1.6.0 | [x] | Displays expiration in days: "Cookies valid until YYYY-MM-DD (N days remaining)" |
| 2.2.5 | v1.6.0 | [x] | Supports session cookies (no expiration date) |
| 2.2.6 | v1.6.0 | [x] | `--skip-cookie-validation` flag bypasses checks (not recommended) |
| 2.2.7 | v1.6.0 | [x] | Cookie status displayed in startup banner: `✓` (valid), `⚠` (invalid/expired), or "No cookies file found" |

### 2.3 Automatic Refresh via Selenium

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.6.0 | [x] | `auto_refresh(backup=True, browser=None)` method orchestrates refresh |
| 2.3.2 | v1.6.0 | [x] | `_extract_with_selenium(browser=None)` launches browser to extract cookies |
| 2.3.3 | v1.6.0 | [x] | Launches browser headless first; falls back to visible mode if login needed |
| 2.3.4 | v1.6.0 | [x] | Login detection: checks for sign-in button presence to determine authentication state |
| 2.3.5 | v1.6.0 | [x] | Converts Selenium cookies to `http.cookiejar.Cookie` objects |
| 2.3.6 | v1.6.0 | [x] | `--auto-refresh-cookies` flag for non-interactive refresh |

### 2.4 Cookie Cleanup

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.6.0 | [x] | `clean_cookies()` removes non-Apple cookies from `cookies.txt` |
| 2.4.2 | v1.6.0 | [x] | Filters by `APPLE_COOKIE_DOMAIN = 'apple.com'` — only retains cookies whose domain contains `apple.com` |
| 2.4.3 | v1.6.0 | [x] | Creates backup before modifying; returns `(success: bool, kept: int, removed: int)` tuple |

### 2.5 Multi-Browser Support

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.6.0 | [x] | `_detect_default_browser()` detects OS default browser |
| 2.5.2 | v1.6.0 | [x] | Platform-specific detection: LaunchServices (macOS), xdg-settings (Linux), registry (Windows) |
| 2.5.3 | v1.6.0 | [x] | Supported browsers: Chrome, Firefox, Safari, Edge |
| 2.5.4 | v1.6.0 | [x] | Automatic fallback to other browsers if default fails |
| 2.5.5 | v1.6.0 | [x] | `webdriver-manager` handles automatic browser driver installation |

### 2.6 Backup Strategy

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.6.0 | [x] | Creates `cookies.txt.backup` before overwriting existing cookies |
| 2.6.2 | v1.6.0 | [x] | Backup preserves last known working cookies |
| 2.6.3 | v1.6.0 | [x] | Backup creation controlled by `backup=True` parameter (default) |

### 2.7 Interactive and Non-Interactive Modes

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v1.6.0 | [x] | Interactive: expired cookies trigger prompt "Attempt automatic cookie refresh? [Y/n]" |
| 2.7.2 | v1.6.0 | [x] | Menu-level checks before batch operations; per-download checks for single operations |
| 2.7.3 | v1.6.0 | [x] | Non-interactive: fails immediately with clear error if cookies invalid (prevents hanging) |

### 2.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v1.6.0 | [x] | No `cookies.txt` file: clear error with instructions to create one |
| 2.8.2 | v1.6.0 | [x] | Malformed cookie file: caught by MozillaCookieJar parser, reported as error |
| 2.8.3 | v1.6.0 | [x] | Browser not installed: automatic fallback to next available browser |
| 2.8.4 | v1.6.0 | [x] | Login required during headless extraction: falls back to visible browser for user interaction |
| 2.8.5 | v1.6.0 | [x] | Selenium not installed: provides manual refresh instructions as fallback |

---

# SRS: Conversion

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Convert downloaded M4A files to MP3 format using ffmpeg, with configurable quality presets, multi-threaded processing, automatic tag transfer, and cover art embedding — producing output files organized according to the active output profile.

## 2. Requirements

### 2.1 M4A-to-MP3 Conversion

The `Converter` class shall convert M4A files to MP3 using ffmpeg:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | Uses `ffmpeg-python` library wrapping the system `ffmpeg` binary |
| 2.1.2 | v1.0.0 | [x] | Codec: `libmp3lame` (LAME MP3 encoder) |
| 2.1.3 | v1.0.0 | [x] | Runs with `quiet=True` to suppress ffmpeg output during batch processing |
| 2.1.4 | v1.0.0 | [x] | Catches `ffmpeg.Error` exceptions; logs details and continues processing remaining files |
| 2.1.5 | v1.0.0 | [x] | Existing MP3s are skipped unless `--force` flag is used |
| 2.1.6 | v1.0.0 | [x] | Force re-conversion increments `overwritten` counter (distinct from `converted`) |

### 2.2 M4A Tag Reading

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.0.0 | [x] | `read_m4a_tags(input_file)` returns `(title, artist, album)` tuple from M4A source |
| 2.2.2 | v1.0.0 | [x] | Default values for missing tags: `"Unknown Title"`, `"Unknown Artist"`, `"Unknown Album"` |
| 2.2.3 | v1.0.0 | [x] | M4A tag constants: `M4A_TAG_TITLE = '\xa9nam'`, `M4A_TAG_ARTIST = '\xa9ART'`, `M4A_TAG_ALBUM = '\xa9alb'`, `M4A_TAG_COVER = 'covr'` |
| 2.2.4 | v1.5.0 | [x] | `read_m4a_cover_art(input_file)` returns `(cover_data: bytes, mime_type: str)` or `(None, None)` |

### 2.3 Output File Naming and Paths

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | `sanitize_filename(name)` removes invalid characters: `/\:*?"<>\|` |
| 2.3.2 | v2.3.0 | [x] | `_build_output_filename(artist, title)` constructs name based on profile's `filename_format` field |
| 2.3.3 | v2.3.0 | [x] | `_build_output_path(base_path, filename, artist, album)` constructs path based on profile's `directory_structure` field |
| 2.3.4 | v2.3.0 | [x] | Directory creation with `parents=True, exist_ok=True` for nested structures |
| 2.3.5 | v2.3.0 | [x] | Filename collision hint when skipping in non-`full` format: suggests using `full` format |

### 2.4 Cover Art Embedding During Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.5.0 | [x] | Cover art automatically extracted from source M4A and embedded into MP3 during conversion |
| 2.4.2 | v1.5.0 | [x] | APIC frame constants: `APIC_MIME_JPEG = "image/jpeg"`, `APIC_MIME_PNG = "image/png"`, `APIC_TYPE_FRONT_COVER = 3` |
| 2.4.3 | v1.7.0 | [x] | Cover art resized per profile's `artwork_size` setting during conversion via `resize_cover_art_bytes()` |
| 2.4.4 | v1.5.0 | [x] | `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding |
| 2.4.5 | v1.0.0 | [x] | Tag application occurs immediately after conversion (in same worker thread) |

### 2.5 Quality Presets

Configurable quality presets via `QUALITY_PRESETS` dictionary and `--preset` flag:

| Preset | Mode | Value | Est. Bitrate |
|--------|------|-------|--------------|
| `lossless` | CBR | `b:a 320k` | 320 kbps |
| `high` | VBR | `q:a 2` | ~190–250 kbps |
| `medium` | VBR | `q:a 4` | ~165–210 kbps |
| `low` | VBR | `q:a 6` | ~115–150 kbps |
| `custom` | VBR | `q:a 0–9` | Variable |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.0.0 | [x] | Default preset: `lossless` (320 kbps CBR) via `DEFAULT_QUALITY_PRESET` constant |
| 2.5.2 | v1.0.0 | [x] | `--preset` flag accepts `lossless`, `high`, `medium`, `low`, `custom` |
| 2.5.3 | v1.0.0 | [x] | Custom VBR requires both `--preset custom` and `--quality 0-9` |
| 2.5.4 | v1.0.0 | [x] | `_get_quality_settings(preset)` resolves preset name to ffmpeg parameters |
| 2.5.5 | v1.0.0 | [x] | `--preset` flag available on both `convert` and `pipeline` subcommands |

### 2.6 Multi-Threaded Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.0.0 | [x] | Uses `concurrent.futures.ThreadPoolExecutor` for parallel file conversion |
| 2.6.2 | v1.0.0 | [x] | Default workers: `min(os.cpu_count(), MAX_DEFAULT_WORKERS)` where `MAX_DEFAULT_WORKERS = 6` |
| 2.6.3 | v1.0.0 | [x] | Configurable via `--workers N` global flag |
| 2.6.4 | v1.0.0 | [x] | `ConversionStatistics` is thread-safe with `threading.Lock` |
| 2.6.5 | v1.0.0 | [x] | Atomic progress counter via `next_progress()` method |
| 2.6.6 | v1.0.0 | [x] | `ConversionStatistics` tracks: `total_found`, `converted`, `overwritten`, `skipped`, `errors` |

### 2.7 Conversion Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v1.0.0 | [x] | Conversion progress format: `[count/total] Action: filename` (e.g., `[3/15] Converting: Artist - Title.mp3`) |

### 2.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v1.0.0 | [x] | Individual file conversion failure: logged and counted as error, remaining files processed |
| 2.8.2 | v1.0.0 | [x] | Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics |
| 2.8.3 | v1.5.0 | [x] | M4A source has no cover art: MP3 created without APIC frame, logged as warning |

---

# SRS: Tag Management

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

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

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | `_txxx_exists(tags, desc_name)` checks for frame existence by iterating `tags.values()` with `isinstance(frame, TXXX)` |
| 2.1.2 | v1.0.0 | [x] | `_get_txxx(tags, desc_name)` retrieves frame value by iterating frame types (not string key indexing) |
| 2.1.3 | v1.0.0 | [x] | `save_original_tag(tags, tag_key, tag_name, current_value, label, logger, verbose)` enforces hard-gate: skips write if `_txxx_exists()` returns True; returns `(value, was_newly_stored)` tuple |
| 2.1.4 | v1.0.0 | [x] | Once written, TXXX protection frames are NEVER overwritten (except via explicit `reset` command) |

### 2.2 Tag Operations

The `TaggerManager` class shall support three tag operations:

**Update** (`update_tags()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.0.0 | [x] | Updates album and/or artist tags on MP3 files |
| 2.2.2 | v1.0.0 | [x] | Saves original values to TXXX frames before overwriting (hard-gate protected) |
| 2.2.3 | v1.0.0 | [x] | `--album` and `--artist` flags for specifying new values |
| 2.2.4 | v1.0.0 | [x] | Statistics tracked per-field: `title_updated`, `album_updated`, `artist_updated` |

**Restore** (`restore_tags()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.5 | v1.0.0 | [x] | Restores tags from TXXX protection frames to standard ID3 fields |
| 2.2.6 | v1.0.0 | [x] | `--all` flag restores all tags; `--album`, `--title`, `--artist` for selective restore |
| 2.2.7 | v1.0.0 | [x] | Reports missing TXXX frames (tracks `*_missing` counters) |
| 2.2.8 | v1.0.0 | [x] | Statistics tracked: `title_restored`, `album_restored`, `artist_restored` |

**Reset** (`reset_tags_from_source()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.9 | v1.0.0 | [x] | Overwrites TXXX protection frames from source M4A files (destructive) |
| 2.2.10 | v1.0.0 | [x] | Requires confirmation prompt before proceeding |
| 2.2.11 | v1.0.0 | [x] | Takes both `input_dir` (M4A source) and `output_dir` (MP3 target) parameters |
| 2.2.12 | v1.7.0 | [x] | Reset tag matching maps M4A files to MP3s using profile-aware filename and directory structure |

### 2.3 Title Formatting

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | `_strip_artist_prefix(title, artist)` prevents double-compounding of "Artist - " prefix |
| 2.3.2 | v1.0.0 | [x] | New titles built from protected originals: `f"{OriginalArtist} - {OriginalTitle}"` |
| 2.3.3 | v1.7.0 | [x] | Title format controlled by profile's `title_tag_format` field (`"artist_title"`) |

### 2.4 ID3 Version and Cleanup

Default cleanup options applied via `_apply_cleanup()`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.0.0 | [x] | ID3v2.3 output by default (older device compatibility), configurable per profile |
| 2.4.2 | v1.0.0 | [x] | ID3v1 tags stripped by default (`strip_id3v1: True`) |
| 2.4.3 | v1.0.0 | [x] | Duplicate frames automatically removed via key iteration |
| 2.4.4 | v1.0.0 | [x] | Overrides available: `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates` |
| 2.4.5 | v1.7.0 | [x] | Profile `id3_version` field: `3` for ID3v2.3, `4` for ID3v2.4 |
| 2.4.6 | v1.0.0 | [x] | `_apply_cleanup()` keeps only `TIT2`, `TPE1`, `TALB`, `APIC`, and TXXX preservation frames; removes all other frames |
| 2.4.7 | v1.0.0 | [x] | Allowed TXXX descriptions: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`, `OriginalCoverArtHash` |

### 2.5 Tag Statistics

`TagStatistics` class tracks per-field counters:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.0.0 | [x] | Updated: `title_updated`, `album_updated`, `artist_updated` |
| 2.5.2 | v1.0.0 | [x] | Stored (TXXX): `title_stored`, `artist_stored`, `album_stored` |
| 2.5.3 | v1.0.0 | [x] | Protected (skipped): `title_protected`, `artist_protected`, `album_protected` |
| 2.5.4 | v1.0.0 | [x] | Restored: `title_restored`, `artist_restored`, `album_restored` |
| 2.5.5 | v1.0.0 | [x] | Missing: `title_missing`, `artist_missing`, `album_missing` |

### 2.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.0.0 | [x] | Mutagen key indexing inconsistency after save/reload: mitigated by iterating `tags.values()` instead of string key lookup |
| 2.6.2 | v1.0.0 | [x] | Files without existing tags: creates new ID3 tag structure before writing |
| 2.6.3 | v1.0.0 | [x] | Multiple script runs: TXXX frames preserved across unlimited update cycles |
| 2.6.4 | v1.0.0 | [x] | Reset confirmation: requires interactive confirmation to prevent accidental TXXX overwrite |

---

# SRS: Cover Art

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.5.0–v2.3.0

---

## 1. Purpose

Manage cover art across the MP3 library — embedding art from M4A sources during conversion, and providing standalone operations to embed, extract, update, strip, and resize artwork on existing MP3 files.

## 2. Requirements

### 2.1 Automatic Embedding During Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.5.0 | [x] | Cover art automatically extracted from source M4A and embedded into MP3 during conversion |
| 2.1.2 | v1.5.0 | [x] | APIC frame with type `APIC_TYPE_FRONT_COVER` (3) and appropriate MIME type (`image/jpeg` or `image/png`) |
| 2.1.3 | v1.5.0 | [x] | SHA-256 hash prefix (first 16 chars) stored in `TXXX:OriginalCoverArtHash` with hard-gate protection |
| 2.1.4 | v1.5.0 | [x] | `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding |
| 2.1.5 | v1.7.0 | [x] | Profile-based resizing: `artwork_size > 0` resizes to max pixels, `0` embeds original, `-1` strips artwork |

### 2.2 Cover Art Subcommands

The `CoverArtManager` class shall support five operations via `cover-art` subcommand:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.5.0 | [x] | **embed:** Embeds cover art from matching M4A source files into existing MP3s |
| 2.2.2 | v1.5.0 | [x] | **embed:** Auto-derives source directory from `export/` → `music/` path mapping |
| 2.2.3 | v1.5.0 | [x] | **embed:** `--source` flag overrides auto-derivation |
| 2.2.4 | v1.5.0 | [x] | **embed:** `--all` flag processes all configured playlists |
| 2.2.5 | v1.5.0 | [x] | **embed:** `--force` flag re-embeds even if art already exists |
| 2.2.6 | v2.3.0 | [x] | **embed:** Accepts `--dir-structure` and `--filename-format` flags for non-default layouts |
| 2.2.7 | v1.5.0 | [x] | **extract:** Saves embedded cover art from MP3 files to image files |
| 2.2.8 | v1.5.0 | [x] | **extract:** Default output directory: `<playlist>/cover-art/` |
| 2.2.9 | v1.5.0 | [x] | **extract:** `--output` flag for custom output directory |
| 2.2.10 | v1.5.0 | [x] | **update:** Replaces cover art on all MP3s from a single image file |
| 2.2.11 | v1.5.0 | [x] | **update:** `--image` flag (required) accepts `.jpg`, `.jpeg`, `.png` files |
| 2.2.12 | v1.5.0 | [x] | **update:** Detects MIME type from file extension |
| 2.2.13 | v1.5.0 | [x] | **strip:** Removes all APIC frames from MP3s to reduce file size |
| 2.2.14 | v1.5.0 | [x] | **resize:** Resizes existing embedded cover art to specified max pixel size |
| 2.2.15 | v1.7.0 | [x] | **resize:** Available as interactive menu option (R) |

### 2.3 Pillow Integration

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.5.0 | [x] | Uses `PIL.Image` from Pillow library for image processing |
| 2.3.2 | v1.5.0 | [x] | Resize method: `img.thumbnail((max_size, max_size), Image.LANCZOS)` (high-quality downsampling) |
| 2.3.3 | v1.5.0 | [x] | Supports PNG and JPEG with proper color mode conversion (RGB for JPEG) |
| 2.3.4 | v1.7.0 | [x] | `ride-command` profile: 100px max artwork; `basic` profile: original size |
| 2.3.5 | v1.5.0 | [x] | `resize_cover_art_bytes(image_data, max_size, mime_type)` returns original data unchanged if image already fits within `max_size` |
| 2.3.6 | v1.5.0 | [x] | PIL lazy-imported to avoid startup cost (imported inside `resize_cover_art_bytes()`) |
| 2.3.7 | v1.5.0 | [x] | Cover art hash: SHA-256 of art bytes, first 16 chars stored in `TXXX:OriginalCoverArtHash` |

### 2.4 Cover Art Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.5.0 | [x] | Per-playlist tracking: `files_with_cover_art`, `files_without_cover_art` |
| 2.4.2 | v1.5.0 | [x] | Original vs. resized tracking: `files_with_original_cover_art`, `files_with_resized_cover_art` |
| 2.4.3 | v1.5.0 | [x] | Integrated into library summary display |

### 2.5 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.5.0 | [x] | M4A source has no cover art: MP3 created without APIC frame, logged as warning |
| 2.5.2 | v1.5.0 | [x] | Source directory not found: clear error message with path displayed |
| 2.5.3 | v1.5.0 | [x] | Unsupported image format in `--image`: rejected with error |

---

# SRS: USB Sync

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

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

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | Platform auto-detected at startup via `platform.system()` (`IS_MACOS`, `IS_LINUX`, `IS_WINDOWS`) |
| 2.1.2 | v1.0.0 | [x] | Excluded volumes defined in `EXCLUDED_USB_VOLUMES` constant (platform-conditional) |
| 2.1.3 | v1.0.0 | [x] | Single drive auto-selected; multiple drives prompt user selection via `select_usb_drive()` |

### 2.2 Incremental Sync

The `_should_copy_file()` method shall determine whether a file needs copying:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.0.0 | [x] | Compares file size between source and destination |
| 2.2.2 | v1.0.0 | [x] | Compares modification time with 2-second FAT32 tolerance |
| 2.2.3 | v1.0.0 | [x] | Returns True (needs copy) if size differs or mtime is newer beyond tolerance |
| 2.2.4 | v1.0.0 | [x] | Existing up-to-date files are skipped (not re-copied) |

### 2.3 Auto-Eject

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | macOS: automatic eject via `diskutil eject /Volumes/<volume>` |
| 2.3.2 | v1.0.0 | [x] | Linux: automatic unmount via `udisksctl unmount` with fallback to `umount` |
| 2.3.3 | v1.0.0 | [x] | Windows: manual eject via Explorer (automatic eject not implemented; user notified) |

### 2.4 USB Directory

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.0.0 | [x] | Default USB subdirectory: `DEFAULT_USB_DIR = "RZR/Music"` |
| 2.4.2 | v1.0.0 | [x] | Configurable via `--usb-dir` flag or `usb_dir` setting in config.yaml |
| 2.4.3 | v1.0.0 | [x] | Creates subdirectory structure on target drive if needed |

### 2.5 Progress Tracking

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.0.0 | [x] | Reports files copied, skipped (up-to-date), and errors |
| 2.5.2 | v1.0.0 | [x] | Integrated into pipeline statistics (`usb_success`, `usb_destination`) |
| 2.5.3 | v1.0.0 | [x] | `--copy-to-usb` flag on `pipeline` command triggers USB sync as final stage |

### 2.6 Standalone Sync

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.0.0 | [x] | `sync-usb` subcommand for standalone USB sync without pipeline |
| 2.6.2 | v1.0.0 | [x] | Optional `source_dir` argument; defaults to entire profile export directory |
| 2.6.3 | v1.0.0 | [x] | Preserves directory structure (flat or nested) on target drive |

### 2.7 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v1.0.0 | [x] | No USB drive detected: clear message to check mount status, with platform-specific instructions |
| 2.7.2 | v1.0.0 | [x] | USB drive removed during sync: file copy error caught and reported |
| 2.7.3 | v1.0.0 | [x] | Eject failure on Linux: `udisksctl` failure falls back to `umount` |

---

# SRS: Library Summary

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.4.0–v2.3.0

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

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.4.0 | [x] | `generate_summary(export_dir, detailed, quick, ...)` main entry point |
| 2.1.2 | v1.4.0 | [x] | `--export-dir` flag for custom export directory |
| 2.1.3 | v1.4.0 | [x] | `--no-library` flag skips source music/ directory scan |
| 2.1.4 | v1.7.0 | [x] | Available in interactive menu as "S. Show library summary" |

### 2.2 Source Library Statistics (MusicLibraryStats)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.4.0 | [x] | Scans nested `music/Artist/Album/Track.m4a` directory structure |
| 2.2.2 | v1.4.0 | [x] | Tracks: `total_playlists`, `total_files`, `total_size_bytes` |
| 2.2.3 | v1.4.0 | [x] | Cross-references against export: `total_exported`, `total_unconverted` |
| 2.2.4 | v1.4.0 | [x] | `scan_duration` records scan time in seconds |
| 2.2.5 | v1.4.0 | [x] | Per-playlist stats in `playlists` list |

### 2.3 Export Playlist Analysis (PlaylistSummary)

Per-playlist statistics:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.4.0 | [x] | `file_count` — Number of MP3 files |
| 2.3.2 | v1.4.0 | [x] | `total_size_bytes` — Total playlist size |
| 2.3.3 | v1.4.0 | [x] | `avg_file_size_mb` — Average file size |
| 2.3.4 | v1.4.0 | [x] | `last_modified` — Most recent modification timestamp |
| 2.3.5 | v1.4.0 | [x] | Tag integrity: `sample_files_checked`, `sample_files_with_tags` |
| 2.3.6 | v1.5.0 | [x] | Cover art: `files_with_cover_art`, `files_without_cover_art`, `files_with_original_cover_art`, `files_with_resized_cover_art` |

### 2.4 Aggregate Statistics (LibrarySummaryStatistics)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.4.0 | [x] | `total_playlists`, `total_files`, `total_size_bytes`, `scan_duration` |
| 2.4.2 | v1.4.0 | [x] | Tag integrity: `sample_size`, `files_with_protection_tags`, `files_missing_protection_tags` |
| 2.4.3 | v1.5.0 | [x] | Cover art: `files_with_cover_art`, `files_without_cover_art` |
| 2.4.4 | v1.4.0 | [x] | `playlists: list[PlaylistSummary]` for per-playlist breakdown |

### 2.5 Tag Integrity Checking

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.4.0 | [x] | `_check_tag_integrity()` scans ALL files (no sampling) |
| 2.5.2 | v1.4.0 | [x] | Checks for TXXX frames: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum` |
| 2.5.3 | v1.5.0 | [x] | Checks for APIC (cover art) frames |
| 2.5.4 | v1.5.0 | [x] | Distinguishes original vs. resized artwork via `OriginalCoverArtHash` TXXX |
| 2.5.5 | v1.4.0 | [x] | Uses same TXXX detection methods as `TaggerManager` for consistency |

### 2.6 Display and Output

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.4.0 | [x] | Per-playlist table with files, tags, size, and last updated date |
| 2.6.2 | v1.4.0 | [x] | Export percentage and unconverted count from source library |
| 2.6.3 | v1.4.0 | [x] | Tag integrity percentages displayed |
| 2.6.4 | v1.5.0 | [x] | Cover art statistics integrated into summary |
| 2.6.5 | v1.4.0 | [x] | Graceful error handling: continues on permission errors, displays partial results |

### 2.7 Web Dashboard Integration

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v2.0.0 | [x] | `GET /api/summary` endpoint returns summary data |
| 2.7.2 | v2.0.0 | [x] | `GET /api/library-stats` endpoint returns source library stats |
| 2.7.3 | v2.0.0 | [x] | Dashboard page displays library stats with sortable table |

### 2.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v1.4.0 | [x] | Empty export directory: reports 0 playlists, no error |
| 2.8.2 | v1.4.0 | [x] | Permission errors on individual files: caught and skipped, partial results displayed |
| 2.8.3 | v1.4.0 | [x] | Missing music/ directory: library stats section skipped with message |

---

# SRS: Configuration

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.7.0–v2.3.0

---

## 1. Purpose

Provide a YAML-based configuration system, output profiles that control conversion behavior and tag handling, configurable output directory structures and filename formats, and all associated constants and resolution logic.

## 2. Requirements

### 2.1 YAML Configuration (ConfigManager)

The `ConfigManager` class shall manage `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.7.0 | [x] | Reads and writes YAML format via PyYAML library |
| 2.1.2 | v1.7.0 | [x] | Auto-creates default `config.yaml` if missing (`_create_default()`) |
| 2.1.3 | v1.7.0 | [x] | Key methods: `get_setting()`, `update_setting()`, `_save()`, `_load_yaml()` |
| 2.1.4 | v1.7.0 | [x] | Playlist management: `get_playlist_by_key()`, `get_playlist_by_index()`, `add_playlist()`, `update_playlist()`, `remove_playlist()` |
| 2.1.5 | v1.7.0 | [x] | Playlist key lookup is case-insensitive |
| 2.1.6 | v1.7.0 | [x] | Duplicate key detection on `add_playlist()` |

Default settings:

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.7 | v1.7.0 | [x] | Default `output_type`: `DEFAULT_OUTPUT_TYPE = "ride-command"` |
| 2.1.8 | v1.7.0 | [x] | Default `usb_dir`: `DEFAULT_USB_DIR = "RZR/Music"` |
| 2.1.9 | v1.7.0 | [x] | Default `workers`: `DEFAULT_WORKERS = min(os.cpu_count(), 6)` |

### 2.2 Settings Precedence

Settings shall follow a three-level precedence chain resolved by `resolve_config_settings()`:

1. **CLI flag** (highest priority)
2. **config.yaml setting**
3. **Hardcoded constant** (lowest priority)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.7.0 | [x] | Precedence chain implemented and documented |
| 2.2.2 | v1.7.0 | [x] | Each setting independently resolved (e.g., `--output-type` overrides config but config workers still apply) |
| 2.2.3 | v2.3.0 | [x] | `resolve_config_settings(args, config)` returns 5-tuple: `(output_type, usb_dir, workers, dir_structure, filename_format)` |
| 2.2.4 | v1.0.0 | [x] | `resolve_quality_preset(args, logger, output_profile)` handles preset + custom quality validation; returns resolved preset string or falls back to profile default |

### 2.3 Default Constants

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | `DEFAULT_MUSIC_DIR = "music"` |
| 2.3.2 | v1.0.0 | [x] | `DEFAULT_EXPORT_DIR = "export"` |
| 2.3.3 | v1.0.0 | [x] | `DEFAULT_LOG_DIR = "logs"` |
| 2.3.4 | v1.7.0 | [x] | `DEFAULT_CONFIG_FILE = "config.yaml"` |
| 2.3.5 | v1.6.0 | [x] | `DEFAULT_COOKIES = "cookies.txt"` |
| 2.3.6 | v1.0.0 | [x] | `DEFAULT_CLEANUP_OPTIONS` dictionary: `remove_id3v1: True`, `use_id3v23: True`, `remove_duplicates: True` |

### 2.4 Output Profiles (OutputProfile)

The `OutputProfile` dataclass shall define conversion behavior per profile:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.7.0 | [x] | Field: `name` — Profile identifier |
| 2.4.2 | v1.7.0 | [x] | Field: `description` — Human-readable description |
| 2.4.3 | v2.3.0 | [x] | Field: `directory_structure` — `"flat"`, `"nested-artist"`, or `"nested-artist-album"` |
| 2.4.4 | v2.3.0 | [x] | Field: `filename_format` — `"full"` or `"title-only"` |
| 2.4.5 | v1.7.0 | [x] | Field: `id3_version` — `3` (ID3v2.3) or `4` (ID3v2.4) |
| 2.4.6 | v1.7.0 | [x] | Field: `strip_id3v1` — Remove ID3v1 tags (boolean) |
| 2.4.7 | v1.7.0 | [x] | Field: `title_tag_format` — e.g., `"artist_title"` |
| 2.4.8 | v1.7.0 | [x] | Field: `artwork_size` — `>0`=resize to max px, `0`=original, `-1`=strip |
| 2.4.9 | v1.7.0 | [x] | Field: `quality_preset` — Default conversion quality |
| 2.4.10 | v1.7.0 | [x] | Field: `pipeline_album` — `"playlist_name"` or `"original"` |
| 2.4.11 | v1.7.0 | [x] | Field: `pipeline_artist` — `"various"` or `"original"` |
| 2.4.12 | v2.3.0 | [x] | Profile override via `dataclasses.replace()` for CLI flag overrides (immutable base profiles) |

Built-in profiles:

| Profile | ID3 | Artwork | Quality | Album | Artist |
|---------|-----|---------|---------|-------|--------|
| `ride-command` | v2.3 | 100px | lossless | playlist name | "Various" |
| `basic` | v2.4 | original | lossless | original | original |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.13 | v1.7.0 | [x] | `ride-command` profile: default, optimized for Polaris Ride Command infotainment |
| 2.4.14 | v1.7.0 | [x] | `basic` profile: standard MP3 with original tags and artwork preserved |
| 2.4.15 | v1.7.0 | [x] | Profiles stored in `OUTPUT_PROFILES` dictionary |

### 2.5 Profile-Scoped Export Directories

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.7.0 | [x] | Export paths scoped by profile: `export/<profile>/<playlist>/` |
| 2.5.2 | v1.7.0 | [x] | `get_export_dir(profile_name, playlist_key=None)` helper builds paths |
| 2.5.3 | v1.7.0 | [x] | Without `playlist_key`: returns `export/<profile>/` |
| 2.5.4 | v1.7.0 | [x] | With `playlist_key`: returns `export/<profile>/<playlist_key>/` |

### 2.6 Directory Structures

The system shall support three directory structure modes, configurable per output profile:

| Value | Layout | Example Path |
|-------|--------|-------------|
| `flat` | All MP3s in a single directory | `export/ride-command/Pop_Workout/Artist - Title.mp3` |
| `nested-artist` | Subdirectories per artist | `export/ride-command/Pop_Workout/Taylor Swift/Title.mp3` |
| `nested-artist-album` | Subdirectories per artist and album | `export/ride-command/Pop_Workout/Taylor Swift/1989/Title.mp3` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v2.3.0 | [x] | `flat` directory structure works (existing behavior) |
| 2.6.2 | v2.3.0 | [x] | `nested-artist` directory structure creates artist subdirectories |
| 2.6.3 | v2.3.0 | [x] | `nested-artist-album` directory structure creates artist/album subdirectories |
| 2.6.4 | v2.3.0 | [x] | Artist and album directory names sanitized using existing `sanitize_filename()` |
| 2.6.5 | v2.3.0 | [x] | Subdirectories created automatically during conversion |
| 2.6.6 | v2.3.0 | [x] | Unknown artist defaults to `"Unknown Artist"` directory name |
| 2.6.7 | v2.3.0 | [x] | Unknown album defaults to `"Unknown Album"` directory name |
| 2.6.8 | v2.3.0 | [x] | `VALID_DIR_STRUCTURES = ("flat", "nested-artist", "nested-artist-album")` constant tuple |

### 2.7 Filename Formats

The system shall support two filename format modes, configurable per output profile:

| Value | Pattern | Example |
|-------|---------|---------|
| `full` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title-only` | `Title.mp3` | `Shake It Off.mp3` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v2.3.0 | [x] | `full` filename format works (existing behavior) |
| 2.7.2 | v2.3.0 | [x] | `title-only` filename format produces title-only filenames |
| 2.7.3 | v2.3.0 | [x] | `VALID_FILENAME_FORMATS = ("full", "title-only")` constant tuple |

### 2.8 Output Format CLI Flags

Settings shall follow the existing precedence chain: **CLI flag > config.yaml setting > profile default**

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `full`, `title-only` | Profile default |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v2.3.0 | [x] | `--dir-structure` flag added to `pipeline` subcommand |
| 2.8.2 | v2.3.0 | [x] | `--dir-structure` flag added to `convert` subcommand |
| 2.8.3 | v2.3.0 | [x] | `--filename-format` flag added to `pipeline` subcommand |
| 2.8.4 | v2.3.0 | [x] | `--filename-format` flag added to `convert` subcommand |

**config.yaml Settings:**

```yaml
settings:
  dir_structure: flat              # optional
  filename_format: artist_title    # optional
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.5 | v2.3.0 | [x] | `dir_structure` setting read from config.yaml |
| 2.8.6 | v2.3.0 | [x] | `filename_format` setting read from config.yaml |
| 2.8.7 | v2.3.0 | [x] | Omitted settings fall back to profile default |

**Profile Defaults:**

Both existing profiles shall retain their current defaults:

| Profile | directory_structure | filename_format |
|---------|-------------------|-----------------|
| `ride-command` | `flat` | `full` |
| `basic` | `flat` | `full` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.8 | v2.3.0 | [x] | `ride-command` profile defaults unchanged |
| 2.8.9 | v2.3.0 | [x] | `basic` profile defaults unchanged |

### 2.9 Display Names

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.9.1 | v2.3.0 | [x] | `display_name(value)` helper converts flag values to human-readable names via `DISPLAY_NAMES` lookup with title-case fallback |
| 2.9.2 | v2.3.0 | [x] | `full` format displays as "Artist - Title" (custom override via `DISPLAY_NAMES`) |
| 2.9.3 | v2.3.0 | [x] | Other values display as title-cased with spaces (e.g., "Nested Artist Album", "Title Only") |
| 2.9.4 | v2.3.0 | [x] | CLI flag values remain hyphenated (e.g., `nested-artist-album`, `title-only`) |

### 2.10 Backward Compatibility

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.10.1 | v2.3.0 | [x] | Default behavior identical to current behavior (zero regression) |
| 2.10.2 | v2.3.0 | [x] | `summary` command works with nested export directories |
| 2.10.3 | v2.3.0 | [x] | `cover-art` commands work with nested export directories |
| 2.10.4 | v2.3.0 | [x] | `sync-usb` preserves nested directory structure on target drive |
| 2.10.5 | v2.3.0 | [x] | `tag` command works with nested export directories |
| 2.10.6 | v2.3.0 | [x] | `restore` command works with nested export directories |

### 2.11 Output Format Feature Parity (CLI & Web)

**CLI:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.11.1 | v2.3.0 | [x] | `--dir-structure` flag on `pipeline` command |
| 2.11.2 | v2.3.0 | [x] | `--dir-structure` flag on `convert` command |
| 2.11.3 | v2.3.0 | [x] | `--filename-format` flag on `pipeline` command |
| 2.11.4 | v2.3.0 | [x] | `--filename-format` flag on `convert` command |

**Web Dashboard:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.11.5 | v2.3.0 | [x] | Convert page: Directory Layout dropdown |
| 2.11.6 | v2.3.0 | [x] | Convert page: Filename Format dropdown |
| 2.11.7 | v2.3.0 | [x] | Pipeline page: Directory Layout dropdown |
| 2.11.8 | v2.3.0 | [x] | Pipeline page: Filename Format dropdown |
| 2.11.9 | v2.3.0 | [x] | Settings page: Profile comparison table includes directory structure |
| 2.11.10 | v2.3.0 | [x] | Settings page: Profile comparison table includes filename format |
| 2.11.11 | v2.3.0 | [x] | `/api/pipeline/run` accepts `dir_structure` parameter |
| 2.11.12 | v2.3.0 | [x] | `/api/pipeline/run` accepts `filename_format` parameter |
| 2.11.13 | v2.3.0 | [x] | `/api/convert/run` accepts `dir_structure` parameter |
| 2.11.14 | v2.3.0 | [x] | `/api/convert/run` accepts `filename_format` parameter |
| 2.11.15 | v2.3.0 | [x] | `/api/settings` GET returns valid `dir_structures` and `filename_formats` lists |
| 2.11.16 | v2.3.0 | [x] | `/api/directories/export` uses `rglob` for nested directory file counts |
| 2.11.17 | v2.3.0 | [x] | `cover-art embed` subcommand accepts `--dir-structure` and `--filename-format` flags |

### 2.12 Output Format Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.12.1 | v2.3.0 | [x] | Startup banner displays active directory structure |
| 2.12.2 | v2.3.0 | [x] | Startup banner displays active filename format |
| 2.12.3 | v2.3.0 | [x] | Log files record active directory structure and filename format |
| 2.12.4 | v2.3.0 | [x] | `--dry-run` output shows full output path (including subdirectories for nested structures) |

### 2.13 Output Format Validation

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.13.1 | v2.3.0 | [x] | Invalid `--dir-structure` value produces clear error with valid choices and non-zero exit |
| 2.13.2 | v2.3.0 | [x] | Invalid `--filename-format` value produces clear error with valid choices and non-zero exit |
| 2.13.3 | v2.3.0 | [x] | Invalid config.yaml values validated and rejected with clear error |

### 2.14 Output Format Testing

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.14.1 | v2.3.0 | [x] | All 6 combinations (3 structures x 2 formats) tested with `--dry-run --verbose` |
| 2.14.2 | v2.3.0 | [x] | Default behavior unchanged (flat + artist_title) |
| 2.14.3 | v2.3.0 | [x] | CLI flag overrides config.yaml |
| 2.14.4 | v2.3.0 | [x] | config.yaml overrides profile default |
| 2.14.5 | v2.3.0 | [x] | `summary` command works with nested export directories |
| 2.14.6 | v2.3.0 | [x] | `cover-art embed` correctly matches files with non-default formats |
| 2.14.7 | v2.3.0 | [x] | `sync-usb` preserves nested structure on target drive |
| 2.14.8 | v2.3.0 | [x] | Filename collisions with `title-only` format handled correctly |
| 2.14.9 | v2.3.0 | [x] | Web UI dropdowns submit correct API parameters |

### 2.15 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.15.1 | v1.7.0 | [x] | Missing `config.yaml`: auto-created with defaults on first run |
| 2.15.2 | v1.7.0 | [x] | Invalid profile name: rejected with error listing valid profiles |
| 2.15.3 | v1.7.0 | [x] | Duplicate playlist key on add: detected and reported |
| 2.15.4 | v2.3.0 | [x] | `title-only` format with duplicate titles: skip-if-exists behavior with warning suggesting `full` format |
| 2.15.5 | v2.3.0 | [x] | Artist/album directory names sanitized by `sanitize_filename()` (strips `/\:*?"<>\|`) |

Deeply nested paths: Very long artist + album + title combinations could exceed filesystem path length limits (255 chars on macOS/Linux). This is an existing limitation and is not addressed.

---

# SRS: Interactive Menu

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.7.0–v2.3.0

---

## 1. Purpose

Provide a loop-based interactive menu interface for user-friendly operation without remembering CLI flags, with numbered playlist selection, letter-based action options, and automatic return to the menu after each operation.

## 2. Requirements

### 2.1 Menu Interface

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

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.7.0 | [x] | `while True` loop returns to menu after each operation (except X) |
| 2.1.2 | v1.7.0 | [x] | Case-insensitive input handling |
| 2.1.3 | v1.7.0 | [x] | Post-processing prompts for USB copy after pipeline operations |
| 2.1.4 | v1.7.0 | [x] | Summary display with pause-to-review before returning to menu |
| 2.1.5 | v1.7.0 | [x] | Profile change persisted to config.yaml via `update_setting()` |
| 2.1.6 | v1.7.0 | [x] | New URLs saved to config.yaml via `add_playlist()` |

### 2.2 Menu Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.7.0 | [x] | Decorative banner with numbered playlists followed by letter-based action options |
| 2.2.2 | v1.7.0 | [x] | Current output profile displayed in menu header |

### 2.3 URL Entry Handler

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.7.0 | [x] | URL entry prompts for playlist key and name after URL is entered |
| 2.3.2 | v1.7.0 | [x] | New playlist saved to config.yaml for future use |

### 2.4 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.7.0 | [x] | Empty Enter at menu: treated as Exit (X) |

---

# SRS: Web Dashboard

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v2.0.0–v2.3.0

---

## 1. Purpose

Provide a browser-based dashboard with full feature parity to the CLI, enabling remote and visual operation of all music-porter capabilities with real-time progress streaming.

## 2. Requirements

### 2.1 Flask Application

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v2.0.0 | [x] | Web dashboard implemented in `web_ui.py` as a Flask application |
| 2.1.2 | v2.0.0 | [x] | Launched via `music-porter web` subcommand with `--host` and `--port` flags |
| 2.1.3 | v2.0.0 | [x] | HTML templates served from `templates/` directory |
| 2.1.4 | v2.0.0 | [x] | `create_app(project_root=None)` factory pattern: creates Flask app, sets `PROJECT_ROOT` config, instantiates `TaskManager`, defines all routes, returns app |
| 2.1.5 | v2.0.0 | [x] | No authentication or CORS configured (development/trusted-network tool) |

### 2.2 Dynamic Module Loading

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v2.0.0 | [x] | `music-porter` imported via `importlib.machinery.SourceFileLoader` (executable has no `.py` extension) |
| 2.2.2 | v2.0.0 | [x] | `mp._init_third_party()` called at import time to pre-load dependencies and avoid `DependencyChecker` in background threads |

### 2.3 Security

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v2.0.0 | [x] | `_safe_dir(directory)` validates directories are within project root via `Path.resolve()` prefix check; returns absolute path string or `None` |

### 2.4 Page Routes (9 pages)

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

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v2.0.0 | [x] | All 9 pages implemented and accessible |

### 2.5 API Endpoints (~26 endpoints)

**Status & Info:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v2.0.0 | [x] | `GET /api/status` — System status, cookies, library stats, current profile |
| 2.5.2 | v2.0.0 | [x] | `GET /api/summary` — Export library statistics |
| 2.5.3 | v2.0.0 | [x] | `GET /api/library-stats` — Source music/ directory statistics |

**Cookie Management:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.4 | v2.0.0 | [x] | `GET /api/cookies/browsers` — Available browser list |
| 2.5.5 | v2.0.0 | [x] | `POST /api/cookies/refresh` — Auto-refresh cookies with browser selection |

**Playlist CRUD:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.6 | v2.0.0 | [x] | `GET /api/playlists` — List all playlists |
| 2.5.7 | v2.0.0 | [x] | `POST /api/playlists` — Add new playlist |
| 2.5.8 | v2.0.0 | [x] | `PUT /api/playlists/<key>` — Update existing playlist |
| 2.5.9 | v2.0.0 | [x] | `DELETE /api/playlists/<key>` — Remove playlist |

**Settings:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.10 | v2.0.0 | [x] | `GET /api/settings` — Get all settings, profiles, valid structures/formats |
| 2.5.11 | v2.0.0 | [x] | `POST /api/settings` — Update settings |

**Directory Listings:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.12 | v2.0.0 | [x] | `GET /api/directories/music` — List music/ playlists |
| 2.5.13 | v2.3.0 | [x] | `GET /api/directories/export` — List export/ playlists with file counts (uses rglob for nested dirs) |

**Operations:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.14 | v2.0.0 | [x] | `POST /api/pipeline/run` — Execute full pipeline (accepts `playlist`, `url`, `auto`, `dir_structure`, `filename_format`) |
| 2.5.15 | v2.0.0 | [x] | `POST /api/convert/run` — Convert M4A to MP3 (accepts `dir_structure`, `filename_format`) |
| 2.5.16 | v2.0.0 | [x] | `POST /api/tags/update` — Update album/artist tags |
| 2.5.17 | v2.0.0 | [x] | `POST /api/tags/restore` — Restore original tags |
| 2.5.18 | v2.0.0 | [x] | `POST /api/tags/reset` — Reset tags from source |
| 2.5.19 | v2.0.0 | [x] | `POST /api/cover-art/<action>` — Cover art: embed, extract, update, strip, resize |

**USB:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.20 | v2.0.0 | [x] | `GET /api/usb/drives` — List connected USB drives |
| 2.5.21 | v2.0.0 | [x] | `POST /api/usb/sync` — Sync files to USB |

**Task Management & Streaming:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.22 | v2.0.0 | [x] | `GET /api/tasks` — List all background tasks |
| 2.5.23 | v2.0.0 | [x] | `GET /api/tasks/<task_id>` — Get task details |
| 2.5.24 | v2.0.0 | [x] | `POST /api/tasks/<task_id>/cancel` — Cancel running task |
| 2.5.25 | v2.0.0 | [x] | `GET /api/stream/<task_id>` — SSE live log stream |

### 2.6 Server-Sent Events (SSE) Live Streaming

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v2.0.0 | [x] | `GET /api/stream/<task_id>` provides real-time log streaming |
| 2.6.2 | v2.0.0 | [x] | Long-polling with 30-second heartbeat timeout |
| 2.6.3 | v2.0.0 | [x] | Message types: `log`, `progress`, `heartbeat`, `done` |
| 2.6.4 | v2.0.0 | [x] | Progress events include: `current`, `total`, `stage`, `percent` |
| 2.6.5 | v2.0.0 | [x] | Sentinel (`None`) in queue indicates task completion |
| 2.6.6 | v2.0.0 | [x] | JSON-formatted SSE data payloads |
| 2.6.7 | v2.0.0 | [x] | Progress throttling: events fire only on percentage change (mutable closure list `last_pct = [-1]`) |

### 2.7 Background Task Management

**TaskState dataclass:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v2.0.0 | [x] | Fields: `id`, `operation`, `description`, `status`, `result`, `error`, `thread`, `cancel_event`, `log_queue`, `started_at`, `finished_at` |
| 2.7.2 | v2.0.0 | [x] | Status values: `pending`, `running`, `completed`, `failed`, `cancelled` |
| 2.7.3 | v2.0.0 | [x] | `elapsed()` method calculates task duration |
| 2.7.4 | v2.0.0 | [x] | `to_dict()` serialization returns 9-key dict with auto-calculated `elapsed` rounded to 1 decimal place |

**TaskManager class:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.5 | v2.0.0 | [x] | `submit(operation, description, target)` spawns background thread, returns 12-char hex task_id |
| 2.7.6 | v2.0.0 | [x] | `get(task_id)` retrieves TaskState |
| 2.7.7 | v2.0.0 | [x] | `list_all()` returns all tasks as dicts |
| 2.7.8 | v2.0.0 | [x] | `cancel(task_id)` signals cancellation via `threading.Event` |
| 2.7.9 | v2.0.0 | [x] | `is_busy()` checks if any task is currently running |

### 2.8 WebLogger

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v2.0.0 | [x] | `WebLogger` subclass of `Logger` routes messages to SSE queue |
| 2.8.2 | v2.0.0 | [x] | `_write(level, message)` strips ANSI escape codes via `_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')`, pushes to queue, and writes to log file |
| 2.8.3 | v2.0.0 | [x] | `file_info(message)` sends per-file progress messages to SSE queue (visible in web UI, unlike CLI) |
| 2.8.4 | v2.0.0 | [x] | `_make_progress_callback()` returns throttled progress event closure |
| 2.8.5 | v2.0.0 | [x] | `register_bar()` / `unregister_bar()` are no-ops (progress handled via SSE) |

### 2.9 Client-Side UI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.9.1 | v2.0.0 | [x] | CDN-served Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 from jsDelivr |
| 2.9.2 | v2.0.0 | [x] | Client-side toast notification system: `showToast(msg, type)` with 4-second auto-dismiss; types: `info`, `success`, `error`, `warning` |
| 2.9.3 | v2.0.0 | [x] | Client-side SSE log streaming via `EventSource` with auto-scrolling in log panels |
| 2.9.4 | v2.0.0 | [x] | Dynamic progress bar injection via `_ensureProgressBar()`: queries parent for `.sse-progress` div, creates and inserts if missing |
| 2.9.5 | v2.0.0 | [x] | Sortable dashboard table: click headers to sort, tracks `currentSort = {key, asc}` state, toggles direction on same-column clicks |
| 2.9.6 | v2.0.0 | [x] | Operations badge: polls `/api/tasks` every 10 seconds, shows count of running tasks in sidebar |
| 2.9.7 | v2.0.0 | [x] | Version/profile badge: fetches `/api/status` on page load, displays version in header and profile in sidebar |
| 2.9.8 | v2.0.0 | [x] | Cookie status badge on dashboard: three states — `bg-success` (valid), `bg-danger` (expired), `bg-warning` (missing) with refresh button |
| 2.9.9 | v2.0.0 | [x] | Pipeline mode toggle: `<select>` with 3 options (playlist/url/auto), conditional input visibility via `d-none` class |
| 2.9.10 | v2.0.0 | [x] | Task history table on operations page: reverse-sorted, status badges with 5 states, cancel buttons for running tasks only, duration formatting (`<60s` → `"X.Xs"`, `>=60s` → `"Xm Ys"`) |

### 2.10 Feature Parity (CLI <-> Web)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.10.1 | v2.0.0 | [x] | Every CLI operation has a corresponding API endpoint |
| 2.10.2 | v2.0.0 | [x] | Pipeline, convert, tag, restore, reset, cover-art, USB sync all accessible from web |
| 2.10.3 | v2.0.0 | [x] | Settings and profile management available in web UI |
| 2.10.4 | v2.0.0 | [x] | Library summary and statistics displayed on dashboard |

### 2.11 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.11.1 | v2.0.0 | [x] | Task already running: `submit()` returns None, client informed of busy state (HTTP 409) |
| 2.11.2 | v2.0.0 | [x] | SSE stream for nonexistent task: handled gracefully (HTTP 404) |
| 2.11.3 | v2.0.0 | [x] | Concurrent access: TaskManager serializes operations |
| 2.11.4 | vNEXT | [x] | Port already in use: before binding, kill any existing process listening on the target port; uses platform-appropriate method (macOS/Linux: `lsof`/`kill`, Windows: `netstat`/`taskkill`); best-effort with graceful fallback if kill fails |

---

# SRS: CLI & Runtime

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

## 1. Purpose

Provide the command-line interface, runtime infrastructure, and cross-cutting concerns — including the startup banner, argument parsing, subcommand routing, dependency checking, logging, progress bars, platform detection, and virtual environment auto-activation.

## 2. Requirements

### 2.1 CLI Subcommand Architecture

The tool shall provide the following subcommands via `argparse`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | `pipeline` — Full download + convert + tag workflow |
| 2.1.2 | v1.0.0 | [x] | `download` — Download from Apple Music |
| 2.1.3 | v1.0.0 | [x] | `convert` — Convert M4A → MP3 |
| 2.1.4 | v1.0.0 | [x] | `tag` — Update tags on existing MP3s |
| 2.1.5 | v1.0.0 | [x] | `restore` — Restore original tags from TXXX frames |
| 2.1.6 | v1.0.0 | [x] | `reset` — Reset tags from source M4A files |
| 2.1.7 | v1.0.0 | [x] | `sync-usb` — Copy files to USB drive |
| 2.1.8 | v1.5.0 | [x] | `cover-art` — Cover art management (embed, extract, update, strip, resize) |
| 2.1.9 | v1.4.0 | [x] | `summary` — Display export library statistics |
| 2.1.10 | v2.0.0 | [x] | `web` — Launch web dashboard |
| 2.1.11 | v1.0.0 | [x] | Main command routing via argparse subparsers |

### 2.2 Shared Argument Parsers

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | v1.0.0 | [x] | `_create_quality_args_parser()` creates shared parent parser with `--preset` and `--quality` arguments |
| 2.2.2 | v1.6.0 | [x] | `_create_cookie_args_parser()` creates shared parent parser with `--cookies`, `--auto-refresh-cookies`, and `--skip-cookie-validation` arguments |
| 2.2.3 | v1.0.0 | [x] | `_create_usb_args_parser()` creates shared parent parser with `--usb-dir` argument |
| 2.2.4 | v1.0.0 | [x] | `positive_int(value)` argparse type function: validates integer >= 1, raises `ArgumentTypeError` for invalid values |

### 2.3 Global Flags

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.0.0 | [x] | `--dry-run` — Preview changes without modifying files |
| 2.3.2 | v1.0.0 | [x] | `--verbose` / `-v` — Enable verbose output |
| 2.3.3 | v1.0.0 | [x] | `--version` — Show version and exit |
| 2.3.4 | v1.0.0 | [x] | `--workers N` — Set parallel conversion workers |
| 2.3.5 | v1.7.0 | [x] | `--output-type TYPE` — Select output profile |

### 2.4 Startup Banner

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.0.0 | [x] | Decorative `╔═══╗` / `╚═══╝` box format with dynamic width based on banner text length |
| 2.4.2 | v1.0.0 | [x] | Banner text: `"Music Porter v{VERSION}"` centered in box |
| 2.4.3 | v1.0.0 | [x] | Startup info lines displayed after banner: Platform, Command, Output type, Quality, Artwork, Dir layout, File names, Workers, Cookies |
| 2.4.4 | v1.0.0 | [x] | Startup info logged to file only (not console) via `logger.file_info()` |
| 2.4.5 | v1.0.0 | [x] | `VERSION` constant defined at line 69 of `music-porter` |

### 2.5 Dependency Checking

The `DependencyChecker` class shall verify all required dependencies:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.0.0 | [x] | `check_all(require_ffmpeg, require_gamdl)` checks all dependencies and returns bool |
| 2.5.2 | v1.0.0 | [x] | `check_python_packages()` checks all packages from `requirements.txt` and installs missing ones via pip |
| 2.5.3 | v1.0.0 | [x] | `display_summary(config)` prints formatted dependency summary with checkmarks |
| 2.5.4 | v1.0.0 | [x] | `IMPORT_MAP` dictionary maps pip package names to Python import names: `{'ffmpeg-python': 'ffmpeg', 'webdriver-manager': 'webdriver_manager', 'Pillow': 'PIL', 'PyYAML': 'yaml', 'Flask': 'flask'}` |
| 2.5.5 | v1.0.0 | [x] | FFmpeg not installed: detects missing binary and provides install instructions per platform (macOS: `brew`, Linux: `apt-get`/`dnf`/`pacman`, Windows: Chocolatey) |

### 2.6 Logging System

The `Logger` class shall provide timestamped logging to console and file:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.0.0 | [x] | Log files stored in `logs/` directory with `%Y-%m-%d_%H-%M-%S.log` naming |
| 2.6.2 | v1.0.0 | [x] | Thread-safe writes via `threading.Lock` |
| 2.6.3 | v1.0.0 | [x] | Log methods: `info()`, `debug()`, `warn()`, `error()`, `success()`, `dry_run()`, `file_info()`, `skip()` |
| 2.6.4 | v1.0.0 | [x] | Console routing through `tqdm.write()` when progress bar is active (`register_bar()` / `unregister_bar()`) |
| 2.6.5 | v1.0.0 | [x] | `--verbose` flag enables debug-level output |
| 2.6.6 | v1.0.0 | [x] | `--version` flag displays current version |
| 2.6.7 | v1.0.0 | [x] | `Logger.skip(message)` logs skip messages for skipped operations |
| 2.6.8 | v1.0.0 | [x] | `Logger.file_info(message)` writes to log file only, not console |

### 2.7 Progress Bars

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v1.0.0 | [x] | Uses `tqdm` library for progress display |
| 2.7.2 | v1.0.0 | [x] | `ProgressBar` context manager wraps tqdm with custom formatting (`__enter__`/`__exit__`) |
| 2.7.3 | v1.0.0 | [x] | Terminal state saved/restored via `_save_terminal()` and `_restore_terminal()` |
| 2.7.4 | v1.0.0 | [x] | Logger integrates with progress bar via `register_bar()` / `unregister_bar()` for write routing |
| 2.7.5 | v1.0.0 | [x] | Progress bars disabled during `--dry-run` mode |

### 2.8 Third-Party Import Deferral

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v1.0.0 | [x] | `_init_third_party()` defers tqdm import until after `DependencyChecker` has ensured packages exist |
| 2.8.2 | v1.0.0 | [x] | Sets `tqdm.monitor_interval = 0` to prevent TMonitor thread from interfering with `input()` |

### 2.9 Platform Detection

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.9.1 | v1.0.0 | [x] | `CURRENT_OS = platform.system()` returns `'Darwin'`, `'Linux'`, or `'Windows'` |
| 2.9.2 | v1.0.0 | [x] | Boolean constants: `IS_MACOS`, `IS_LINUX`, `IS_WINDOWS` |
| 2.9.3 | v1.0.0 | [x] | `get_os_display_name()` returns friendly names: `"macOS"`, `"Linux"`, `"Windows"` |

### 2.10 Dry-Run Mode

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.10.1 | v1.0.0 | [x] | Global `--dry-run` flag passed through all operations |
| 2.10.2 | v1.0.0 | [x] | `logger.dry_run(message)` writes messages with `[DRY-RUN]` prefix |
| 2.10.3 | v1.0.0 | [x] | File write operations conditionally skipped when `dry_run=True` |
| 2.10.4 | v1.0.0 | [x] | Progress bars disabled during dry-run |
| 2.10.5 | v1.0.0 | [x] | No files created, modified, or deleted in dry-run mode |

### 2.11 Virtual Environment Auto-Activation

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.11.1 | v1.0.0 | [x] | `_auto_activate_venv()` detects and re-execs under `.venv/bin/python` if available |
| 2.11.2 | v1.0.0 | [x] | Supports macOS/Linux (`.venv/bin/python`) and Windows (`.venv/Scripts/python.exe`) |
| 2.11.3 | v1.0.0 | [x] | Uses `os.execv()` for transparent re-launch |

### 2.12 Web Subcommand

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.12.1 | v2.0.0 | [x] | `web` subcommand dynamically imports `web_ui.py` via `importlib` |
| 2.12.2 | v2.0.0 | [x] | Fallback with clear error message if Flask is not installed |

### 2.13 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.13.1 | v1.0.0 | [x] | FFmpeg not installed: `DependencyChecker` detects missing binary and provides platform-specific install instructions |
| 2.13.2 | v1.0.0 | [x] | Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics |
| 2.13.3 | v1.0.0 | [x] | KeyboardInterrupt handling in confirmation prompts: caught and handled gracefully |
