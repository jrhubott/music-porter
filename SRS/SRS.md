# Completed SRS Documents

## Table of Contents

### Core Pipeline

| # | Entry | IDs | Description |
|---|-------|-----|-------------|
| 1 | [Pipeline](#srs-1-pipeline) | 1.1–1.3 | Multi-stage workflow orchestration: download → convert → tag → USB sync, with batch processing and statistics |
| 2 | [Download & Authentication](#srs-2-download--authentication) | 2.1–2.8 | Apple Music playlist downloading via gamdl, cookie validation, automatic browser-based refresh, and multi-browser support |
| 3 | [Conversion](#srs-3-conversion) | 3.1–3.8 | M4A-to-MP3 conversion using ffmpeg with quality presets, multi-threaded processing, and cover art embedding |
| 4 | [Tag Management](#srs-4-tag-management) | 4.1–4.6 | TXXX hard-gate metadata protection, tag update/restore/reset operations, title formatting, and ID3 cleanup |
| 5 | [Cover Art](#srs-5-cover-art) | 5.1–5.5 | Cover art embedding, extraction, replacement, stripping, and resizing with Pillow integration |
| 6 | [USB Sync](#srs-6-usb-sync) | 6.1–6.7 | Platform-aware USB drive detection, incremental file sync, and auto-eject for macOS/Linux/Windows |

### Library & Configuration

| # | Entry | IDs | Description |
|---|-------|-----|-------------|
| 7 | [Library Summary](#srs-7-library-summary) | 7.1–7.8 | Export library statistics with tag integrity checking, cover art analysis, and three output modes (quick/default/detailed) |
| 8 | [Configuration](#srs-8-configuration) | 8.1–8.15 | YAML config system, output profiles, directory structures, filename formats, settings precedence, and CLI/Web parity |
| 9 | [Configurable Output Profiles](#srs-9-configurable-output-profiles) | 9.1–9.14 | User-defined output profiles in config.yaml replacing hardcoded Python definitions, with validation and migration |
| 14 | [Summary Freshness Levels](#srs-14-summary-freshness-levels) | 14.1–14.4 | Graduated freshness indicators (Current/Recent/Stale/Outdated) in summary playlist table with aggregate statistics |

### User Interfaces

| # | Entry | IDs | Description |
|---|-------|-----|-------------|
| 10 | [Interactive Menu](#srs-10-interactive-menu) | 10.1–10.4 | Loop-based CLI menu with numbered playlist selection, letter-based actions, and profile management |
| 11 | [Web Dashboard](#srs-11-web-dashboard) | 11.1–11.11 | Flask-based browser UI with full CLI parity, ~26 API endpoints, SSE live streaming, and background task management |
| 12 | [CLI & Runtime](#srs-12-cli--runtime) | 12.1–12.13 | Argument parsing, subcommand routing, startup banner, dependency checking, logging, progress bars, and platform detection |
| 15 | [iOS Companion App](#srs-15-ios-companion-app) | 15.1–15.12 | Native iOS app with server discovery, API auth, playlist browsing, file downloads, MusicKit integration, and USB export |

### Architecture

| # | Entry | IDs | Description |
|---|-------|-----|-------------|
| 13 | [Service Layer](#srs-13-service-layer) | 13.1–13.7 | Business logic / UI separation: structured result objects, UserPromptHandler callbacks, DisplayHandler abstraction |

---

## Core Pipeline

---

### SRS 1: Pipeline

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Orchestrate the multi-stage workflow that downloads Apple Music playlists, converts them to MP3, applies tags, and optionally syncs to USB — coordinating stages, tracking statistics, and handling batch processing across multiple playlists.

#### Requirements

##### 1.1 Pipeline Orchestration

The `PipelineOrchestrator` class shall coordinate a four-stage workflow:

| Stage | Name | Description |
|-------|------|-------------|
| 1 | `download` | Download playlist from Apple Music via gamdl |
| 2 | `convert` | Convert M4A → MP3 via ffmpeg |
| 3 | `tag` | Apply album/artist tags and embed cover art |
| 4 | `usb-sync` | Copy files to USB drive (optional) |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 1.1.1 | v1.0.0 | [x] | Pipeline runs stages sequentially: download → convert → tag → USB sync |
| 1.1.2 | v1.0.0 | [x] | Individual stage failures do not abort the entire pipeline (error recovery) |
| 1.1.3 | v1.0.0 | [x] | Pipeline supports single-playlist (`--playlist`), URL-based (`--url`), and batch (`--auto`) modes |
| 1.1.4 | v1.7.0 | [x] | Post-pipeline USB prompt in interactive mode: offers to copy results to USB after completion |

##### 1.2 Batch Processing Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 1.2.1 | v1.0.0 | [x] | `PipelineStatistics` tracks `stages_completed`, `stages_failed`, and `stages_skipped` lists |
| 1.2.2 | v1.0.0 | [x] | `PipelineStatistics` aggregates download, conversion, tagging, cover art, and USB stats per playlist |
| 1.2.3 | v1.0.0 | [x] | `PlaylistResult` captures per-playlist results including `failed_stage` indicator and `duration` |
| 1.2.4 | v1.0.0 | [x] | `AggregateStatistics` accumulates results across multiple playlists with `get_cumulative_stats()` |
| 1.2.5 | v1.0.0 | [x] | Comprehensive summary report printed at pipeline completion |

##### 1.3 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 1.3.1 | v1.0.0 | [x] | Empty playlist directory: conversion reports 0 files found, no error |
| 1.3.2 | v1.0.0 | [x] | gamdl subprocess failure: captured via return code and logged |
| 1.3.3 | v1.0.0 | [x] | Individual file conversion failure during pipeline: logged and counted as error, remaining files processed |

---

### SRS 2: Download & Authentication

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Download Apple Music playlists via gamdl and manage the cookie-based authentication required for access — including validation, automatic browser-based refresh, multi-browser support, and graceful handling of expired sessions.

#### Requirements

##### 2.1 Download Module

The `Downloader` class shall download playlists from Apple Music:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | v1.0.0 | [x] | Executes gamdl as a subprocess via `subprocess.Popen()` |
| 2.1.2 | v1.0.0 | [x] | Command: `python -m gamdl --log-level INFO -o <output_path>/ <url>` |
| 2.1.3 | v1.0.0 | [x] | Line-buffered output (`bufsize=1`, `universal_newlines=True`) |
| 2.1.4 | v1.0.0 | [x] | `DownloadStatistics` tracks `playlist_total`, `downloaded`, `skipped`, and `failed` |
| 2.1.5 | v1.0.0 | [x] | Output organized in nested `Artist/Album/Track.m4a` directory structure |

##### 2.2 Cookie Validation

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

##### 2.3 Automatic Refresh via Selenium

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | v1.6.0 | [x] | `auto_refresh(backup=True, browser=None)` method orchestrates refresh |
| 2.3.2 | v1.6.0 | [x] | `_extract_with_selenium(browser=None)` launches browser to extract cookies |
| 2.3.3 | v1.6.0 | [x] | Launches browser headless first; falls back to visible mode if login needed |
| 2.3.4 | v1.6.0 | [x] | Login detection: checks for sign-in button presence to determine authentication state |
| 2.3.5 | v1.6.0 | [x] | Converts Selenium cookies to `http.cookiejar.Cookie` objects |
| 2.3.6 | v1.6.0 | [x] | `--auto-refresh-cookies` flag for non-interactive refresh |

##### 2.4 Cookie Cleanup

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | v1.6.0 | [x] | `clean_cookies()` removes non-Apple cookies from `cookies.txt` |
| 2.4.2 | v1.6.0 | [x] | Filters by `APPLE_COOKIE_DOMAIN = 'apple.com'` — only retains cookies whose domain contains `apple.com` |
| 2.4.3 | v1.6.0 | [x] | Creates backup before modifying; returns `(success: bool, kept: int, removed: int)` tuple |

##### 2.5 Multi-Browser Support

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | v1.6.0 | [x] | `_detect_default_browser()` detects OS default browser |
| 2.5.2 | v1.6.0 | [x] | Platform-specific detection: LaunchServices (macOS), xdg-settings (Linux), registry (Windows) |
| 2.5.3 | v1.6.0 | [x] | Supported browsers: Chrome, Firefox, Safari, Edge |
| 2.5.4 | v1.6.0 | [x] | Automatic fallback to other browsers if default fails |
| 2.5.5 | v1.6.0 | [x] | `webdriver-manager` handles automatic browser driver installation |

##### 2.6 Backup Strategy

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | v1.6.0 | [x] | Creates `cookies.txt.backup` before overwriting existing cookies |
| 2.6.2 | v1.6.0 | [x] | Backup preserves last known working cookies |
| 2.6.3 | v1.6.0 | [x] | Backup creation controlled by `backup=True` parameter (default) |

##### 2.7 Interactive and Non-Interactive Modes

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | v1.6.0 | [x] | Interactive: expired cookies trigger prompt "Attempt automatic cookie refresh? [Y/n]" |
| 2.7.2 | v1.6.0 | [x] | Menu-level checks before batch operations; per-download checks for single operations |
| 2.7.3 | v1.6.0 | [x] | Non-interactive: fails immediately with clear error if cookies invalid (prevents hanging) |

##### 2.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | v1.6.0 | [x] | No `cookies.txt` file: clear error with instructions to create one |
| 2.8.2 | v1.6.0 | [x] | Malformed cookie file: caught by MozillaCookieJar parser, reported as error |
| 2.8.3 | v1.6.0 | [x] | Browser not installed: automatic fallback to next available browser |
| 2.8.4 | v1.6.0 | [x] | Login required during headless extraction: falls back to visible browser for user interaction |
| 2.8.5 | v1.6.0 | [x] | Selenium not installed: provides manual refresh instructions as fallback |

---

### SRS 3: Conversion

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Convert downloaded M4A files to MP3 format using ffmpeg, with configurable quality presets, multi-threaded processing, automatic tag transfer, and cover art embedding — producing output files organized according to the active output profile.

#### Requirements

##### 3.1 M4A-to-MP3 Conversion

The `Converter` class shall convert M4A files to MP3 using ffmpeg:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.1.1 | v1.0.0 | [x] | Uses `ffmpeg-python` library wrapping the system `ffmpeg` binary |
| 3.1.2 | v1.0.0 | [x] | Codec: `libmp3lame` (LAME MP3 encoder) |
| 3.1.3 | v1.0.0 | [x] | Runs with `quiet=True` to suppress ffmpeg output during batch processing |
| 3.1.4 | v1.0.0 | [x] | Catches `ffmpeg.Error` exceptions; logs details and continues processing remaining files |
| 3.1.5 | v1.0.0 | [x] | Existing MP3s are skipped unless `--force` flag is used |
| 3.1.6 | v1.0.0 | [x] | Force re-conversion increments `overwritten` counter (distinct from `converted`) |

##### 3.2 M4A Tag Reading

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.2.1 | v1.0.0 | [x] | `read_m4a_tags(input_file)` returns `(title, artist, album)` tuple from M4A source |
| 3.2.2 | v1.0.0 | [x] | Default values for missing tags: `"Unknown Title"`, `"Unknown Artist"`, `"Unknown Album"` |
| 3.2.3 | v1.0.0 | [x] | M4A tag constants: `M4A_TAG_TITLE = '\xa9nam'`, `M4A_TAG_ARTIST = '\xa9ART'`, `M4A_TAG_ALBUM = '\xa9alb'`, `M4A_TAG_COVER = 'covr'` |
| 3.2.4 | v1.5.0 | [x] | `read_m4a_cover_art(input_file)` returns `(cover_data: bytes, mime_type: str)` or `(None, None)` |

##### 3.3 Output File Naming and Paths

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.3.1 | v1.0.0 | [x] | `sanitize_filename(name)` removes invalid characters: `/\:*?"<>\|` |
| 3.3.2 | v2.3.0 | [x] | `_build_output_filename(artist, title)` constructs name based on profile's `filename_format` field |
| 3.3.3 | v2.3.0 | [x] | `_build_output_path(base_path, filename, artist, album)` constructs path based on profile's `directory_structure` field |
| 3.3.4 | v2.3.0 | [x] | Directory creation with `parents=True, exist_ok=True` for nested structures |
| 3.3.5 | v2.3.0 | [x] | Filename collision hint when skipping in non-`full` format: suggests using `full` format |

##### 3.4 Cover Art Embedding During Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.4.1 | v1.5.0 | [x] | Cover art automatically extracted from source M4A and embedded into MP3 during conversion |
| 3.4.2 | v1.5.0 | [x] | APIC frame constants: `APIC_MIME_JPEG = "image/jpeg"`, `APIC_MIME_PNG = "image/png"`, `APIC_TYPE_FRONT_COVER = 3` |
| 3.4.3 | v1.7.0 | [x] | Cover art resized per profile's `artwork_size` setting during conversion via `resize_cover_art_bytes()` |
| 3.4.4 | v1.5.0 | [x] | `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding |
| 3.4.5 | v1.0.0 | [x] | Tag application occurs immediately after conversion (in same worker thread) |

##### 3.5 Quality Presets

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
| 3.5.1 | v1.0.0 | [x] | Default preset: `lossless` (320 kbps CBR) via `DEFAULT_QUALITY_PRESET` constant |
| 3.5.2 | v1.0.0 | [x] | `--preset` flag accepts `lossless`, `high`, `medium`, `low`, `custom` |
| 3.5.3 | v1.0.0 | [x] | Custom VBR requires both `--preset custom` and `--quality 0-9` |
| 3.5.4 | v1.0.0 | [x] | `_get_quality_settings(preset)` resolves preset name to ffmpeg parameters |
| 3.5.5 | v1.0.0 | [x] | `--preset` flag available on both `convert` and `pipeline` subcommands |

##### 3.6 Multi-Threaded Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.6.1 | v1.0.0 | [x] | Uses `concurrent.futures.ThreadPoolExecutor` for parallel file conversion |
| 3.6.2 | v1.0.0 | [x] | Default workers: `min(os.cpu_count(), MAX_DEFAULT_WORKERS)` where `MAX_DEFAULT_WORKERS = 6` |
| 3.6.3 | v1.0.0 | [x] | Configurable via `--workers N` global flag |
| 3.6.4 | v1.0.0 | [x] | `ConversionStatistics` is thread-safe with `threading.Lock` |
| 3.6.5 | v1.0.0 | [x] | Atomic progress counter via `next_progress()` method |
| 3.6.6 | v1.0.0 | [x] | `ConversionStatistics` tracks: `total_found`, `converted`, `overwritten`, `skipped`, `errors` |

##### 3.7 Conversion Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.7.1 | v1.0.0 | [x] | Conversion progress format: `[count/total] Action: filename` (e.g., `[3/15] Converting: Artist - Title.mp3`) |

##### 3.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 3.8.1 | v1.0.0 | [x] | Individual file conversion failure: logged and counted as error, remaining files processed |
| 3.8.2 | v1.0.0 | [x] | Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics |
| 3.8.3 | v1.5.0 | [x] | M4A source has no cover art: MP3 created without APIC frame, logged as warning |

---

### SRS 4: Tag Management

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Provide a robust tag management system that preserves original metadata from source files using TXXX (user-defined text) ID3 frames with hard-gate protection, ensuring originals can always be restored even after multiple update cycles.

#### Requirements

##### 4.1 TXXX Hard-Gate Protection

Original metadata shall be stored in TXXX frames that are written once and never overwritten:

| TXXX Frame | Constant | Stores |
|------------|----------|--------|
| `OriginalTitle` | `TXXX_ORIGINAL_TITLE` | Original track title |
| `OriginalArtist` | `TXXX_ORIGINAL_ARTIST` | Original artist name |
| `OriginalAlbum` | `TXXX_ORIGINAL_ALBUM` | Original album name |
| `OriginalCoverArtHash` | `TXXX_ORIGINAL_COVER_ART_HASH` | SHA-256 hash prefix of original cover art |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.1.1 | v1.0.0 | [x] | `_txxx_exists(tags, desc_name)` checks for frame existence by iterating `tags.values()` with `isinstance(frame, TXXX)` |
| 4.1.2 | v1.0.0 | [x] | `_get_txxx(tags, desc_name)` retrieves frame value by iterating frame types (not string key indexing) |
| 4.1.3 | v1.0.0 | [x] | `save_original_tag(tags, tag_key, tag_name, current_value, label, logger, verbose)` enforces hard-gate: skips write if `_txxx_exists()` returns True; returns `(value, was_newly_stored)` tuple |
| 4.1.4 | v1.0.0 | [x] | Once written, TXXX protection frames are NEVER overwritten (except via explicit `reset` command) |

##### 4.2 Tag Operations

The `TaggerManager` class shall support three tag operations:

**Update** (`update_tags()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.2.1 | v1.0.0 | [x] | Updates album and/or artist tags on MP3 files |
| 4.2.2 | v1.0.0 | [x] | Saves original values to TXXX frames before overwriting (hard-gate protected) |
| 4.2.3 | v1.0.0 | [x] | `--album` and `--artist` flags for specifying new values |
| 4.2.4 | v1.0.0 | [x] | Statistics tracked per-field: `title_updated`, `album_updated`, `artist_updated` |

**Restore** (`restore_tags()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.2.5 | v1.0.0 | [x] | Restores tags from TXXX protection frames to standard ID3 fields |
| 4.2.6 | v1.0.0 | [x] | `--all` flag restores all tags; `--album`, `--title`, `--artist` for selective restore |
| 4.2.7 | v1.0.0 | [x] | Reports missing TXXX frames (tracks `*_missing` counters) |
| 4.2.8 | v1.0.0 | [x] | Statistics tracked: `title_restored`, `album_restored`, `artist_restored` |

**Reset** (`reset_tags_from_source()`):

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.2.9 | v1.0.0 | [x] | Overwrites TXXX protection frames from source M4A files (destructive) |
| 4.2.10 | v1.0.0 | [x] | Requires confirmation prompt before proceeding |
| 4.2.11 | v1.0.0 | [x] | Takes both `input_dir` (M4A source) and `output_dir` (MP3 target) parameters |
| 4.2.12 | v1.7.0 | [x] | Reset tag matching maps M4A files to MP3s using profile-aware filename and directory structure |

##### 4.3 Title Formatting

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.3.1 | v1.0.0 | [x] | `_strip_artist_prefix(title, artist)` prevents double-compounding of "Artist - " prefix |
| 4.3.2 | v1.0.0 | [x] | New titles built from protected originals: `f"{OriginalArtist} - {OriginalTitle}"` |
| 4.3.3 | v1.7.0 | [x] | Title format controlled by profile's `title_tag_format` field (`"artist_title"`) |

##### 4.4 ID3 Version and Cleanup

Default cleanup options applied via `_apply_cleanup()`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.4.1 | v1.0.0 | [x] | ID3v2.3 output by default (older device compatibility), configurable per profile |
| 4.4.2 | v1.0.0 | [x] | ID3v1 tags stripped by default (`strip_id3v1: True`) |
| 4.4.3 | v1.0.0 | [x] | Duplicate frames automatically removed via key iteration |
| 4.4.4 | v1.0.0 | [x] | Overrides available: `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates` |
| 4.4.5 | v1.7.0 | [x] | Profile `id3_version` field: `3` for ID3v2.3, `4` for ID3v2.4 |
| 4.4.6 | v1.0.0 | [x] | `_apply_cleanup()` keeps only `TIT2`, `TPE1`, `TALB`, `APIC`, and TXXX preservation frames; removes all other frames |
| 4.4.7 | v1.0.0 | [x] | Allowed TXXX descriptions: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`, `OriginalCoverArtHash` |

##### 4.5 Tag Statistics

`TagStatistics` class tracks per-field counters:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.5.1 | v1.0.0 | [x] | Updated: `title_updated`, `album_updated`, `artist_updated` |
| 4.5.2 | v1.0.0 | [x] | Stored (TXXX): `title_stored`, `artist_stored`, `album_stored` |
| 4.5.3 | v1.0.0 | [x] | Protected (skipped): `title_protected`, `artist_protected`, `album_protected` |
| 4.5.4 | v1.0.0 | [x] | Restored: `title_restored`, `artist_restored`, `album_restored` |
| 4.5.5 | v1.0.0 | [x] | Missing: `title_missing`, `artist_missing`, `album_missing` |

##### 4.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 4.6.1 | v1.0.0 | [x] | Mutagen key indexing inconsistency after save/reload: mitigated by iterating `tags.values()` instead of string key lookup |
| 4.6.2 | v1.0.0 | [x] | Files without existing tags: creates new ID3 tag structure before writing |
| 4.6.3 | v1.0.0 | [x] | Multiple script runs: TXXX frames preserved across unlimited update cycles |
| 4.6.4 | v1.0.0 | [x] | Reset confirmation: requires interactive confirmation to prevent accidental TXXX overwrite |

---

### SRS 5: Cover Art

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.5.0–v2.3.0

---

#### Purpose

Manage cover art across the MP3 library — embedding art from M4A sources during conversion, and providing standalone operations to embed, extract, update, strip, and resize artwork on existing MP3 files.

#### Requirements

##### 5.1 Automatic Embedding During Conversion

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 5.1.1 | v1.5.0 | [x] | Cover art automatically extracted from source M4A and embedded into MP3 during conversion |
| 5.1.2 | v1.5.0 | [x] | APIC frame with type `APIC_TYPE_FRONT_COVER` (3) and appropriate MIME type (`image/jpeg` or `image/png`) |
| 5.1.3 | v1.5.0 | [x] | SHA-256 hash prefix (first 16 chars) stored in `TXXX:OriginalCoverArtHash` with hard-gate protection |
| 5.1.4 | v1.5.0 | [x] | `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding |
| 5.1.5 | v1.7.0 | [x] | Profile-based resizing: `artwork_size > 0` resizes to max pixels, `0` embeds original, `-1` strips artwork |

##### 5.2 Cover Art Subcommands

The `CoverArtManager` class shall support five operations via `cover-art` subcommand:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 5.2.1 | v1.5.0 | [x] | **embed:** Embeds cover art from matching M4A source files into existing MP3s |
| 5.2.2 | v1.5.0 | [x] | **embed:** Auto-derives source directory from `export/` → `music/` path mapping |
| 5.2.3 | v1.5.0 | [x] | **embed:** `--source` flag overrides auto-derivation |
| 5.2.4 | v1.5.0 | [x] | **embed:** `--all` flag processes all configured playlists |
| 5.2.5 | v1.5.0 | [x] | **embed:** `--force` flag re-embeds even if art already exists |
| 5.2.6 | v2.3.0 | [x] | **embed:** Accepts `--dir-structure` and `--filename-format` flags for non-default layouts |
| 5.2.7 | v1.5.0 | [x] | **extract:** Saves embedded cover art from MP3 files to image files |
| 5.2.8 | v1.5.0 | [x] | **extract:** Default output directory: `<playlist>/cover-art/` |
| 5.2.9 | v1.5.0 | [x] | **extract:** `--output` flag for custom output directory |
| 5.2.10 | v1.5.0 | [x] | **update:** Replaces cover art on all MP3s from a single image file |
| 5.2.11 | v1.5.0 | [x] | **update:** `--image` flag (required) accepts `.jpg`, `.jpeg`, `.png` files |
| 5.2.12 | v1.5.0 | [x] | **update:** Detects MIME type from file extension |
| 5.2.13 | v1.5.0 | [x] | **strip:** Removes all APIC frames from MP3s to reduce file size |
| 5.2.14 | v1.5.0 | [x] | **resize:** Resizes existing embedded cover art to specified max pixel size |
| 5.2.15 | v1.7.0 | [x] | **resize:** Available as interactive menu option (R) |

##### 5.3 Pillow Integration

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 5.3.1 | v1.5.0 | [x] | Uses `PIL.Image` from Pillow library for image processing |
| 5.3.2 | v1.5.0 | [x] | Resize method: `img.thumbnail((max_size, max_size), Image.LANCZOS)` (high-quality downsampling) |
| 5.3.3 | v1.5.0 | [x] | Supports PNG and JPEG with proper color mode conversion (RGB for JPEG) |
| 5.3.4 | v1.7.0 | [x] | `ride-command` profile: 100px max artwork; `basic` profile: original size |
| 5.3.5 | v1.5.0 | [x] | `resize_cover_art_bytes(image_data, max_size, mime_type)` returns original data unchanged if image already fits within `max_size` |
| 5.3.6 | v1.5.0 | [x] | PIL lazy-imported to avoid startup cost (imported inside `resize_cover_art_bytes()`) |
| 5.3.7 | v1.5.0 | [x] | Cover art hash: SHA-256 of art bytes, first 16 chars stored in `TXXX:OriginalCoverArtHash` |

##### 5.4 Cover Art Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 5.4.1 | v1.5.0 | [x] | Per-playlist tracking: `files_with_cover_art`, `files_without_cover_art` |
| 5.4.2 | v1.5.0 | [x] | Original vs. resized tracking: `files_with_original_cover_art`, `files_with_resized_cover_art` |
| 5.4.3 | v1.5.0 | [x] | Integrated into library summary display |

##### 5.5 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 5.5.1 | v1.5.0 | [x] | M4A source has no cover art: MP3 created without APIC frame, logged as warning |
| 5.5.2 | v1.5.0 | [x] | Source directory not found: clear error message with path displayed |
| 5.5.3 | v1.5.0 | [x] | Unsupported image format in `--image`: rejected with error |

---

### SRS 6: USB Sync

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Detect connected USB drives, incrementally sync exported MP3 files, and optionally eject the drive — with platform-aware behavior for macOS, Linux, and Windows.

#### Requirements

##### 6.1 Platform-Aware Drive Detection

The `USBManager` class shall detect USB drives based on the current platform:

| Platform | Detection Path | Excluded Volumes | Method |
|----------|---------------|-----------------|--------|
| macOS | `/Volumes/` | "Macintosh HD", "Macintosh HD - Data" | `_find_usb_drives_macos()` |
| Linux | `/media/$USER/`, `/mnt/` | "boot", "root" | `_find_usb_drives_linux()` |
| Windows | Drive letters A:–Z: | C: (system drive) | `_find_usb_drives_windows()` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.1.1 | v1.0.0 | [x] | Platform auto-detected at startup via `platform.system()` (`IS_MACOS`, `IS_LINUX`, `IS_WINDOWS`) |
| 6.1.2 | v1.0.0 | [x] | Excluded volumes defined in `EXCLUDED_USB_VOLUMES` constant (platform-conditional) |
| 6.1.3 | v1.0.0 | [x] | Single drive auto-selected; multiple drives prompt user selection via `select_usb_drive()` |

##### 6.2 Incremental Sync

The `_should_copy_file()` method shall determine whether a file needs copying:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.2.1 | v1.0.0 | [x] | Compares file size between source and destination |
| 6.2.2 | v1.0.0 | [x] | Compares modification time with 2-second FAT32 tolerance |
| 6.2.3 | v1.0.0 | [x] | Returns True (needs copy) if size differs or mtime is newer beyond tolerance |
| 6.2.4 | v1.0.0 | [x] | Existing up-to-date files are skipped (not re-copied) |

##### 6.3 Auto-Eject

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.3.1 | v1.0.0 | [x] | macOS: automatic eject via `diskutil eject /Volumes/<volume>` |
| 6.3.2 | v1.0.0 | [x] | Linux: automatic unmount via `udisksctl unmount` with fallback to `umount` |
| 6.3.3 | v1.0.0 | [x] | Windows: manual eject via Explorer (automatic eject not implemented; user notified) |

##### 6.4 USB Directory

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.4.1 | v1.0.0 | [x] | Default USB subdirectory: `DEFAULT_USB_DIR = "RZR/Music"` |
| 6.4.2 | v1.0.0 | [x] | Configurable via `--usb-dir` flag or `usb_dir` setting in config.yaml |
| 6.4.3 | v1.0.0 | [x] | Creates subdirectory structure on target drive if needed |

##### 6.5 Progress Tracking

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.5.1 | v1.0.0 | [x] | Reports files copied, skipped (up-to-date), and errors |
| 6.5.2 | v1.0.0 | [x] | Integrated into pipeline statistics (`usb_success`, `usb_destination`) |
| 6.5.3 | v1.0.0 | [x] | `--copy-to-usb` flag on `pipeline` command triggers USB sync as final stage |

##### 6.6 Standalone Sync

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.6.1 | v1.0.0 | [x] | `sync-usb` subcommand for standalone USB sync without pipeline |
| 6.6.2 | v1.0.0 | [x] | Optional `source_dir` argument; defaults to entire profile export directory |
| 6.6.3 | v1.0.0 | [x] | Preserves directory structure (flat or nested) on target drive |

##### 6.7 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 6.7.1 | v1.0.0 | [x] | No USB drive detected: clear message to check mount status, with platform-specific instructions |
| 6.7.2 | v1.0.0 | [x] | USB drive removed during sync: file copy error caught and reported |
| 6.7.3 | v1.0.0 | [x] | Eject failure on Linux: `udisksctl` failure falls back to `umount` |

---

## Library & Configuration

---

### SRS 7: Library Summary

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.4.0–v2.3.0

---

#### Purpose

Provide comprehensive library statistics covering both source (M4A) and export (MP3) collections, with tag integrity checking and multiple output modes for different use cases.

#### Requirements

##### 7.1 Summary Command

The `summary` subcommand shall display export library statistics in three modes:

| Mode | Flag | Description |
|------|------|-------------|
| Default | (none) | Aggregate stats + tag integrity + cover art + per-playlist table |
| Quick | `--quick` | Aggregate statistics only, no per-playlist breakdown |
| Detailed | `--detailed` | Default + extended per-playlist information and metadata |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.1.1 | v1.4.0 | [x] | `generate_summary(export_dir, detailed, quick, ...)` main entry point |
| 7.1.2 | v1.4.0 | [x] | `--export-dir` flag for custom export directory |
| 7.1.3 | v1.4.0 | [x] | `--no-library` flag skips source music/ directory scan |
| 7.1.4 | v1.7.0 | [x] | Available in interactive menu as "S. Show library summary" |

##### 7.2 Source Library Statistics (MusicLibraryStats)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.2.1 | v1.4.0 | [x] | Scans nested `music/Artist/Album/Track.m4a` directory structure |
| 7.2.2 | v1.4.0 | [x] | Tracks: `total_playlists`, `total_files`, `total_size_bytes` |
| 7.2.3 | v1.4.0 | [x] | Cross-references against export: `total_exported`, `total_unconverted` |
| 7.2.4 | v1.4.0 | [x] | `scan_duration` records scan time in seconds |
| 7.2.5 | v1.4.0 | [x] | Per-playlist stats in `playlists` list |

##### 7.3 Export Playlist Analysis (PlaylistSummary)

Per-playlist statistics:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.3.1 | v1.4.0 | [x] | `file_count` — Number of MP3 files |
| 7.3.2 | v1.4.0 | [x] | `total_size_bytes` — Total playlist size |
| 7.3.3 | v1.4.0 | [x] | `avg_file_size_mb` — Average file size |
| 7.3.4 | v1.4.0 | [x] | `last_modified` — Most recent modification timestamp |
| 7.3.5 | v1.4.0 | [x] | Tag integrity: `sample_files_checked`, `sample_files_with_tags` |
| 7.3.6 | v1.5.0 | [x] | Cover art: `files_with_cover_art`, `files_without_cover_art`, `files_with_original_cover_art`, `files_with_resized_cover_art` |

##### 7.4 Aggregate Statistics (LibrarySummaryStatistics)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.4.1 | v1.4.0 | [x] | `total_playlists`, `total_files`, `total_size_bytes`, `scan_duration` |
| 7.4.2 | v1.4.0 | [x] | Tag integrity: `sample_size`, `files_with_protection_tags`, `files_missing_protection_tags` |
| 7.4.3 | v1.5.0 | [x] | Cover art: `files_with_cover_art`, `files_without_cover_art` |
| 7.4.4 | v1.4.0 | [x] | `playlists: list[PlaylistSummary]` for per-playlist breakdown |

##### 7.5 Tag Integrity Checking

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.5.1 | v1.4.0 | [x] | `_check_tag_integrity()` scans ALL files (no sampling) |
| 7.5.2 | v1.4.0 | [x] | Checks for TXXX frames: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum` |
| 7.5.3 | v1.5.0 | [x] | Checks for APIC (cover art) frames |
| 7.5.4 | v1.5.0 | [x] | Distinguishes original vs. resized artwork via `OriginalCoverArtHash` TXXX |
| 7.5.5 | v1.4.0 | [x] | Uses same TXXX detection methods as `TaggerManager` for consistency |

##### 7.6 Display and Output

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.6.1 | v1.4.0 | [x] | Per-playlist table with files, tags, size, and last updated date |
| 7.6.2 | v1.4.0 | [x] | Export percentage and unconverted count from source library |
| 7.6.3 | v1.4.0 | [x] | Tag integrity percentages displayed |
| 7.6.4 | v1.5.0 | [x] | Cover art statistics integrated into summary |
| 7.6.5 | v1.4.0 | [x] | Graceful error handling: continues on permission errors, displays partial results |

##### 7.7 Web Dashboard Integration

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.7.1 | v2.0.0 | [x] | `GET /api/summary` endpoint returns summary data |
| 7.7.2 | v2.0.0 | [x] | `GET /api/library-stats` endpoint returns source library stats |
| 7.7.3 | v2.0.0 | [x] | Dashboard page displays library stats with sortable table |

##### 7.8 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 7.8.1 | v1.4.0 | [x] | Empty export directory: reports 0 playlists, no error |
| 7.8.2 | v1.4.0 | [x] | Permission errors on individual files: caught and skipped, partial results displayed |
| 7.8.3 | v1.4.0 | [x] | Missing music/ directory: library stats section skipped with message |

---

### SRS 8: Configuration

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.7.0–v2.3.0

---

#### Purpose

Provide a YAML-based configuration system, output profiles that control conversion behavior and tag handling, configurable output directory structures and filename formats, and all associated constants and resolution logic.

#### Requirements

##### 8.1 YAML Configuration (ConfigManager)

The `ConfigManager` class shall manage `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.1.1 | v1.7.0 | [x] | Reads and writes YAML format via PyYAML library |
| 8.1.2 | v1.7.0 | [x] | Auto-creates default `config.yaml` if missing (`_create_default()`) |
| 8.1.3 | v1.7.0 | [x] | Key methods: `get_setting()`, `update_setting()`, `_save()`, `_load_yaml()` |
| 8.1.4 | v1.7.0 | [x] | Playlist management: `get_playlist_by_key()`, `get_playlist_by_index()`, `add_playlist()`, `update_playlist()`, `remove_playlist()` |
| 8.1.5 | v1.7.0 | [x] | Playlist key lookup is case-insensitive |
| 8.1.6 | v1.7.0 | [x] | Duplicate key detection on `add_playlist()` |

Default settings:

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.1.7 | v1.7.0 | [x] | Default `output_type`: `DEFAULT_OUTPUT_TYPE = "ride-command"` |
| 8.1.8 | v1.7.0 | [x] | Default `usb_dir`: `DEFAULT_USB_DIR = "RZR/Music"` |
| 8.1.9 | v1.7.0 | [x] | Default `workers`: `DEFAULT_WORKERS = min(os.cpu_count(), 6)` |

##### 8.2 Settings Precedence

Settings shall follow a three-level precedence chain resolved by `resolve_config_settings()`:

1. **CLI flag** (highest priority)
2. **config.yaml setting**
3. **Hardcoded constant** (lowest priority)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.2.1 | v1.7.0 | [x] | Precedence chain implemented and documented |
| 8.2.2 | v1.7.0 | [x] | Each setting independently resolved (e.g., `--output-type` overrides config but config workers still apply) |
| 8.2.3 | v2.3.0 | [x] | `resolve_config_settings(args, config)` returns 5-tuple: `(output_type, usb_dir, workers, dir_structure, filename_format)` |
| 8.2.4 | v1.0.0 | [x] | `resolve_quality_preset(args, logger, output_profile)` handles preset + custom quality validation; returns resolved preset string or falls back to profile default |

##### 8.3 Default Constants

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.3.1 | v1.0.0 | [x] | `DEFAULT_MUSIC_DIR = "music"` |
| 8.3.2 | v1.0.0 | [x] | `DEFAULT_EXPORT_DIR = "export"` |
| 8.3.3 | v1.0.0 | [x] | `DEFAULT_LOG_DIR = "logs"` |
| 8.3.4 | v1.7.0 | [x] | `DEFAULT_CONFIG_FILE = "config.yaml"` |
| 8.3.5 | v1.6.0 | [x] | `DEFAULT_COOKIES = "cookies.txt"` |
| 8.3.6 | v1.0.0 | [x] | `DEFAULT_CLEANUP_OPTIONS` dictionary: `remove_id3v1: True`, `use_id3v23: True`, `remove_duplicates: True` |

##### 8.4 Output Profiles (OutputProfile)

The `OutputProfile` dataclass shall define conversion behavior per profile:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.4.1 | v1.7.0 | [x] | Field: `name` — Profile identifier |
| 8.4.2 | v1.7.0 | [x] | Field: `description` — Human-readable description |
| 8.4.3 | v2.3.0 | [x] | Field: `directory_structure` — `"flat"`, `"nested-artist"`, or `"nested-artist-album"` |
| 8.4.4 | v2.3.0 | [x] | Field: `filename_format` — `"full"` or `"title-only"` |
| 8.4.5 | v1.7.0 | [x] | Field: `id3_version` — `3` (ID3v2.3) or `4` (ID3v2.4) |
| 8.4.6 | v1.7.0 | [x] | Field: `strip_id3v1` — Remove ID3v1 tags (boolean) |
| 8.4.7 | v1.7.0 | [x] | Field: `title_tag_format` — e.g., `"artist_title"` |
| 8.4.8 | v1.7.0 | [x] | Field: `artwork_size` — `>0`=resize to max px, `0`=original, `-1`=strip |
| 8.4.9 | v1.7.0 | [x] | Field: `quality_preset` — Default conversion quality |
| 8.4.10 | v1.7.0 | [x] | Field: `pipeline_album` — `"playlist_name"` or `"original"` |
| 8.4.11 | v1.7.0 | [x] | Field: `pipeline_artist` — `"various"` or `"original"` |
| 8.4.12 | v2.3.0 | [x] | Profile override via `dataclasses.replace()` for CLI flag overrides (immutable base profiles) |

Built-in profiles:

| Profile | ID3 | Artwork | Quality | Album | Artist |
|---------|-----|---------|---------|-------|--------|
| `ride-command` | v2.3 | 100px | lossless | playlist name | "Various" |
| `basic` | v2.4 | original | lossless | original | original |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.4.13 | v1.7.0 | [x] | `ride-command` profile: default, optimized for Polaris Ride Command infotainment |
| 8.4.14 | v1.7.0 | [x] | `basic` profile: standard MP3 with original tags and artwork preserved |
| 8.4.15 | v1.7.0 | [x] | Profiles stored in `OUTPUT_PROFILES` dictionary |

##### 8.5 Profile-Scoped Export Directories

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.5.1 | v1.7.0 | [x] | Export paths scoped by profile: `export/<profile>/<playlist>/` |
| 8.5.2 | v1.7.0 | [x] | `get_export_dir(profile_name, playlist_key=None)` helper builds paths |
| 8.5.3 | v1.7.0 | [x] | Without `playlist_key`: returns `export/<profile>/` |
| 8.5.4 | v1.7.0 | [x] | With `playlist_key`: returns `export/<profile>/<playlist_key>/` |

##### 8.6 Directory Structures

The system shall support three directory structure modes, configurable per output profile:

| Value | Layout | Example Path |
|-------|--------|-------------|
| `flat` | All MP3s in a single directory | `export/ride-command/Pop_Workout/Artist - Title.mp3` |
| `nested-artist` | Subdirectories per artist | `export/ride-command/Pop_Workout/Taylor Swift/Title.mp3` |
| `nested-artist-album` | Subdirectories per artist and album | `export/ride-command/Pop_Workout/Taylor Swift/1989/Title.mp3` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.6.1 | v2.3.0 | [x] | `flat` directory structure works (existing behavior) |
| 8.6.2 | v2.3.0 | [x] | `nested-artist` directory structure creates artist subdirectories |
| 8.6.3 | v2.3.0 | [x] | `nested-artist-album` directory structure creates artist/album subdirectories |
| 8.6.4 | v2.3.0 | [x] | Artist and album directory names sanitized using existing `sanitize_filename()` |
| 8.6.5 | v2.3.0 | [x] | Subdirectories created automatically during conversion |
| 8.6.6 | v2.3.0 | [x] | Unknown artist defaults to `"Unknown Artist"` directory name |
| 8.6.7 | v2.3.0 | [x] | Unknown album defaults to `"Unknown Album"` directory name |
| 8.6.8 | v2.3.0 | [x] | `VALID_DIR_STRUCTURES = ("flat", "nested-artist", "nested-artist-album")` constant tuple |

##### 8.7 Filename Formats

The system shall support two filename format modes, configurable per output profile:

| Value | Pattern | Example |
|-------|---------|---------|
| `full` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title-only` | `Title.mp3` | `Shake It Off.mp3` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.7.1 | v2.3.0 | [x] | `full` filename format works (existing behavior) |
| 8.7.2 | v2.3.0 | [x] | `title-only` filename format produces title-only filenames |
| 8.7.3 | v2.3.0 | [x] | `VALID_FILENAME_FORMATS = ("full", "title-only")` constant tuple |

##### 8.8 Output Format CLI Flags

Settings shall follow the existing precedence chain: **CLI flag > config.yaml setting > profile default**

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `full`, `title-only` | Profile default |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.8.1 | v2.3.0 | [x] | `--dir-structure` flag added to `pipeline` subcommand |
| 8.8.2 | v2.3.0 | [x] | `--dir-structure` flag added to `convert` subcommand |
| 8.8.3 | v2.3.0 | [x] | `--filename-format` flag added to `pipeline` subcommand |
| 8.8.4 | v2.3.0 | [x] | `--filename-format` flag added to `convert` subcommand |

**config.yaml Settings:**

```yaml
settings:
  dir_structure: flat              # optional
  filename_format: artist_title    # optional
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.8.5 | v2.3.0 | [x] | `dir_structure` setting read from config.yaml |
| 8.8.6 | v2.3.0 | [x] | `filename_format` setting read from config.yaml |
| 8.8.7 | v2.3.0 | [x] | Omitted settings fall back to profile default |

**Profile Defaults:**

Both existing profiles shall retain their current defaults:

| Profile | directory_structure | filename_format |
|---------|-------------------|-----------------|
| `ride-command` | `flat` | `full` |
| `basic` | `flat` | `full` |

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.8.8 | v2.3.0 | [x] | `ride-command` profile defaults unchanged |
| 8.8.9 | v2.3.0 | [x] | `basic` profile defaults unchanged |

##### 8.9 Display Names

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.9.1 | v2.3.0 | [x] | `display_name(value)` helper converts flag values to human-readable names via `DISPLAY_NAMES` lookup with title-case fallback |
| 8.9.2 | v2.3.0 | [x] | `full` format displays as "Artist - Title" (custom override via `DISPLAY_NAMES`) |
| 8.9.3 | v2.3.0 | [x] | Other values display as title-cased with spaces (e.g., "Nested Artist Album", "Title Only") |
| 8.9.4 | v2.3.0 | [x] | CLI flag values remain hyphenated (e.g., `nested-artist-album`, `title-only`) |

##### 8.10 Backward Compatibility

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.10.1 | v2.3.0 | [x] | Default behavior identical to current behavior (zero regression) |
| 8.10.2 | v2.3.0 | [x] | `summary` command works with nested export directories |
| 8.10.3 | v2.3.0 | [x] | `cover-art` commands work with nested export directories |
| 8.10.4 | v2.3.0 | [x] | `sync-usb` preserves nested directory structure on target drive |
| 8.10.5 | v2.3.0 | [x] | `tag` command works with nested export directories |
| 8.10.6 | v2.3.0 | [x] | `restore` command works with nested export directories |

##### 8.11 Output Format Feature Parity (CLI & Web)

**CLI:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.11.1 | v2.3.0 | [x] | `--dir-structure` flag on `pipeline` command |
| 8.11.2 | v2.3.0 | [x] | `--dir-structure` flag on `convert` command |
| 8.11.3 | v2.3.0 | [x] | `--filename-format` flag on `pipeline` command |
| 8.11.4 | v2.3.0 | [x] | `--filename-format` flag on `convert` command |

**Web Dashboard:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.11.5 | v2.3.0 | [x] | Convert page: Directory Layout dropdown |
| 8.11.6 | v2.3.0 | [x] | Convert page: Filename Format dropdown |
| 8.11.7 | v2.3.0 | [x] | Pipeline page: Directory Layout dropdown |
| 8.11.8 | v2.3.0 | [x] | Pipeline page: Filename Format dropdown |
| 8.11.9 | v2.3.0 | [x] | Settings page: Profile comparison table includes directory structure |
| 8.11.10 | v2.3.0 | [x] | Settings page: Profile comparison table includes filename format |
| 8.11.11 | v2.3.0 | [x] | `/api/pipeline/run` accepts `dir_structure` parameter |
| 8.11.12 | v2.3.0 | [x] | `/api/pipeline/run` accepts `filename_format` parameter |
| 8.11.13 | v2.3.0 | [x] | `/api/convert/run` accepts `dir_structure` parameter |
| 8.11.14 | v2.3.0 | [x] | `/api/convert/run` accepts `filename_format` parameter |
| 8.11.15 | v2.3.0 | [x] | `/api/settings` GET returns valid `dir_structures` and `filename_formats` lists |
| 8.11.16 | v2.3.0 | [x] | `/api/directories/export` uses `rglob` for nested directory file counts |
| 8.11.17 | v2.3.0 | [x] | `cover-art embed` subcommand accepts `--dir-structure` and `--filename-format` flags |

##### 8.12 Output Format Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.12.1 | v2.3.0 | [x] | Startup banner displays active directory structure |
| 8.12.2 | v2.3.0 | [x] | Startup banner displays active filename format |
| 8.12.3 | v2.3.0 | [x] | Log files record active directory structure and filename format |
| 8.12.4 | v2.3.0 | [x] | `--dry-run` output shows full output path (including subdirectories for nested structures) |

##### 8.13 Output Format Validation

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.13.1 | v2.3.0 | [x] | Invalid `--dir-structure` value produces clear error with valid choices and non-zero exit |
| 8.13.2 | v2.3.0 | [x] | Invalid `--filename-format` value produces clear error with valid choices and non-zero exit |
| 8.13.3 | v2.3.0 | [x] | Invalid config.yaml values validated and rejected with clear error |

##### 8.14 Output Format Testing

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.14.1 | v2.3.0 | [x] | All 6 combinations (3 structures x 2 formats) tested with `--dry-run --verbose` |
| 8.14.2 | v2.3.0 | [x] | Default behavior unchanged (flat + artist_title) |
| 8.14.3 | v2.3.0 | [x] | CLI flag overrides config.yaml |
| 8.14.4 | v2.3.0 | [x] | config.yaml overrides profile default |
| 8.14.5 | v2.3.0 | [x] | `summary` command works with nested export directories |
| 8.14.6 | v2.3.0 | [x] | `cover-art embed` correctly matches files with non-default formats |
| 8.14.7 | v2.3.0 | [x] | `sync-usb` preserves nested structure on target drive |
| 8.14.8 | v2.3.0 | [x] | Filename collisions with `title-only` format handled correctly |
| 8.14.9 | v2.3.0 | [x] | Web UI dropdowns submit correct API parameters |

##### 8.15 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 8.15.1 | v1.7.0 | [x] | Missing `config.yaml`: auto-created with defaults on first run |
| 8.15.2 | v1.7.0 | [x] | Invalid profile name: rejected with error listing valid profiles |
| 8.15.3 | v1.7.0 | [x] | Duplicate playlist key on add: detected and reported |
| 8.15.4 | v2.3.0 | [x] | `title-only` format with duplicate titles: skip-if-exists behavior with warning suggesting `full` format |
| 8.15.5 | v2.3.0 | [x] | Artist/album directory names sanitized by `sanitize_filename()` (strips `/\:*?"<>\|`) |

Deeply nested paths: Very long artist + album + title combinations could exceed filesystem path length limits (255 chars on macOS/Linux). This is an existing limitation and is not addressed.

---

### SRS 9: Configurable Output Profiles

**Version:** 1.0  |  **Date:** 2026-02-22  |  **Status:** Implemented  |  **Implemented in:** v2.5.0

---

#### Purpose

Move output-type profile definitions from hardcoded Python dataclasses into `config.yaml`, enabling users to create, modify, and delete output profiles without editing source code. The two built-in profiles (`ride-command` and `basic`) become seed defaults that are written to `config.yaml` on first run, and all profile resolution thereafter reads from the config file.

---

#### Requirements

##### 9.1 Profile Definition in config.yaml

Output profiles shall be defined under a top-level `output_types` key in `config.yaml`:

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6

output_types:
  ride-command:
    description: "Polaris Ride Command infotainment system"
    directory_structure: flat
    filename_format: full
    id3_version: 3
    strip_id3v1: true
    title_tag_format: artist_title
    artwork_size: 100
    quality_preset: lossless
    pipeline_album: playlist_name
    pipeline_artist: various

  basic:
    description: "Standard MP3 with original tags and artwork"
    directory_structure: flat
    filename_format: full
    id3_version: 4
    strip_id3v1: true
    title_tag_format: artist_title
    artwork_size: 0
    quality_preset: lossless
    pipeline_album: original
    pipeline_artist: original

playlists:
  - key: Pop_Workout
    url: https://music.apple.com/us/playlist/...
    name: Pop Workout
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.1.1 | v2.5.0 | [x] | Profiles defined under `output_types` key in `config.yaml` as a YAML mapping of profile-name → field values |
| 9.1.2 | v2.5.0 | [x] | Each profile entry contains all `OutputProfile` fields except `name` (derived from the YAML key) |
| 9.1.3 | v2.5.0 | [x] | Field names in YAML use snake_case matching the `OutputProfile` dataclass (e.g., `directory_structure`, `id3_version`) |
| 9.1.4 | v2.5.0 | [x] | YAML types map naturally: strings for text fields, integers for `id3_version` and `artwork_size`, booleans for `strip_id3v1` |

##### 9.2 Seed Defaults

On first run or when `output_types` is absent from `config.yaml`, the system shall generate the section from built-in defaults:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.2.1 | v2.5.0 | [x] | Built-in defaults for `ride-command` and `basic` profiles defined as a constant (e.g., `DEFAULT_OUTPUT_PROFILES`) in source code |
| 9.2.2 | v2.5.0 | [x] | `ConfigManager._create_default()` includes the `output_types` section with both built-in profiles |
| 9.2.3 | v2.5.0 | [x] | When loading an existing `config.yaml` that has no `output_types` key, the built-in defaults are written to the file (automatic migration) |
| 9.2.4 | v2.5.0 | [x] | Migration preserves all other existing config.yaml content (settings, playlists) |
| 9.2.5 | v2.5.0 | [x] | After migration, the system reads profiles from config.yaml — not from built-in defaults |

##### 9.3 Profile Loading

`ConfigManager` shall load profiles from `config.yaml` and construct `OutputProfile` dataclass instances:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.3.1 | v2.5.0 | [x] | `_load_yaml()` parses the `output_types` mapping and builds `OutputProfile` instances |
| 9.3.2 | v2.5.0 | [x] | Loaded profiles stored in a dictionary accessible via `ConfigManager` (e.g., `config.output_profiles`) |
| 9.3.3 | v2.5.0 | [x] | The module-level `OUTPUT_PROFILES` dictionary is populated from `ConfigManager` at startup (not from hardcoded definitions) |
| 9.3.4 | v2.5.0 | [x] | `settings.output_type` must reference a profile name that exists in `output_types`; invalid references produce a clear error listing available profiles |

##### 9.4 Profile Validation

All profile fields shall be validated when loading from config.yaml:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.4.1 | v2.5.0 | [x] | Missing required fields produce a clear error naming the profile and missing field |
| 9.4.2 | v2.5.0 | [x] | `directory_structure` validated against `VALID_DIR_STRUCTURES` |
| 9.4.3 | v2.5.0 | [x] | `filename_format` validated against `VALID_FILENAME_FORMATS` |
| 9.4.4 | v2.5.0 | [x] | `id3_version` validated: must be `3` or `4` |
| 9.4.5 | v2.5.0 | [x] | `strip_id3v1` validated: must be boolean |
| 9.4.6 | v2.5.0 | [x] | `title_tag_format` validated: must be `"artist_title"` (currently the only supported value) |
| 9.4.7 | v2.5.0 | [x] | `artwork_size` validated: must be integer (`-1`, `0`, or positive) |
| 9.4.8 | v2.5.0 | [x] | `quality_preset` validated against `QUALITY_PRESETS` keys (`lossless`, `high`, `medium`, `low`) |
| 9.4.9 | v2.5.0 | [x] | `pipeline_album` validated: must be `"playlist_name"` or `"original"` |
| 9.4.10 | v2.5.0 | [x] | `pipeline_artist` validated: must be `"various"` or `"original"` |
| 9.4.11 | v2.5.0 | [x] | `description` validated: must be a non-empty string |
| 9.4.12 | v2.5.0 | [x] | Validation errors include the profile name and field name for easy debugging |
| 9.4.13 | v2.5.0 | [x] | All validation runs at startup; invalid profiles halt the program with a non-zero exit code |

##### 9.5 User-Defined Profiles

Users shall be able to add new profiles by editing `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.5.1 | v2.5.0 | [x] | New profiles added under `output_types` are automatically available at next startup |
| 9.5.2 | v2.5.0 | [x] | New profile names appear in `--output-type` CLI flag choices |
| 9.5.3 | v2.5.0 | [x] | New profiles appear in interactive menu's "Change output profile" (P) list |
| 9.5.4 | v2.5.0 | [x] | New profiles create their own export directory: `export/<profile-name>/` |
| 9.5.5 | v2.5.0 | [x] | Profile names validated: lowercase alphanumeric and hyphens only (e.g., `my-device`, `car-stereo`) |
| 9.5.6 | v2.5.0 | [x] | Invalid profile names rejected with clear error at startup |

##### 9.6 Modifying Built-in Profiles

Users shall be able to customize the built-in profiles by editing their values in `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.6.1 | v2.5.0 | [x] | Users can change any field of `ride-command` or `basic` profiles in config.yaml |
| 9.6.2 | v2.5.0 | [x] | Modified built-in profiles are loaded with the user's values (not overwritten by defaults) |
| 9.6.3 | v2.5.0 | [x] | Deleting a built-in profile from config.yaml is allowed — it will not be re-created on next run |

##### 9.7 Removing Hardcoded Profiles

The hardcoded `OUTPUT_PROFILES` dictionary in source code shall be replaced:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.7.1 | v2.5.0 | [x] | The hardcoded `OUTPUT_PROFILES` dictionary is removed from `porter_core.py` |
| 9.7.2 | v2.5.0 | [x] | A `DEFAULT_OUTPUT_PROFILES` constant retains the two built-in profile definitions as seed data only (used for migration and `_create_default()`) |
| 9.7.3 | v2.5.0 | [x] | All code that previously read from `OUTPUT_PROFILES` now reads from `ConfigManager`'s loaded profiles |
| 9.7.4 | v2.5.0 | [x] | The `OutputProfile` dataclass remains unchanged in source code |

##### 9.8 Interactive Menu Updates

The interactive menu profile selection (P option) shall reflect config-defined profiles:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.8.1 | v2.5.0 | [x] | "Change output profile" lists all profiles from config.yaml (not just hardcoded ones) |
| 9.8.2 | v2.5.0 | [x] | Profile selection persists to `settings.output_type` in config.yaml (existing behavior) |
| 9.8.3 | v2.5.0 | [x] | Profile descriptions displayed alongside names in selection menu |

##### 9.9 CLI Updates

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.9.1 | v2.5.0 | [x] | `--output-type` flag dynamically accepts any profile name from config.yaml |
| 9.9.2 | v2.5.0 | [x] | `--help` output for `--output-type` lists available profiles from config.yaml |
| 9.9.3 | v2.5.0 | [x] | Invalid `--output-type` value produces clear error listing available profiles |
| 9.9.4 | v2.5.0 | [x] | Profile override via `dataclasses.replace()` continues to work for CLI flag overrides (existing behavior) |

##### 9.10 Web Dashboard Updates

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.10.1 | v2.5.0 | [x] | `GET /api/settings` returns all profiles from config.yaml (not hardcoded) |
| 9.10.2 | v2.5.0 | [x] | Settings page profile comparison table shows all config-defined profiles |
| 9.10.3 | v2.5.0 | [x] | Profile selection dropdowns in pipeline/convert pages reflect config-defined profiles |

##### 9.11 Startup Banner

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.11.1 | v2.5.0 | [x] | Startup banner continues to display active profile name and description |
| 9.11.2 | v2.5.0 | [x] | Total available profiles count shown (e.g., `Profile: ride-command (1 of 3)`) |

##### 9.12 Config Persistence

Profile changes made through the application shall be saved back to config.yaml:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.12.1 | v2.5.0 | [x] | `ConfigManager._save()` writes the `output_types` section back to YAML preserving user-defined profiles |
| 9.12.2 | v2.5.0 | [x] | Round-trip fidelity: load → save produces equivalent YAML (no data loss or reordering) |
| 9.12.3 | v2.5.0 | [x] | YAML comments in config.yaml are not preserved (PyYAML limitation — document this) |

##### 9.13 Backward Compatibility

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.13.1 | v2.5.0 | [x] | Existing `config.yaml` files without `output_types` are automatically migrated (see 9.2.3) |
| 9.13.2 | v2.5.0 | [x] | After migration, behavior is identical to the current hardcoded profiles (zero regression) |
| 9.13.3 | v2.5.0 | [x] | `settings.output_type` continues to work as before — no changes to the settings key name |
| 9.13.4 | v2.5.0 | [x] | Profile-scoped export directories (`export/<profile>/`) continue to work unchanged |
| 9.13.5 | v2.5.0 | [x] | All CLI flags (`--output-type`, `--dir-structure`, `--filename-format`, `--preset`) continue to work unchanged |

##### 9.14 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 9.14.1 | v2.5.0 | [x] | Empty `output_types` mapping (`output_types: {}`): error — at least one profile required |
| 9.14.2 | v2.5.0 | [x] | `output_types` key present but value is `null`: treated as missing, triggers migration from defaults |
| 9.14.3 | v2.5.0 | [x] | `settings.output_type` references a deleted profile: error at startup listing available profiles |
| 9.14.4 | v2.5.0 | [x] | Profile with unknown extra fields: ignored (forward compatibility — new fields in future versions won't break older configs) |
| 9.14.5 | v2.5.0 | [x] | Duplicate profile names: impossible in YAML (last-key-wins per YAML spec) — no special handling needed |
| 9.14.6 | v2.5.0 | [x] | Profile name with spaces or special characters: rejected by name validation (9.5.5) with suggestion to use hyphens |
| 9.14.7 | v2.5.0 | [x] | config.yaml with only one profile: valid — system operates normally with a single profile |

---

## User Interfaces

---

### SRS 10: Interactive Menu

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.7.0–v2.3.0

---

#### Purpose

Provide a loop-based interactive menu interface for user-friendly operation without remembering CLI flags, with numbered playlist selection, letter-based action options, and automatic return to the menu after each operation.

#### Requirements

##### 10.1 Menu Interface

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
| 10.1.1 | v1.7.0 | [x] | `while True` loop returns to menu after each operation (except X) |
| 10.1.2 | v1.7.0 | [x] | Case-insensitive input handling |
| 10.1.3 | v1.7.0 | [x] | Post-processing prompts for USB copy after pipeline operations |
| 10.1.4 | v1.7.0 | [x] | Summary display with pause-to-review before returning to menu |
| 10.1.5 | v1.7.0 | [x] | Profile change persisted to config.yaml via `update_setting()` |
| 10.1.6 | v1.7.0 | [x] | New URLs saved to config.yaml via `add_playlist()` |

##### 10.2 Menu Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 10.2.1 | v1.7.0 | [x] | Decorative banner with numbered playlists followed by letter-based action options |
| 10.2.2 | v1.7.0 | [x] | Current output profile displayed in menu header |

##### 10.3 URL Entry Handler

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 10.3.1 | v1.7.0 | [x] | URL entry prompts for playlist key and name after URL is entered |
| 10.3.2 | v1.7.0 | [x] | New playlist saved to config.yaml for future use |

##### 10.4 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 10.4.1 | v1.7.0 | [x] | Empty Enter at menu: treated as Exit (X) |

---

### SRS 11: Web Dashboard

**Version:** 2.0  |  **Date:** 2026-02-23  |  **Status:** Complete  |  **Implemented in:** v2.0.0–v2.7.0

---

#### Purpose

Provide a browser-based dashboard with full feature parity to the CLI, enabling remote and visual operation of all music-porter capabilities with real-time progress streaming.

#### Requirements

##### 11.1 Flask Application

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.1.1 | v2.0.0 | [x] | Web dashboard implemented in `web_ui.py` as a Flask application |
| 11.1.2 | v2.0.0 | [x] | Launched via `music-porter web` subcommand with `--host` and `--port` flags |
| 11.1.3 | v2.0.0 | [x] | HTML templates served from `templates/` directory |
| 11.1.4 | v2.0.0 | [x] | `create_app(project_root=None)` factory pattern: creates Flask app, sets `PROJECT_ROOT` config, instantiates `TaskManager`, defines all routes, returns app |
| 11.1.5 | v2.0.0 | [x] | No authentication or CORS configured (development/trusted-network tool) |

##### 11.2 Dynamic Module Loading

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.2.1 | v2.0.0 | [x] | `music-porter` imported via `importlib.machinery.SourceFileLoader` (executable has no `.py` extension) |
| 11.2.2 | v2.0.0 | [x] | `mp._init_third_party()` called at import time to pre-load dependencies and avoid `DependencyChecker` in background threads |

##### 11.3 Security

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.3.1 | v2.0.0 | [x] | `_safe_dir(directory)` validates directories are within project root via `Path.resolve()` prefix check; returns absolute path string or `None` |

##### 11.4 Page Routes (9 pages)

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
| 11.4.1 | v2.0.0 | [x] | All 9 pages implemented and accessible |

##### 11.5 API Endpoints (~26 endpoints)

**Status & Info:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.1 | v2.0.0 | [x] | `GET /api/status` — System status, cookies, library stats, current profile |
| 11.5.2 | v2.0.0 | [x] | `GET /api/summary` — Export library statistics |
| 11.5.3 | v2.0.0 | [x] | `GET /api/library-stats` — Source music/ directory statistics |

**Cookie Management:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.4 | v2.0.0 | [x] | `GET /api/cookies/browsers` — Available browser list |
| 11.5.5 | v2.0.0 | [x] | `POST /api/cookies/refresh` — Auto-refresh cookies with browser selection |

**Playlist CRUD:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.6 | v2.0.0 | [x] | `GET /api/playlists` — List all playlists |
| 11.5.7 | v2.0.0 | [x] | `POST /api/playlists` — Add new playlist |
| 11.5.8 | v2.0.0 | [x] | `PUT /api/playlists/<key>` — Update existing playlist |
| 11.5.9 | v2.0.0 | [x] | `DELETE /api/playlists/<key>` — Remove playlist |

**Settings:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.10 | v2.0.0 | [x] | `GET /api/settings` — Get all settings, profiles, valid structures/formats |
| 11.5.11 | v2.0.0 | [x] | `POST /api/settings` — Update settings |

**Directory Listings:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.12 | v2.0.0 | [x] | `GET /api/directories/music` — List music/ playlists |
| 11.5.13 | v2.3.0 | [x] | `GET /api/directories/export` — List export/ playlists with file counts (uses rglob for nested dirs) |

**Operations:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.14 | v2.0.0 | [x] | `POST /api/pipeline/run` — Execute full pipeline (accepts `playlist`, `url`, `auto`, `dir_structure`, `filename_format`) |
| 11.5.15 | v2.0.0 | [x] | `POST /api/convert/run` — Convert M4A to MP3 (accepts `dir_structure`, `filename_format`) |
| 11.5.16 | v2.0.0 | [x] | `POST /api/tags/update` — Update album/artist tags |
| 11.5.17 | v2.0.0 | [x] | `POST /api/tags/restore` — Restore original tags |
| 11.5.18 | v2.0.0 | [x] | `POST /api/tags/reset` — Reset tags from source |
| 11.5.19 | v2.0.0 | [x] | `POST /api/cover-art/<action>` — Cover art: embed, extract, update, strip, resize |

**USB:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.20 | v2.0.0 | [x] | `GET /api/usb/drives` — List connected USB drives |
| 11.5.21 | v2.0.0 | [x] | `POST /api/usb/sync` — Sync files to USB |

**Task Management & Streaming:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.5.22 | v2.0.0 | [x] | `GET /api/tasks` — List all background tasks |
| 11.5.23 | v2.0.0 | [x] | `GET /api/tasks/<task_id>` — Get task details |
| 11.5.24 | v2.0.0 | [x] | `POST /api/tasks/<task_id>/cancel` — Cancel running task |
| 11.5.25 | v2.0.0 | [x] | `GET /api/stream/<task_id>` — SSE live log stream |

##### 11.6 Server-Sent Events (SSE) Live Streaming

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.6.1 | v2.0.0 | [x] | `GET /api/stream/<task_id>` provides real-time log streaming |
| 11.6.2 | v2.0.0 | [x] | Long-polling with 30-second heartbeat timeout |
| 11.6.3 | v2.0.0 | [x] | Message types: `log`, `progress`, `heartbeat`, `done` |
| 11.6.4 | v2.0.0 | [x] | Progress events include: `current`, `total`, `stage`, `percent` |
| 11.6.5 | v2.0.0 | [x] | Sentinel (`None`) in queue indicates task completion |
| 11.6.6 | v2.0.0 | [x] | JSON-formatted SSE data payloads |
| 11.6.7 | v2.0.0 | [x] | Progress throttling: events fire only on percentage change (mutable closure list `last_pct = [-1]`) |

##### 11.7 Background Task Management

**TaskState dataclass:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.7.1 | v2.0.0 | [x] | Fields: `id`, `operation`, `description`, `status`, `result`, `error`, `thread`, `cancel_event`, `log_queue`, `started_at`, `finished_at` |
| 11.7.2 | v2.0.0 | [x] | Status values: `pending`, `running`, `completed`, `failed`, `cancelled` |
| 11.7.3 | v2.0.0 | [x] | `elapsed()` method calculates task duration |
| 11.7.4 | v2.0.0 | [x] | `to_dict()` serialization returns 9-key dict with auto-calculated `elapsed` rounded to 1 decimal place |

**TaskManager class:**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.7.5 | v2.0.0 | [x] | `submit(operation, description, target)` spawns background thread, returns 12-char hex task_id |
| 11.7.6 | v2.0.0 | [x] | `get(task_id)` retrieves TaskState |
| 11.7.7 | v2.0.0 | [x] | `list_all()` returns all tasks as dicts |
| 11.7.8 | v2.0.0 | [x] | `cancel(task_id)` signals cancellation via `threading.Event` |
| 11.7.9 | v2.0.0 | [x] | `is_busy()` checks if any task is currently running |

##### 11.8 WebLogger

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.8.1 | v2.0.0 | [x] | `WebLogger` subclass of `Logger` routes messages to SSE queue |
| 11.8.2 | v2.0.0 | [x] | `_write(level, message)` strips ANSI escape codes via `_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')`, pushes to queue, and writes to log file |
| 11.8.3 | v2.0.0 | [x] | `file_info(message)` sends per-file progress messages to SSE queue (visible in web UI, unlike CLI) |
| 11.8.4 | v2.0.0 | [x] | `_make_progress_callback()` returns throttled progress event closure |
| 11.8.5 | v2.0.0 | [x] | `register_bar()` / `unregister_bar()` are no-ops (progress handled via SSE) |

##### 11.9 Client-Side UI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.9.1 | v2.0.0 | [x] | CDN-served Bootstrap 5.3.3 and Bootstrap Icons 1.11.3 from jsDelivr |
| 11.9.2 | v2.0.0 | [x] | Client-side toast notification system: `showToast(msg, type)` with 4-second auto-dismiss; types: `info`, `success`, `error`, `warning` |
| 11.9.3 | v2.0.0 | [x] | Client-side SSE log streaming via `EventSource` with auto-scrolling in log panels |
| 11.9.4 | v2.0.0 | [x] | Dynamic progress bar injection via `_ensureProgressBar()`: queries parent for `.sse-progress` div, creates and inserts if missing |
| 11.9.5 | v2.0.0 | [x] | Sortable dashboard table: click headers to sort, tracks `currentSort = {key, asc}` state, toggles direction on same-column clicks |
| 11.9.6 | v2.0.0 | [x] | Operations badge: polls `/api/tasks` every 10 seconds, shows count of running tasks in sidebar |
| 11.9.7 | v2.0.0 | [x] | Version/profile badge: fetches `/api/status` on page load, displays version in header and profile in sidebar |
| 11.9.8 | v2.0.0 | [x] | Cookie status badge on dashboard: three states — `bg-success` (valid), `bg-danger` (expired), `bg-warning` (missing) with refresh button |
| 11.9.9 | v2.0.0 | [x] | Pipeline mode toggle: `<select>` with 3 options (playlist/url/auto), conditional input visibility via `d-none` class |
| 11.9.10 | v2.0.0 | [x] | Task history table on operations page: reverse-sorted, status badges with 5 states, cancel buttons for running tasks only, duration formatting (`<60s` → `"X.Xs"`, `>=60s` → `"Xm Ys"`) |

##### 11.10 Feature Parity (CLI <-> Web)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.10.1 | v2.0.0 | [x] | Every CLI operation has a corresponding API endpoint |
| 11.10.2 | v2.0.0 | [x] | Pipeline, convert, tag, restore, reset, cover-art, USB sync all accessible from web |
| 11.10.3 | v2.0.0 | [x] | Settings and profile management available in web UI |
| 11.10.4 | v2.0.0 | [x] | Library summary and statistics displayed on dashboard |

##### 11.11 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.11.1 | v2.0.0 | [x] | Task already running: `submit()` returns None, client informed of busy state (HTTP 409) |
| 11.11.2 | v2.0.0 | [x] | SSE stream for nonexistent task: handled gracefully (HTTP 404) |
| 11.11.3 | v2.0.0 | [x] | Concurrent access: TaskManager serializes operations |
| 11.11.4 | vNEXT | [x] | Port already in use: before binding, kill any existing process listening on the target port; uses platform-appropriate method (macOS/Linux: `lsof`/`kill`, Windows: `netstat`/`taskkill`); best-effort with graceful fallback if kill fails |

##### 11.12 Setup and Prerequisites

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.12.1 | v2.0.0 | [x] | Flask listed as a dependency in `requirements.txt` and installed in the Python virtual environment |
| 11.12.2 | v2.0.0 | [x] | `music-porter web` launches the Flask server with optional `--host` (default `127.0.0.1`) and `--port` (default `5555`) flags |
| 11.12.3 | v2.0.0 | [x] | Default server URL is `http://127.0.0.1:5555`; printed to console on startup |
| 11.12.4 | v2.0.0 | [x] | `config.yaml` must exist (auto-created with defaults if missing) for playlists and settings at startup |
| 11.12.5 | v2.0.0 | [x] | Output profiles loaded from `config.yaml` into `mp.OUTPUT_PROFILES` at startup via `load_output_profiles()` |
| 11.12.6 | v2.0.0 | [x] | `mp._init_third_party()` called at module import time to pre-load dependencies before background threads start |
| 11.12.7 | v2.0.0 | [x] | `music-porter` imported via `importlib.machinery.SourceFileLoader` because the executable has no `.py` extension |

##### 11.13 API Request/Response Contracts

All API endpoints return JSON. Error responses use the shape `{"error": "<message>"}` with the appropriate HTTP status code unless otherwise noted.

**HTTP status code conventions:**

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Validation error (missing/invalid parameters) |
| 404 | Resource not found (task, playlist, directory) |
| 409 | Conflict (another operation already running, duplicate playlist key) |

**11.13.1 Status and Info Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.1.1 | v2.0.0 | [x] | `GET /api/status` returns 200 with JSON: `version` (string), `cookies` (object with `valid` bool, `exists` bool, `reason` string, `days_remaining` int or null), `library` (object with `playlists` int, `files` int, `size_mb` float), `profile` (string), `busy` (bool) |
| 11.13.1.2 | v2.0.0 | [x] | `GET /api/summary` returns 200 with JSON: `total_playlists` (int), `total_files` (int), `total_size_bytes` (int), `scan_duration` (float), `tag_integrity` (object with `checked`/`protected`/`missing` ints), `cover_art` (object with `with_art`/`without_art`/`original`/`resized` ints), `freshness` (object with `current`/`recent`/`stale`/`outdated` ints), `playlists` (array of objects with `name`, `file_count`, `size_bytes`, `avg_size_mb`, `last_modified` ISO8601 or null, `freshness`, `tags_checked`, `tags_protected`, `cover_with`, `cover_without`), `profile` (string) |
| 11.13.1.3 | v2.0.0 | [x] | `GET /api/library-stats` returns 200 with JSON: `total_playlists` (int), `total_files` (int), `total_size_bytes` (int), `total_exported` (int), `total_unconverted` (int), `scan_duration` (float) |

**11.13.2 Cookie Management Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.2.1 | v2.0.0 | [x] | `GET /api/cookies/browsers` returns 200 with JSON: `default` (string or null — detected default browser), `installed` (array of strings — available browser names) |
| 11.13.2.2 | v2.0.0 | [x] | `POST /api/cookies/refresh` accepts JSON body: `browser` (string, required — `"auto"` or browser name), `verbose` (bool, optional). Returns 200 with `{"task_id": "<hex>"}` on submission. Returns 409 with error if another operation is running |
| 11.13.2.3 | v2.0.0 | [x] | Cookie refresh task result contains: `success` (bool), `reason` (string), `days_remaining` (int or null) |

**11.13.3 Playlist CRUD Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.3.1 | v2.0.0 | [x] | `GET /api/playlists` returns 200 with JSON array of objects: `key` (string), `url` (string), `name` (string) |
| 11.13.3.2 | v2.0.0 | [x] | `POST /api/playlists` accepts JSON body with required fields: `key` (string, unique identifier), `url` (string, Apple Music URL), `name` (string, display name). Returns 200 with `{"ok": true}`. Returns 400 if any field is missing. Returns 409 if `key` already exists |
| 11.13.3.3 | v2.0.0 | [x] | `PUT /api/playlists/<key>` accepts JSON body with optional fields: `url` (string), `name` (string). Returns 200 with `{"ok": true}`. Returns 404 if `key` not found |
| 11.13.3.4 | v2.0.0 | [x] | `DELETE /api/playlists/<key>` returns 200 with `{"ok": true}`. Returns 404 if `key` not found |

**11.13.4 Directory Listing Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.4.1 | v2.0.0 | [x] | `GET /api/directories/music` returns 200 with JSON array of sorted directory name strings (non-hidden subdirectories of `music/`) |
| 11.13.4.2 | v2.0.0 | [x] | `GET /api/directories/export` returns 200 with JSON array of objects: `name` (string), `files` (int — count via `rglob` for nested directories). Scoped to current output profile: `export/<profile>/` |

**11.13.5 Settings Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.5.1 | v2.0.0 | [x] | `GET /api/settings` returns 200 with JSON: `settings` (object with `output_type` string, `usb_dir` string, `workers` int), `profiles` (object keyed by profile name, each with `description`, `quality_preset`, `artwork_size`, `id3_version`, `directory_structure`, `filename_format`), `quality_presets` (array of strings), `dir_structures` (array of strings), `filename_formats` (array of strings) |
| 11.13.5.2 | v2.0.0 | [x] | `POST /api/settings` accepts JSON body with any combination of: `output_type` (string), `usb_dir` (string), `workers` (int). Returns 200 with `{"ok": true}` |

**11.13.6 Pipeline Endpoint**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.6.1 | v2.0.0 | [x] | `POST /api/pipeline/run` accepts JSON body: `playlist` (string, optional — playlist key), `url` (string, optional — Apple Music URL), `auto` (bool, optional — process all playlists), `preset` (string, optional — quality preset), `copy_to_usb` (bool, optional), `dir_structure` (string, optional), `filename_format` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Exactly one of `playlist`, `url`, or `auto` must be provided |
| 11.13.6.2 | v2.0.0 | [x] | Pipeline returns 200 with `{"task_id": "<hex>"}` on submission. Returns 400 if none of `playlist`/`url`/`auto` provided. Returns 409 if another operation is running |
| 11.13.6.3 | v2.0.0 | [x] | Pipeline task result contains: `success` (bool), `playlists` (int — count, for auto mode) |

**11.13.7 Convert Endpoint**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.7.1 | v2.0.0 | [x] | `POST /api/convert/run` accepts JSON body: `input_dir` (string, required — relative path under `music/`), `output_dir` (string, optional — defaults to `export/<profile>/`), `preset` (string, optional — defaults to `"lossless"`), `force` (bool, optional), `no_cover_art` (bool, optional), `dir_structure` (string, optional), `filename_format` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional) |
| 11.13.7.2 | v2.0.0 | [x] | Convert returns 200 with `{"task_id": "<hex>"}`. Returns 400 if `input_dir` is missing or fails `_safe_dir()` validation. Returns 409 if another operation is running |
| 11.13.7.3 | v2.0.0 | [x] | Convert task result contains: `success` (bool) |

**11.13.8 Tag Operation Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.8.1 | v2.0.0 | [x] | `POST /api/tags/update` accepts JSON body: `directory` (string, required — relative path under `export/`), `album` (string, optional), `artist` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` is missing or fails `_safe_dir()`. Returns 409 if busy |
| 11.13.8.2 | v2.0.0 | [x] | `POST /api/tags/restore` accepts JSON body: `directory` (string, required), `all` (bool, optional — restore all fields), `album` (bool, optional), `title` (bool, optional), `artist` (bool, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` invalid. Returns 409 if busy |
| 11.13.8.3 | v2.0.0 | [x] | `POST /api/tags/reset` accepts JSON body: `input_dir` (string, required — source M4A directory), `output_dir` (string, required — target MP3 directory), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if either directory is missing or fails `_safe_dir()`. Returns 409 if busy |
| 11.13.8.4 | v2.0.0 | [x] | All tag operation task results contain: `success` (bool) |

**11.13.9 Cover Art Endpoint**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.9.1 | v2.0.0 | [x] | `POST /api/cover-art/<action>` where `<action>` is one of: `embed`, `extract`, `update`, `strip`, `resize`. Returns 400 if action is not one of the five valid values |
| 11.13.9.2 | v2.0.0 | [x] | Common parameters for all cover art actions: `directory` (string, required — relative path under `export/`), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` invalid. Returns 409 if busy |
| 11.13.9.3 | v2.0.0 | [x] | Action-specific parameters: `embed` accepts `source` (string, optional — M4A source directory, auto-derived from export path if omitted) and `force` (bool, optional); `update` accepts `image` (string, optional — path to image file); `resize` accepts `max_size` (int, optional — default 100 pixels) |
| 11.13.9.4 | v2.0.0 | [x] | Cover art task result contains: `success` (bool). For `update` action, may also include `error` (string) if image validation fails |

**11.13.10 USB Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.10.1 | v2.0.0 | [x] | `GET /api/usb/drives` returns 200 with JSON array of objects: `mount_point` (string), `name` (string), `size_gb` (float) |
| 11.13.10.2 | v2.0.0 | [x] | `POST /api/usb/sync` accepts JSON body: `source_dir` (string, required — relative path under `export/`), `volume` (string, required — mount point or drive letter), `usb_dir` (string, optional — default `"RZR/Music"`), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `source_dir` or `volume` missing. Returns 409 if busy |
| 11.13.10.3 | v2.0.0 | [x] | USB sync task result contains: `success` (bool), `files_found` (int), `files_copied` (int), `files_skipped` (int), `files_failed` (int) |

**11.13.11 Task Management Endpoints**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.11.1 | v2.0.0 | [x] | `GET /api/tasks` returns 200 with JSON array of task objects: `id` (string — 12-char hex), `operation` (string), `description` (string), `status` (string — `pending`/`running`/`completed`/`failed`/`cancelled`), `result` (object or null), `error` (string or null), `elapsed` (float — seconds, rounded to 1 decimal), `started_at` (float — Unix timestamp), `finished_at` (float or null) |
| 11.13.11.2 | v2.0.0 | [x] | `GET /api/tasks/<task_id>` returns 200 with single task object (same schema as list). Returns 404 if `task_id` not found |
| 11.13.11.3 | v2.0.0 | [x] | `POST /api/tasks/<task_id>/cancel` returns 200 with `{"ok": true}` if task was running and cancel signal sent. Returns 404 if `task_id` not found or task is not in `running` status |
| 11.13.11.4 | v2.0.0 | [x] | `GET /api/stream/<task_id>` returns SSE stream (`text/event-stream`) with headers `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Returns 404 if `task_id` not found |

**11.13.12 SSE Event Contracts**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.12.1 | v2.0.0 | [x] | SSE `log` event payload: `{"type": "log", "level": "INFO\|WARN\|ERROR", "message": "<text>"}` — ANSI escape codes stripped before sending |
| 11.13.12.2 | v2.0.0 | [x] | SSE `progress` event payload: `{"type": "progress", "current": <int>, "total": <int>, "percent": <int>, "stage": "<text>"}` — throttled to fire only on percentage change |
| 11.13.12.3 | v2.0.0 | [x] | SSE `heartbeat` event payload: `{"type": "heartbeat"}` — sent when queue is empty for 30 seconds |
| 11.13.12.4 | v2.0.0 | [x] | SSE `done` event payload: `{"type": "done", "status": "completed\|failed\|cancelled", "result": <object or null>, "error": "<string or null>"}` — sent once on task completion, acts as sentinel |

**11.13.13 Common API Conventions**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.13.1 | v2.0.0 | [x] | All directory parameters are validated via `_safe_dir()` which resolves the path and confirms it is within the project root; returns `None` (triggering 400) if the path escapes the project root |
| 11.13.13.2 | v2.0.0 | [x] | All background operations follow the task submission pattern: POST request → validation → `task_manager.submit()` → return `{"task_id": "<hex>"}` or error. Frontend subscribes to `/api/stream/<task_id>` for live updates |
| 11.13.13.3 | v2.0.0 | [x] | `task_manager.submit()` returns `None` when another task is already running, resulting in HTTP 409 response |
| 11.13.13.4 | v2.0.0 | [x] | POST/PUT endpoints parse request body with `request.get_json(force=True)` (strict JSON required) or `request.get_json(silent=True) or {}` (optional JSON with empty-dict fallback) |

**11.13.14 Edge Cases**

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.14.1 | v2.0.0 | [x] | Directory path traversal attempt (e.g., `../etc/passwd`): `_safe_dir()` returns `None`, endpoint returns 400 |
| 11.13.14.2 | v2.0.0 | [x] | Missing required JSON body on POST: endpoint returns 400 with descriptive error message |
| 11.13.14.3 | v2.0.0 | [x] | SSE stream for completed task: stream replays final `done` event immediately |
| 11.13.14.4 | v2.0.0 | [x] | Pipeline called with no mode (`playlist`, `url`, or `auto` all absent): returns 400 with error |
| 11.13.14.5 | v2.0.0 | [x] | Cover art `update` action with invalid image path: task completes with `success: false` and `error` message in result |

##### 11.14 Template Linting (djLint)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.14.1 | v2.7.0 | [x] | `djlint` added to `requirements-dev.txt` as a development dependency |
| 11.14.2 | v2.7.0 | [x] | djLint configuration in `pyproject.toml` under `[tool.djlint]` with `profile = "jinja"` |
| 11.14.3 | v2.7.0 | [x] | Lint check command: `djlint templates/ --lint` — checks all 10 HTML templates for linting issues |
| 11.14.4 | v2.7.0 | [x] | Format check command: `djlint templates/ --check` — verifies template formatting without modifying files |
| 11.14.5 | v2.7.0 | [x] | CLAUDE.md linting section updated to include djLint commands alongside Ruff and PyMarkdown |

---

### SRS 12: CLI & Runtime

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v1.0.0–v2.3.0

---

#### Purpose

Provide the command-line interface, runtime infrastructure, and cross-cutting concerns — including the startup banner, argument parsing, subcommand routing, dependency checking, logging, progress bars, platform detection, and virtual environment auto-activation.

#### Requirements

##### 12.1 CLI Subcommand Architecture

The tool shall provide the following subcommands via `argparse`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.1.1 | v1.0.0 | [x] | `pipeline` — Full download + convert + tag workflow |
| 12.1.2 | v1.0.0 | [x] | `download` — Download from Apple Music |
| 12.1.3 | v1.0.0 | [x] | `convert` — Convert M4A → MP3 |
| 12.1.4 | v1.0.0 | [x] | `tag` — Update tags on existing MP3s |
| 12.1.5 | v1.0.0 | [x] | `restore` — Restore original tags from TXXX frames |
| 12.1.6 | v1.0.0 | [x] | `reset` — Reset tags from source M4A files |
| 12.1.7 | v1.0.0 | [x] | `sync-usb` — Copy files to USB drive |
| 12.1.8 | v1.5.0 | [x] | `cover-art` — Cover art management (embed, extract, update, strip, resize) |
| 12.1.9 | v1.4.0 | [x] | `summary` — Display export library statistics |
| 12.1.10 | v2.0.0 | [x] | `web` — Launch web dashboard |
| 12.1.11 | v1.0.0 | [x] | Main command routing via argparse subparsers |

##### 12.2 Shared Argument Parsers

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.2.1 | v1.0.0 | [x] | `_create_quality_args_parser()` creates shared parent parser with `--preset` and `--quality` arguments |
| 12.2.2 | v1.6.0 | [x] | `_create_cookie_args_parser()` creates shared parent parser with `--cookies`, `--auto-refresh-cookies`, and `--skip-cookie-validation` arguments |
| 12.2.3 | v1.0.0 | [x] | `_create_usb_args_parser()` creates shared parent parser with `--usb-dir` argument |
| 12.2.4 | v1.0.0 | [x] | `positive_int(value)` argparse type function: validates integer >= 1, raises `ArgumentTypeError` for invalid values |

##### 12.3 Global Flags

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.3.1 | v1.0.0 | [x] | `--dry-run` — Preview changes without modifying files |
| 12.3.2 | v1.0.0 | [x] | `--verbose` / `-v` — Enable verbose output |
| 12.3.3 | v1.0.0 | [x] | `--version` — Show version and exit |
| 12.3.4 | v1.0.0 | [x] | `--workers N` — Set parallel conversion workers |
| 12.3.5 | v1.7.0 | [x] | `--output-type TYPE` — Select output profile |

##### 12.4 Startup Banner

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.4.1 | v1.0.0 | [x] | Decorative `╔═══╗` / `╚═══╝` box format with dynamic width based on banner text length |
| 12.4.2 | v1.0.0 | [x] | Banner text: `"Music Porter v{VERSION}"` centered in box |
| 12.4.3 | v1.0.0 | [x] | Startup info lines displayed after banner: Platform, Command, Output type, Quality, Artwork, Dir layout, File names, Workers, Cookies |
| 12.4.4 | v1.0.0 | [x] | Startup info logged to file only (not console) via `logger.file_info()` |
| 12.4.5 | v1.0.0 | [x] | `VERSION` constant defined at line 69 of `music-porter` |

##### 12.5 Dependency Checking

The `DependencyChecker` class shall verify all required dependencies:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.5.1 | v1.0.0 | [x] | `check_all(require_ffmpeg, require_gamdl)` checks all dependencies and returns bool |
| 12.5.2 | v1.0.0 | [x] | `check_python_packages()` checks all packages from `requirements.txt` and installs missing ones via pip |
| 12.5.3 | v1.0.0 | [x] | `display_summary(config)` prints formatted dependency summary with checkmarks |
| 12.5.4 | v1.0.0 | [x] | `IMPORT_MAP` dictionary maps pip package names to Python import names: `{'ffmpeg-python': 'ffmpeg', 'webdriver-manager': 'webdriver_manager', 'Pillow': 'PIL', 'PyYAML': 'yaml', 'Flask': 'flask'}` |
| 12.5.5 | v1.0.0 | [x] | FFmpeg not installed: detects missing binary and provides install instructions per platform (macOS: `brew`, Linux: `apt-get`/`dnf`/`pacman`, Windows: Chocolatey) |

##### 12.6 Logging System

The `Logger` class shall provide timestamped logging to console and file:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.6.1 | v1.0.0 | [x] | Log files stored in `logs/` directory with `%Y-%m-%d_%H-%M-%S.log` naming |
| 12.6.2 | v1.0.0 | [x] | Thread-safe writes via `threading.Lock` |
| 12.6.3 | v1.0.0 | [x] | Log methods: `info()`, `debug()`, `warn()`, `error()`, `success()`, `dry_run()`, `file_info()`, `skip()` |
| 12.6.4 | v1.0.0 | [x] | Console routing through `tqdm.write()` when progress bar is active (`register_bar()` / `unregister_bar()`) |
| 12.6.5 | v1.0.0 | [x] | `--verbose` flag enables debug-level output |
| 12.6.6 | v1.0.0 | [x] | `--version` flag displays current version |
| 12.6.7 | v1.0.0 | [x] | `Logger.skip(message)` logs skip messages for skipped operations |
| 12.6.8 | v1.0.0 | [x] | `Logger.file_info(message)` writes to log file only, not console |

##### 12.7 Progress Bars

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.7.1 | v1.0.0 | [x] | Uses `tqdm` library for progress display |
| 12.7.2 | v1.0.0 | [x] | `ProgressBar` context manager wraps tqdm with custom formatting (`__enter__`/`__exit__`) |
| 12.7.3 | v1.0.0 | [x] | Terminal state saved/restored via `_save_terminal()` and `_restore_terminal()` |
| 12.7.4 | v1.0.0 | [x] | Logger integrates with progress bar via `register_bar()` / `unregister_bar()` for write routing |
| 12.7.5 | v1.0.0 | [x] | Progress bars disabled during `--dry-run` mode |

##### 12.8 Third-Party Import Deferral

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.8.1 | v1.0.0 | [x] | `_init_third_party()` defers tqdm import until after `DependencyChecker` has ensured packages exist |
| 12.8.2 | v1.0.0 | [x] | Sets `tqdm.monitor_interval = 0` to prevent TMonitor thread from interfering with `input()` |

##### 12.9 Platform Detection

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.9.1 | v1.0.0 | [x] | `CURRENT_OS = platform.system()` returns `'Darwin'`, `'Linux'`, or `'Windows'` |
| 12.9.2 | v1.0.0 | [x] | Boolean constants: `IS_MACOS`, `IS_LINUX`, `IS_WINDOWS` |
| 12.9.3 | v1.0.0 | [x] | `get_os_display_name()` returns friendly names: `"macOS"`, `"Linux"`, `"Windows"` |

##### 12.10 Dry-Run Mode

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.10.1 | v1.0.0 | [x] | Global `--dry-run` flag passed through all operations |
| 12.10.2 | v1.0.0 | [x] | `logger.dry_run(message)` writes messages with `[DRY-RUN]` prefix |
| 12.10.3 | v1.0.0 | [x] | File write operations conditionally skipped when `dry_run=True` |
| 12.10.4 | v1.0.0 | [x] | Progress bars disabled during dry-run |
| 12.10.5 | v1.0.0 | [x] | No files created, modified, or deleted in dry-run mode |

##### 12.11 Virtual Environment Auto-Activation

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.11.1 | v1.0.0 | [x] | `_auto_activate_venv()` detects and re-execs under `.venv/bin/python` if available |
| 12.11.2 | v1.0.0 | [x] | Supports macOS/Linux (`.venv/bin/python`) and Windows (`.venv/Scripts/python.exe`) |
| 12.11.3 | v1.0.0 | [x] | Uses `os.execv()` for transparent re-launch |

##### 12.12 Web Subcommand

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.12.1 | v2.0.0 | [x] | `web` subcommand dynamically imports `web_ui.py` via `importlib` |
| 12.12.2 | v2.0.0 | [x] | Fallback with clear error message if Flask is not installed |

##### 12.13 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 12.13.1 | v1.0.0 | [x] | FFmpeg not installed: `DependencyChecker` detects missing binary and provides platform-specific install instructions |
| 12.13.2 | v1.0.0 | [x] | Thread worker crash: caught by ThreadPoolExecutor, counted as error in statistics |
| 12.13.3 | v1.0.0 | [x] | KeyboardInterrupt handling in confirmation prompts: caught and handled gracefully |

---

## Architecture

---

### SRS 13: Service Layer

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Complete  |  **Implemented in:** v2.4.0

---

#### Purpose

Decouple the `music-porter` business logic from all user interface concerns — console `print()` output, `input()` prompts, and progress bars — so that the same core classes can be driven by the CLI, the Interactive CLI menu, and the Web dashboard without modification. Business logic classes shall return structured result objects and accept callback functions for user interaction, never directly reading from stdin or writing to stdout.

---

#### Requirements

##### 13.1 Service Layer Architecture

Each business logic class shall return structured result objects instead of printing summaries directly. All operations that currently call `_print_*_summary()` internally shall instead populate a result/statistics object and return it to the caller. The caller (CLI, Interactive Menu, or Web handler) is responsible for presenting results.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.1.1 | v2.4.0 | [x] | Every public method on a business logic class (`TaggerManager`, `Converter`, `Downloader`, `CookieManager`, `USBManager`, `SummaryManager`, `CoverArtManager`, `PipelineOrchestrator`) shall return a structured result object (dataclass or typed dict) containing all data currently printed in its summary |
| 13.1.2 | v2.4.0 | [x] | No business logic class shall call `print()` for summary display. All `_print_*_summary()` methods shall be removed from the business logic classes and replaced with result object population |
| 13.1.3 | v2.4.0 | [x] | No business logic class shall call `input()`. All user interaction shall be delegated through callback interfaces (see 13.2) |
| 13.1.4 | v2.4.0 | [x] | Business logic classes shall accept an optional `Logger` instance (as today) but shall not assume that logging implies console output — `Logger` continues to write to log files and may optionally echo to console at the caller's discretion |
| 13.1.5 | v2.4.0 | [x] | Existing `*Statistics` classes (`TagStatistics`, `ConversionStatistics`, `DownloadStatistics`, `PipelineStatistics`, `AggregateStatistics`, `LibrarySummaryStatistics`) shall continue to serve as the structured result objects — they already track the data, but callers shall now receive them as return values rather than having the business class print them |

###### 13.1.6 Result Objects

Each operation shall return a result object. The following table defines the minimum fields per result type. Fields marked "(existing)" are already tracked in the corresponding `*Statistics` class; fields marked "(new)" must be added.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.1.6 | v2.4.0 | [x] | `TaggerManager.update_tags()` shall return a `TagUpdateResult` containing: `success: bool`, `directory: str`, `duration: float`, `files_processed: int`, `files_updated: int`, `files_skipped: int`, `errors: int`, `title_updated: int` (existing), `album_updated: int` (existing), `artist_updated: int` (existing), `title_stored: int` (existing), `artist_stored: int` (existing), `album_stored: int` (existing) |
| 13.1.7 | v2.4.0 | [x] | `TaggerManager.restore_tags()` shall return a `TagRestoreResult` containing: `success: bool`, `directory: str`, `duration: float`, `files_processed: int`, `files_restored: int`, `files_skipped: int`, `errors: int`, `title_restored: int` (existing), `artist_restored: int` (existing), `album_restored: int` (existing) |
| 13.1.8 | v2.4.0 | [x] | `TaggerManager.reset_tags_from_source()` shall return a `TagResetResult` containing: `success: bool`, `input_dir: str`, `output_dir: str`, `duration: float`, `files_matched: int`, `files_reset: int`, `files_skipped: int`, `errors: int` |
| 13.1.9 | v2.4.0 | [x] | `Converter.convert()` shall return a `ConversionResult` containing: `success: bool`, `input_dir: str`, `output_dir: str`, `duration: float`, `quality_preset: str`, `quality_mode: str`, `quality_value: str`, `workers: int`, `total_found: int` (existing), `converted: int` (existing), `overwritten: int` (existing), `skipped: int` (existing), `errors: int` (existing) |
| 13.1.10 | v2.4.0 | [x] | `Downloader.download()` shall return a `DownloadResult` containing: `success: bool`, `key: str`, `album_name: str`, `duration: float`, `playlist_total: int` (existing), `downloaded: int` (existing), `skipped: int` (existing), `failed: int` (existing) |
| 13.1.11 | v2.4.0 | [x] | `USBManager.sync_to_usb()` shall return a `USBSyncResult` containing: `success: bool`, `source: str`, `destination: str`, `volume_name: str`, `duration: float`, `files_found: int` (existing), `files_copied: int` (existing), `files_skipped: int` (existing), `files_failed: int` (existing) |
| 13.1.12 | v2.4.0 | [x] | `SummaryManager.generate_summary()` shall return a `LibrarySummaryResult` containing: `success: bool`, `export_dir: str`, `scan_duration: float`, `mode: str` (quick/default/detailed), `total_playlists: int`, `total_files: int`, `total_size_bytes: int`, `avg_file_size: float`, `files_with_protection_tags: int`, `files_missing_protection_tags: int`, `sample_size: int`, `files_with_cover_art: int`, `files_without_cover_art: int`, `files_with_original_cover_art: int`, `files_with_resized_cover_art: int`, `playlist_summaries: list[PlaylistSummary]` |
| 13.1.13 | v2.4.0 | [x] | `CoverArtManager` action methods (`embed()`, `extract()`, `update()`, `strip()`) shall each return a `CoverArtResult` containing: `success: bool`, `action: str`, `directory: str`, `duration: float`, `files_processed: int`, `files_modified: int`, `files_skipped: int`, `errors: int` |
| 13.1.14 | v2.4.0 | [x] | `PipelineOrchestrator.run_pipeline()` shall return a `PipelineResult` containing: `success: bool`, `playlist_name: str`, `playlist_key: str`, `duration: float`, `stages_completed: list[str]`, `stages_failed: list[str]`, `stages_skipped: list[str]`, plus nested results: `download_result: DownloadResult | None`, `conversion_result: ConversionResult | None`, `tag_result: TagUpdateResult | None`, `cover_art_result: CoverArtResult | None`, `usb_result: USBSyncResult | None` |
| 13.1.15 | v2.4.0 | [x] | `PipelineOrchestrator.run_batch()` (or equivalent batch method) shall return an `AggregateResult` containing: `success: bool`, `duration: float`, `total_playlists: int`, `successful_playlists: int`, `failed_playlists: int`, `playlist_results: list[PipelineResult]`, `cumulative_stats: dict` (same shape as `AggregateStatistics.get_cumulative_stats()`) |

##### 13.2 User Input Abstraction

All embedded `input()` calls in business logic classes shall be replaced with callback functions. Each class that currently prompts the user shall accept an optional `UserPromptHandler` (protocol/interface) at construction. When no handler is provided, the class shall use sensible non-interactive defaults (fail-safe: deny destructive actions, skip optional prompts).

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.2.1 | v2.4.0 | [x] | A `UserPromptHandler` protocol shall define the following methods, each returning the user's response asynchronously or synchronously depending on the interface |
| 13.2.2 | v2.4.0 | [x] | `confirm(message: str, default: bool) -> bool` — for yes/no confirmations. The `default` parameter indicates the default answer when the user provides no input. Used by: cookie refresh prompt (`default=True`), continue-without-cookies prompt (`default=False`), download confirmation (`default=False`), USB eject prompt (`default=False`), USB copy prompt (`default=False`), save-to-config prompt (`default=False`), embed-cover-art prompt (`default=True`), cover-art batch continue (`default=True`), dependency warning continue (`default=True`) |
| 13.2.3 | v2.4.0 | [x] | `confirm_destructive(message: str) -> bool` — for destructive operations requiring explicit typed confirmation (e.g., `reset_tags_from_source` which currently requires typing "yes"). Non-interactive default: `False` (deny) |
| 13.2.4 | v2.4.0 | [x] | `select_from_list(prompt: str, options: list[str], allow_cancel: bool) -> int | None` — for numbered menu selections. Returns 0-based index of selected option, or `None` if cancelled. Used by: USB drive selection, browser selection. Non-interactive default: `None` (cancel) |
| 13.2.5 | v2.4.0 | [x] | `get_text_input(prompt: str, default: str | None) -> str | None` — for free-text input. Used by: URL entry, cover art resize dimension. Returns `None` if cancelled. Non-interactive default: return `default` |
| 13.2.6 | v2.4.0 | [x] | `wait_for_continue(message: str) -> None` — for modal pauses that block until the user acknowledges (e.g., "Press Enter after logging in...", "Press Enter to continue..."). Non-interactive default: return immediately |
| 13.2.7 | v2.4.0 | [x] | When no `UserPromptHandler` is provided (or `None`), business logic classes shall use a `NonInteractivePromptHandler` that returns fail-safe defaults: `confirm()` returns `default`, `confirm_destructive()` returns `False`, `select_from_list()` returns `None`, `get_text_input()` returns `default`, `wait_for_continue()` returns immediately |

###### 13.2.8 Input Call Migration Map

The following table maps every current `input()` call to the `UserPromptHandler` method that replaces it.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.2.8 | v2.4.0 | [x] | `Downloader.download()` line ~2171 ("Attempt automatic cookie refresh? [Y/n]") shall call `prompt_handler.confirm(message, default=True)` |
| 13.2.9 | v2.4.0 | [x] | `Downloader.download()` line ~2185 ("Continue without valid cookies? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 13.2.10 | v2.4.0 | [x] | `Downloader.download()` line ~2191 ("Continue without valid cookies? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 13.2.11 | v2.4.0 | [x] | `Downloader.download()` line ~2202 ("Download {key}? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 13.2.12 | v2.4.0 | [x] | `CookieManager._extract_with_selenium()` line ~2587 ("Select browser [1]...") shall call `prompt_handler.select_from_list(prompt, browser_list, allow_cancel=True)` |
| 13.2.13 | v2.4.0 | [x] | `CookieManager._extract_cookies_from_driver()` line ~2883 ("Press Enter after logging in...") shall call `prompt_handler.wait_for_continue(message)` |
| 13.2.14 | v2.4.0 | [x] | `USBManager.select_usb_drive()` line ~3209 ("Select drive:") shall call `prompt_handler.select_from_list(prompt, drive_list, allow_cancel=True)` |
| 13.2.15 | v2.4.0 | [x] | `USBManager._prompt_and_eject_usb()` line ~3413 ("Eject USB drive '{name}'? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 13.2.16 | v2.4.0 | [x] | `TaggerManager.reset_tags_from_source()` line ~1534 ("Type 'yes' to continue...") shall call `prompt_handler.confirm_destructive(message)` |
| 13.2.17 | v2.4.0 | [x] | `PipelineOrchestrator._ask_save_to_config()` line ~5044 ("Save '{album_name}' to config.yaml? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 13.2.18 | v2.4.0 | [x] | `PipelineOrchestrator._check_and_embed_cover_art()` line ~5094 ("Embed cover art from source files? [Y/n]") shall call `prompt_handler.confirm(message, default=True)` |
| 13.2.19 | v2.4.0 | [x] | `main()` cover-art batch confirmation prompts (lines ~6410, ~6476 — "Continue? [Y/n]" for batch cover-art operations on multiple directories) shall call `prompt_handler.confirm(message, default=True)` |

##### 13.3 Progress & Display Abstraction

All embedded `print()` calls used for progress updates, status messages, and summary display during operations shall be routed through a `DisplayHandler` protocol. Business logic classes shall accept an optional `DisplayHandler` at construction. Summary rendering is the responsibility of the interface layer, not the business logic.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.3.1 | v2.4.0 | [x] | A `DisplayHandler` protocol shall define the following methods for progress and status reporting during operations |
| 13.3.2 | v2.4.0 | [x] | `show_progress(current: int, total: int, message: str) -> None` — replaces inline `print()` calls that report file-by-file progress during batch operations (e.g., "Converting file 3/50..."). CLI implements this with tqdm or line printing; Web implements with progress events |
| 13.3.3 | v2.4.0 | [x] | `show_status(message: str, level: str) -> None` — replaces inline `print()` calls that report status messages (e.g., "Found 50 MP3 files", "Skipping existing file"). `level` is one of: `"info"`, `"success"`, `"warning"`, `"error"`. CLI implements with colored console output; Web implements with log events |
| 13.3.4 | v2.4.0 | [x] | `show_banner(title: str, subtitle: str | None) -> None` — replaces the startup banner print block. CLI renders to console; Web may ignore or log it |
| 13.3.5 | v2.4.0 | [x] | The existing `Logger` class shall continue to handle file logging independently of `DisplayHandler`. `Logger.info()`, `Logger.error()`, etc. always write to the log file. `DisplayHandler.show_status()` is for user-facing display, not log file writing |
| 13.3.6 | v2.4.0 | [x] | When no `DisplayHandler` is provided (or `None`), business logic classes shall use a `NullDisplayHandler` that silently discards all display calls. Operations still log to the `Logger` log file |

###### 13.3.7 Summary Display Removal from Business Logic

The following `_print_*_summary()` methods shall be removed from their respective business logic classes. Each caller shall receive the result object (per 13.1) and render the summary itself using the format appropriate to its interface.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.3.7 | v2.4.0 | [x] | `TaggerManager._print_update_summary()` shall be removed. The CLI shall render the tag update summary from the returned `TagUpdateResult`. Format: 60-char-wide box with sections: header ("TAG UPDATE SUMMARY"), run metadata (date, directory, duration), FILES (processed/updated/skipped/errors), TAG UPDATES (title/album/artist/total), ORIGINAL TAG PROTECTION (stored counts), status line (checkmark or X emoji) |
| 13.3.8 | v2.4.0 | [x] | `TaggerManager._print_restore_summary()` shall be removed. The CLI shall render the tag restore summary from the returned `TagRestoreResult`. Format: 60-char-wide box with sections: header ("TAG RESTORATION SUMMARY"), run metadata, FILES (processed/restored/skipped/errors), TAG RESTORATIONS (title/artist/album/total), status line |
| 13.3.9 | v2.4.0 | [x] | `Converter._print_summary()` shall be removed. The CLI shall render the conversion summary from the returned `ConversionResult`. Format: 60-char-wide box with sections: header ("CONVERSION SUMMARY"), run metadata (date, input dir, output dir, duration, workers if >1), QUALITY SETTINGS (preset, mode description), FILES (found/converted/overwritten/skipped/errors), TAGGING (source tags copied), status line (checkmark, warning, or info emoji) |
| 13.3.10 | v2.4.0 | [x] | `USBManager._print_usb_summary()` shall be removed. The CLI shall render the USB sync summary from the returned `USBSyncResult`. Format: 60-char-wide box with sections: header ("USB SYNC SUMMARY"), run metadata (date, source, destination, duration), FILES (found/copied/skipped/failed), status line |
| 13.3.11 | v2.4.0 | [x] | `SummaryManager._print_summary()`, `_print_quick_summary()`, and `_print_detailed_summary()` shall be removed. The CLI shall render from the returned `LibrarySummaryResult`. Default format: 60-char-wide double-border box with sections: header ("PLAYLIST SUMMARY"), metadata (directory, scan date, duration), AGGREGATE STATISTICS (playlists/files/size/avg), TAG INTEGRITY (protection percentage, status), COVER ART (counts, percentages, status), PLAYLIST BREAKDOWN (table of playlists), final status. Quick format: header + directory + playlists/files/size/duration only. Detailed format: default + per-playlist extended breakdowns |
| 13.3.12 | v2.4.0 | [x] | `PipelineOrchestrator._print_pipeline_summary()` shall be removed. The CLI shall render from the returned `PipelineResult`. Format: 70-char-wide box with sections: header ("PIPELINE SUMMARY"), run metadata (date, playlist name/key, duration), per-stage sections (DOWNLOAD/CONVERSION/TAGGING/USB SYNC with stats and status emoji), COMPREHENSIVE FILES SUMMARY (cross-stage totals), overall status line with failed stages list |
| 13.3.13 | v2.4.0 | [x] | `PipelineOrchestrator.print_aggregate_summary()` shall be removed. The CLI shall render from the returned `AggregateResult`. Format: 70-char-wide box with sections: header ("TOTAL SUMMARY - ALL PLAYLISTS"), overview (playlists processed, duration, overall status), PLAYLIST RESULTS (table: Playlist / Downloaded / Converted / Tagged / Status), TOTALS row, CUMULATIVE STATISTICS (downloads/conversions/tags breakdowns), STATUS with failed playlist list |
| 13.3.14 | v2.4.0 | [x] | `DependencyChecker` display methods (`display_summary()`, `_show_package_install_help()`, `_show_ffmpeg_install_help()`, `_show_venv_help()`) shall be removed from the class. Dependency status shall be returned as a `DependencyCheckResult` containing: `venv_active: bool`, `venv_path: str | None`, `packages: dict[str, bool]`, `ffmpeg_available: bool`, `all_ok: bool`, `missing_packages: list[str]`. The CLI renders install help messages |
| 13.3.15 | v2.4.0 | [x] | `CoverArtManager` inline print blocks in `embed()`, `extract()`, `update()`, `strip()` shall be removed. Each method returns a `CoverArtResult` (per 13.1.13). The CLI renders the cover art operation summary |

##### 13.4 Interface Contracts

Three interface layers shall implement the `UserPromptHandler` and render results from the service layer. Each interface is responsible for its own I/O and presentation. The business logic classes are shared unchanged across all three.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.4.1 | v2.4.0 | [x] | **CLI interface** shall implement `UserPromptHandler` using standard `input()` calls with `[Y/n]` / `[y/N]` formatting. It shall render all result objects as formatted console boxes (60 or 70 char wide) matching the current visual output exactly. It shall use `tqdm` for progress bars and ANSI colors for status levels |
| 13.4.2 | v2.4.0 | [x] | **Interactive CLI interface** (`InteractiveMenu` class) shall implement `UserPromptHandler` for its menu-driven workflow. It shall render results using the same console box formats as the CLI. The menu loop, playlist selection, action dispatch, and post-operation pauses remain in `InteractiveMenu` — these are interface concerns, not business logic |
| 13.4.3 | v2.4.0 | [x] | **Web interface** shall implement `UserPromptHandler` by translating prompts to HTTP request/response cycles or WebSocket messages. Confirmation prompts become modal dialogs. Selection prompts become dropdown/radio UI. Text input prompts become form fields. Progress becomes server-sent events or WebSocket messages. Summaries become JSON responses rendered by the frontend |
| 13.4.4 | v2.4.0 | [x] | The `InteractiveMenu` class shall remain as a CLI-specific interface component. It shall not contain business logic — only menu display, user input collection, and delegation to service layer methods. All business operations invoked by the menu shall go through the same service layer methods used by the CLI and Web interfaces |
| 13.4.5 | v2.4.0 | [x] | The CLI argument parser (`argparse` setup in `main()`) shall remain a CLI-specific concern. The Web interface has its own routing and request parsing. Neither interface's request parsing shall live inside business logic classes |
| 13.4.6 | v2.4.0 | [x] | All three interfaces shall import and use the same business logic classes with the same method signatures. Interface-specific behavior is controlled by which `UserPromptHandler` and `DisplayHandler` implementations are injected, not by flags or conditionals inside the business logic |
| 13.4.7 | v2.4.0 | [x] | A `CLIPromptHandler` class shall implement `UserPromptHandler` using `input()` with formatted prompts. `confirm()` formats as `"message [Y/n] "` or `"message [y/N] "` based on default. `confirm_destructive()` formats as `"Type 'yes' to continue, anything else to cancel: "`. `select_from_list()` prints numbered options and reads an integer. `get_text_input()` prints prompt and reads a line. `wait_for_continue()` prints message and calls `input()` |
| 13.4.8 | v2.4.0 | [x] | A `CLIDisplayHandler` class shall implement `DisplayHandler` using `print()` to stdout. `show_progress()` updates a `tqdm` progress bar or prints a line. `show_status()` prints with optional ANSI color based on level. `show_banner()` prints the startup banner |
| 13.4.9 | v2.4.0 | [x] | A `CLISummaryRenderer` module (or set of functions) shall contain all summary formatting logic extracted from the removed `_print_*_summary()` methods. Each function takes a result object and prints the formatted console box. Functions: `render_tag_update_summary(result)`, `render_tag_restore_summary(result)`, `render_conversion_summary(result)`, `render_usb_sync_summary(result)`, `render_library_summary(result, mode)`, `render_pipeline_summary(result)`, `render_aggregate_summary(result)`, `render_dependency_check(result)`, `render_cover_art_summary(result)` |
| 13.4.10 | v2.4.0 | [x] | The Web interface shall return result objects as JSON. Each result dataclass shall support serialization to a dict via a `to_dict()` method or Python's `dataclasses.asdict()`. The Web frontend renders summaries from the JSON data |

##### 13.5 Logger Behavior

The `Logger` class bridges both file logging and optional console echo. Its behavior must be clearly defined in the separated architecture.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.5.1 | v2.4.0 | [x] | `Logger` shall always write to the timestamped log file regardless of interface type (CLI, Interactive, Web) |
| 13.5.2 | v2.4.0 | [x] | `Logger` shall accept an optional `echo_to_console: bool` parameter (default `True` for CLI, `False` for Web). When `True`, log messages are also printed to stdout. When `False`, log messages only go to the file |
| 13.5.3 | v2.4.0 | [x] | `Logger` shall remain independent of `DisplayHandler`. Logger handles structured log messages; `DisplayHandler` handles user-facing display. A single operation may both log (to file) and display (to user) — these are separate concerns |
| 13.5.4 | v2.4.0 | [x] | Business logic classes shall use `Logger` for operational logging (e.g., "Processing file X", "Error reading tags") and `DisplayHandler` for user-facing status (e.g., progress bars, summary headers). The distinction: Logger records what happened; DisplayHandler shows the user what's happening |

##### 13.6 ProgressBar Integration

The existing `ProgressBar` class (tqdm wrapper) is a CLI-specific concern that must be abstracted.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.6.1 | v2.4.0 | [x] | The `ProgressBar` class shall remain as a CLI-specific implementation, not used directly by business logic classes |
| 13.6.2 | v2.4.0 | [x] | Business logic classes that currently create `ProgressBar` instances directly shall instead call `display_handler.show_progress(current, total, message)` at each iteration |
| 13.6.3 | v2.4.0 | [x] | The `CLIDisplayHandler` shall internally manage `ProgressBar` / tqdm instances, creating them on first `show_progress()` call for a given operation and closing them when the operation completes |
| 13.6.4 | v2.4.0 | [x] | The Web `DisplayHandler` shall translate `show_progress()` calls into server-sent events or WebSocket messages containing `{current, total, message}` |

##### 13.7 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 13.7.1 | v2.4.0 | [x] | **Error propagation:** When a business logic method encounters an error, it shall set `success=False` on the result object and populate an `errors` count. It shall NOT raise exceptions for expected failure modes (file not found, conversion error, permission denied). Unexpected exceptions shall propagate naturally to the caller |
| 13.7.2 | v2.4.0 | [x] | **Timeout handling:** The `UserPromptHandler.wait_for_continue()` method shall accept an optional `timeout: float | None` parameter (seconds). If the timeout expires, the method returns as if the user acknowledged. Default: `None` (no timeout). Web interface should always set a reasonable timeout (e.g., 300 seconds) to prevent hung requests |
| 13.7.3 | v2.4.0 | [x] | **Cancellation:** Business logic operations that iterate over files shall check an optional `cancelled: threading.Event` flag between iterations. If set, the operation shall stop early, set `success=False`, and return partial results in the result object. This enables the Web interface to support cancel buttons |
| 13.7.4 | v2.4.0 | [x] | **Concurrent operations:** Business logic classes shall be stateless between method calls (statistics are reset at the start of each operation). This allows the Web interface to handle concurrent requests by creating separate instances per request. The `Logger` class shall be thread-safe for concurrent log writes |
| 13.7.5 | v2.4.0 | [x] | **Non-interactive fallback:** When `UserPromptHandler` is `None` and a business logic method needs user input, it shall use the `NonInteractivePromptHandler` defaults (per 13.2.7). This ensures operations never block waiting for input that cannot arrive (e.g., Web API with no WebSocket) |
| 13.7.6 | v2.4.0 | [x] | **Partial results on interruption:** If a batch operation (e.g., converting 50 files) is interrupted by error or cancellation after processing some files, the result object shall reflect the partial progress (e.g., `converted=23, errors=1, total_found=50`) rather than reporting zero |
| 13.7.7 | v2.4.0 | [x] | **Handler hot-swap prevention:** Once a business logic class is constructed with a `UserPromptHandler` and `DisplayHandler`, those handlers shall not be changed during an operation. Handlers are set at construction time and remain fixed for the lifetime of that instance |
| 13.7.8 | v2.4.0 | [x] | **Backward compatibility during migration:** While interfaces are being migrated incrementally, a `LegacyDisplayHandler` shall be available that reproduces the current `print()`-based behavior exactly, allowing classes to be migrated one at a time without changing visible output |

---

## Library & Configuration (continued)

---

### SRS 14: Summary Freshness Levels

**Version:** 1.0  |  **Date:** 2026-02-23  |  **Status:** Complete  |  **Implemented in:** v2.6.0

---

#### Purpose

Replace the binary today/not-today update check in the library summary playlist table with four graduated freshness levels, giving users clear visual indicators of which playlists need re-syncing.

#### Freshness Levels

| Level | Icon | Age Range | Meaning |
|-------|------|-----------|---------|
| Current | ✅ | Today (0 days) | Just updated |
| Recent | (none) | 1–7 days | Still fresh |
| Stale | ⚠️ | 8–30 days | Needs attention |
| Outdated | ❌ | 31+ days | Needs re-sync |

#### Requirements

##### 14.1 Freshness Classification

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.1.1 | v2.6.0 | [x] | A helper function classifies a `last_modified` datetime into one of four levels: Current (0 days), Recent (1–7 days), Stale (8–30 days), Outdated (31+ days) |
| 14.1.2 | v2.6.0 | [x] | The function returns both the icon string and the level name |
| 14.1.3 | v2.6.0 | [x] | Age is calculated as calendar days between `last_modified.date()` and `today` |

##### 14.2 Playlist Table Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.2.1 | v2.6.0 | [x] | The "Updated" column in `_render_playlist_table()` uses the freshness icon instead of the old binary ⚠️ check |
| 14.2.2 | v2.6.0 | [x] | Format: `{icon} {MMM DD}` (e.g., `✅ Feb 23`, `⚠️ Feb 10`, `❌ Jan 05`) |
| 14.2.3 | v2.6.0 | [x] | Recent level shows no icon — just the date (e.g., `Feb 20`) |
| 14.2.4 | v2.6.0 | [x] | Missing `last_modified` displays `❌ N/A` |

##### 14.3 Aggregate Freshness Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.3.1 | v2.6.0 | [x] | Default and detailed summary modes display a freshness breakdown line showing counts per level |
| 14.3.2 | v2.6.0 | [x] | Format: `Freshness: X current, X recent, X stale, X outdated` |
| 14.3.3 | v2.6.0 | [x] | Quick mode does not display freshness breakdown |

##### 14.4 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.4.1 | v2.6.0 | [x] | Playlists with no files (empty directory) show `❌ N/A` |
| 14.4.2 | v2.6.0 | [x] | The freshness thresholds are defined as named constants, not magic numbers |

---

### SRS 15: iOS Companion App

**Version:** 1.0  |  **Date:** 2026-02-23  |  **Status:** Complete  |  **Implemented in:** v2.9.0

---

#### Purpose

Provide a native iOS companion app that connects to the music-porter server over the local network, enabling mobile browsing of playlists, triggering server-side operations (pipeline, convert, tag, cover art), downloading MP3 files to the device, and exporting to USB drives — all authenticated via API key and discoverable via Bonjour/mDNS.

#### Requirements

##### 15.1 Server Command and Authentication

The `server` subcommand shall start the Flask web server with API key authentication, Bonjour advertisement, and CORS support for iOS clients.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.1.1 | v2.9.0 | [x] | `server` subcommand starts Flask on `0.0.0.0:5555` by default (network-accessible) |
| 15.1.2 | v2.9.0 | [x] | API key generated via `secrets.token_urlsafe(32)` and persisted in `config.yaml` under `settings.api_key` |
| 15.1.3 | v2.9.0 | [x] | Authentication middleware validates `Authorization: Bearer <key>` on all `/api/` routes; returns 401 if missing or invalid |
| 15.1.4 | v2.9.0 | [x] | CORS `after_request` handler sets `Access-Control-Allow-Origin: *`, permits `Authorization` header, and allows GET/POST/PUT/DELETE/OPTIONS methods |
| 15.1.5 | v2.9.0 | [x] | Auth middleware skips OPTIONS requests to allow CORS preflight |
| 15.1.6 | v2.9.0 | [x] | `--no-auth` flag disables authentication middleware (sets `app.config['NO_AUTH']`) |
| 15.1.7 | v2.9.0 | [x] | `--show-api-key` flag displays the full API key at startup |
| 15.1.8 | v2.9.0 | [x] | `--no-bonjour` flag disables Bonjour/mDNS service advertisement |
| 15.1.9 | v2.9.0 | [x] | `POST /api/auth/validate` validates Bearer token and returns server identity (name, version, platform) |
| 15.1.10 | v2.9.0 | [x] | `GET /api/server-info` returns server metadata (name, version, platform, available profiles) |
| 15.1.11 | v2.9.0 | [x] | Startup banner prints connection instructions: local IP, port, API key (masked unless `--show-api-key`), and QR code |

##### 15.2 Bonjour/mDNS Discovery

The `BonjourAdvertiser` class shall register the server as a discoverable service on the local network using zeroconf.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.2.1 | v2.9.0 | [x] | Service type registered as `_music-porter._tcp.local.` |
| 15.2.2 | v2.9.0 | [x] | Service name formatted as `"Music Porter on {safe_hostname}._music-porter._tcp.local."` |
| 15.2.3 | v2.9.0 | [x] | mDNS TXT record includes `version`, `platform`, and `api_version` properties |
| 15.2.4 | v2.9.0 | [x] | Local IP determined via UDP socket trick (`connect('10.255.255.255', 1)`) |
| 15.2.5 | v2.9.0 | [x] | Bonjour only starts when host is not `127.0.0.1` (network interfaces only) |
| 15.2.6 | v2.9.0 | [x] | Graceful degradation if `zeroconf` package is not installed (prints skip message) |
| 15.2.7 | v2.9.0 | [x] | Service unregistered on server shutdown (`stop()` called in `finally` block) |
| 15.2.8 | v2.9.0 | [x] | iOS `ServerDiscovery` class uses `NWBrowser` to browse for `_music-porter._tcp` services |
| 15.2.9 | v2.9.0 | [x] | Discovery auto-stops after 10 seconds to conserve battery |
| 15.2.10 | v2.9.0 | [x] | Resolved endpoints deduplicated (one connection per unique server) |

##### 15.3 File Serving Endpoints

The server shall provide REST endpoints for listing, downloading, and streaming files from the export directory.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.3.1 | v2.9.0 | [x] | `GET /api/files/<playlist_key>` returns JSON array of MP3 files with ID3 metadata (title, artist, album, duration, size, has\_cover\_art, has\_protection\_tags) |
| 15.3.2 | v2.9.0 | [x] | `GET /api/files/<playlist_key>/<filename>` serves the MP3 file with `audio/mpeg` MIME type |
| 15.3.3 | v2.9.0 | [x] | `GET /api/files/<playlist_key>/<filename>/artwork` extracts and serves the APIC frame image with correct MIME type |
| 15.3.4 | v2.9.0 | [x] | `GET /api/files/<playlist_key>/download-all` streams a ZIP archive of all MP3s (ZIP\_STORED, 64KB chunks) |
| 15.3.5 | v2.9.0 | [x] | All file endpoints validate paths via `_safe_dir()` to prevent directory traversal |
| 15.3.6 | v2.9.0 | [x] | File download validates `.mp3` extension and confirms resolved path stays within safe directory |
| 15.3.7 | v2.9.0 | [x] | File listing response includes `playlist`, `profile`, `file_count`, and `files` array |
| 15.3.8 | v2.9.0 | [x] | Artwork endpoint returns 404 if no APIC frame found in MP3 |

##### 15.4 QR Code Pairing

The server shall generate a terminal-displayable QR code containing connection credentials for iOS app pairing.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.4.1 | v2.9.0 | [x] | QR code generated using `segno` library with JSON payload: `{"host": "<ip>", "port": <port>, "key": "<api_key>"}` |
| 15.4.2 | v2.9.0 | [x] | QR rendered to terminal via `segno.terminal()` with compact mode |
| 15.4.3 | v2.9.0 | [x] | Each QR line indented with two spaces for consistent formatting |
| 15.4.4 | v2.9.0 | [x] | Graceful fallback if `segno` not installed (prints install hint) |
| 15.4.5 | v2.9.0 | [x] | QR code displayed as step 4 of the server startup connection guide |

##### 15.5 iOS App — Connection Flow

The iOS app shall discover servers via Bonjour, allow manual IP entry, validate API keys, and persist credentials for auto-reconnect.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.5.1 | v2.9.0 | [x] | `ServerDiscoveryView` shown as root view when not connected |
| 15.5.2 | v2.9.0 | [x] | Discovered servers listed with name, host, and port; tap to select |
| 15.5.3 | v2.9.0 | [x] | Manual connection section with server address field (URL keyboard) and port field (default 5555) |
| 15.5.4 | v2.9.0 | [x] | `PairingView` presented as sheet after server selection; accepts API key via `SecureField` |
| 15.5.5 | v2.9.0 | [x] | API key validated against server via `POST /api/auth/validate` |
| 15.5.6 | v2.9.0 | [x] | Validated API key stored in iOS Keychain via `KeychainService` (service ID: `com.musicporter.apikey`) |
| 15.5.7 | v2.9.0 | [x] | Server connection saved to `UserDefaults` as `savedServer` for auto-reconnect |
| 15.5.8 | v2.9.0 | [x] | Auto-reconnect attempted on app launch using saved server and Keychain API key (3-second timeout) |
| 15.5.9 | v2.9.0 | [x] | Failed auto-reconnect falls back to discovery screen silently |
| 15.5.10 | v2.9.0 | [x] | Refresh button in toolbar restarts Bonjour search |

##### 15.6 iOS App — Dashboard and Browsing

The iOS app shall display server status, library statistics, and allow browsing playlists and tracks with metadata.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.6.1 | v2.9.0 | [x] | Dashboard tab shows server card: version, active profile, cookie status badge (Valid/Invalid with green/red), expiration days, busy status badge (Idle/Busy with green/orange) |
| 15.6.2 | v2.9.0 | [x] | Dashboard shows library stats card: playlist count, file count, total size in MB |
| 15.6.3 | v2.9.0 | [x] | Dashboard lists all playlists with per-playlist file counts |
| 15.6.4 | v2.9.0 | [x] | Pull-to-refresh on dashboard reloads status and summary |
| 15.6.5 | v2.9.0 | [x] | Playlists tab lists all server playlists with name, key, and file count |
| 15.6.6 | v2.9.0 | [x] | Tapping a playlist navigates to `PlaylistDetailView` showing all tracks |
| 15.6.7 | v2.9.0 | [x] | `TrackRow` component shows artwork thumbnail (44x44, rounded), title, artist, and file size |
| 15.6.8 | v2.9.0 | [x] | Artwork loaded via `AsyncImage` from `/api/files/<key>/<filename>/artwork` endpoint |
| 15.6.9 | v2.9.0 | [x] | Add playlist via plus button in toolbar: form with key, URL, and display name fields |
| 15.6.10 | v2.9.0 | [x] | Delete playlist via swipe-to-delete gesture |

##### 15.7 iOS App — Operations and SSE

The iOS app shall trigger server-side operations and display real-time progress via Server-Sent Events.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.7.1 | v2.9.0 | [x] | Pipeline tab provides form with source selection (playlist picker, URL field, or auto-all toggle) |
| 15.7.2 | v2.9.0 | [x] | Pipeline options include quality preset picker (lossless, high, medium, low) and copy-to-USB toggle |
| 15.7.3 | v2.9.0 | [x] | Run Pipeline button triggers `POST /api/pipeline/run` and returns task ID |
| 15.7.4 | v2.9.0 | [x] | `SSEClient` (actor) subscribes to `GET /api/stream/<task_id>` and yields `AsyncStream<SSEEvent>` |
| 15.7.5 | v2.9.0 | [x] | SSE events parsed from `"data: {json}"` lines into typed `SSEEvent` enum: `.log`, `.progress`, `.heartbeat`, `.done` |
| 15.7.6 | v2.9.0 | [x] | `ProgressPanel` component shows progress bar with stage name and percentage during operations |
| 15.7.7 | v2.9.0 | [x] | `ProgressPanel` shows scrollable monospace log with color-coded levels: ERROR=red, WARN=orange, OK=green, SKIP=yellow |
| 15.7.8 | v2.9.0 | [x] | `OperationViewModel` manages operation lifecycle: `run()`, `handleEvent()`, `reset()` |
| 15.7.9 | v2.9.0 | [x] | Completion status shown as green checkmark (success) or red X with error message (failure) |
| 15.7.10 | v2.9.0 | [x] | Form inputs disabled while operation is running |

##### 15.8 iOS App — MusicKit Integration

The iOS app shall use MusicKit to browse the user's Apple Music library and send playlist URLs to the server for processing.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.8.1 | v2.9.0 | [x] | `MusicKitService` requests MusicKit authorization on user action (not at launch) |
| 15.8.2 | v2.9.0 | [x] | Authorization prompt shown only when user taps "Authorize Apple Music" button |
| 15.8.3 | v2.9.0 | [x] | `fetchLibraryPlaylists()` retrieves user's library playlists sorted by name |
| 15.8.4 | v2.9.0 | [x] | `searchPlaylists(query:)` searches Apple Music catalog with limit of 25 results |
| 15.8.5 | v2.9.0 | [x] | `AppleMusicBrowserView` lists playlists with name, description, and send-to-server button |
| 15.8.6 | v2.9.0 | [x] | Searchable modifier enables catalog search from the playlist list |
| 15.8.7 | v2.9.0 | [x] | Sending a playlist to server triggers pipeline via `POST /api/pipeline/run` with the playlist URL |
| 15.8.8 | v2.9.0 | [x] | MusicKit cannot export audio due to DRM; all downloads handled server-side |

##### 15.9 iOS App — File Downloads

The iOS app shall download MP3 files from the server to local device storage with progress tracking.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.9.1 | v2.9.0 | [x] | `FileDownloadManager` downloads individual MP3 files via `GET /api/files/<key>/<filename>` |
| 15.9.2 | v2.9.0 | [x] | `downloadAll(playlist:)` downloads entire playlist as ZIP via `GET /api/files/<key>/download-all` |
| 15.9.3 | v2.9.0 | [x] | Files stored in `~/Documents/MusicPorter/<playlist>/` on device |
| 15.9.4 | v2.9.0 | [x] | Per-file download state tracked: `.pending`, `.downloading(progress)`, `.completed(URL)`, `.failed(Error)` |
| 15.9.5 | v2.9.0 | [x] | `DownloadView` shows server playlists with file counts and local file counts (green indicator) |
| 15.9.6 | v2.9.0 | [x] | Local storage usage displayed in Downloads tab |
| 15.9.7 | v2.9.0 | [x] | `deletePlaylist(playlist:)` removes locally downloaded files for a playlist |
| 15.9.8 | v2.9.0 | [x] | Background `URLSession` used for resilient file downloads |

##### 15.10 iOS App — USB Export

The iOS app shall export downloaded MP3 files to USB drives or external storage via the system document picker.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.10.1 | v2.9.0 | [x] | `USBExportService` presents `UIDocumentPickerViewController` for folder selection |
| 15.10.2 | v2.9.0 | [x] | Supports FAT, ExFAT, HFS+, and APFS formatted drives |
| 15.10.3 | v2.9.0 | [x] | `USBSyncView` lists downloaded playlists with selectable checkmarks |
| 15.10.4 | v2.9.0 | [x] | Export button shows count of selected playlists |
| 15.10.5 | v2.9.0 | [x] | File copy progress tracked via `exportProgress` (0.0–1.0) |
| 15.10.6 | v2.9.0 | [x] | `ExportResult` reports success status, files copied count, and message |
| 15.10.7 | v2.9.0 | [x] | Security-scoped URLs used for accessing external storage (iOS sandbox compliance) |

##### 15.11 iOS App — Settings

The iOS app shall display server connection details, available profiles, and provide access to advanced operations.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.11.1 | v2.9.0 | [x] | Settings tab shows server host:port and server name |
| 15.11.2 | v2.9.0 | [x] | Disconnect button (red, destructive) clears server, API key, and Keychain data |
| 15.11.3 | v2.9.0 | [x] | Profiles section lists available output profiles with descriptions |
| 15.11.4 | v2.9.0 | [x] | Operations navigation link shows task history with status badges (completed=green, running=blue, failed=red, cancelled=orange) |
| 15.11.5 | v2.9.0 | [x] | Apple Music navigation link opens `AppleMusicBrowserView` |
| 15.11.6 | v2.9.0 | [x] | USB navigation link opens `USBSyncView` |
| 15.11.7 | v2.9.0 | [x] | About section shows app version |

##### 15.12 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 15.12.1 | v2.9.0 | [x] | IPv6 addresses: `ServerDiscovery` extracts mapped IPv4 from IPv6 (e.g., `::ffff:192.168.1.100` → `192.168.1.100`) |
| 15.12.2 | v2.9.0 | [x] | Scope IDs stripped from resolved addresses (e.g., `%bridge101`, `%en0` removed) |
| 15.12.3 | v2.9.0 | [x] | Network timeout: auto-reconnect uses 3-second timeout; failure falls back to discovery silently |
| 15.12.4 | v2.9.0 | [x] | Server busy (HTTP 409): `APIError.serverBusy` returned when attempting operation while another is running |
| 15.12.5 | v2.9.0 | [x] | Stale reconnect data: if saved server is unreachable, app falls back to discovery screen without error toast |
| 15.12.6 | v2.9.0 | [x] | Empty playlist directory: file listing returns empty `files` array with `file_count: 0` |
| 15.12.7 | v2.9.0 | [x] | Missing cover art: artwork endpoint returns 404; `TrackRow` shows music note placeholder |
| 15.12.8 | v2.9.0 | [x] | URL construction uses `URLComponents` to properly handle IPv6 addresses and special characters |
| 15.12.9 | v2.9.0 | [x] | All `@Observable` ViewModels annotated with `@MainActor` for thread-safe UI updates |
| 15.12.10 | v2.9.0 | [x] | Bonjour discovery deduplicates servers (one connection per unique host:port) |
