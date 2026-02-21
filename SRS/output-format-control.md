# SRS: Configurable Output Directory Structure & Filename Format

**Version:** 1.0
**Date:** 2026-02-19
**Status:** Complete

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
| `artist_title` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title_only` | `Title.mp3` | `Shake It Off.mp3` |

- [x] `artist_title` filename format works (existing behavior)
- [x] `title_only` filename format produces title-only filenames

### 3.3 Configuration

Settings shall follow the existing precedence chain:

**CLI flag > config.yaml setting > profile default**

#### 3.3.1 CLI Flags

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `artist_title`, `title_only` | Profile default |

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
| `ride-command` | `flat` | `artist_title` |
| `basic` | `flat` | `artist_title` |

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

## 4. Edge Cases

### 4.1 Filename Collisions

- [x] `title_only` format with duplicate titles: skip-if-exists behavior with warning suggesting `artist_title` format

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
- [x] Filename collisions with `title_only` format handled correctly
- [x] Web UI dropdowns submit correct API parameters
