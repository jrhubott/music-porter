# SRS: Configurable Output Directory Structure & Filename Format

**Version:** 1.0
**Date:** 2026-02-19
**Status:** Draft

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

- [ ] `flat` directory structure works (existing behavior)
- [ ] `nested-artist` directory structure creates artist subdirectories
- [ ] `nested-artist-album` directory structure creates artist/album subdirectories
- [ ] Artist and album directory names sanitized using existing `sanitize_filename()`
- [ ] Subdirectories created automatically during conversion
- [ ] Unknown artist defaults to `"Unknown Artist"` directory name
- [ ] Unknown album defaults to `"Unknown Album"` directory name

### 3.2 Filename Formats

The system shall support two filename format modes, configurable per output profile:

| Value | Pattern | Example |
|-------|---------|---------|
| `artist_title` | `Artist - Title.mp3` | `Taylor Swift - Shake It Off.mp3` |
| `title_only` | `Title.mp3` | `Shake It Off.mp3` |

- [ ] `artist_title` filename format works (existing behavior)
- [ ] `title_only` filename format produces title-only filenames

### 3.3 Configuration

Settings shall follow the existing precedence chain:

**CLI flag > config.yaml setting > profile default**

#### 3.3.1 CLI Flags

| Flag | Values | Default |
|------|--------|---------|
| `--dir-structure` | `flat`, `nested-artist`, `nested-artist-album` | Profile default |
| `--filename-format` | `artist_title`, `title_only` | Profile default |

- [ ] `--dir-structure` flag added to `pipeline` subcommand
- [ ] `--dir-structure` flag added to `convert` subcommand
- [ ] `--filename-format` flag added to `pipeline` subcommand
- [ ] `--filename-format` flag added to `convert` subcommand

#### 3.3.2 config.yaml Settings

```yaml
settings:
  dir_structure: flat              # optional
  filename_format: artist_title    # optional
```

- [ ] `dir_structure` setting read from config.yaml
- [ ] `filename_format` setting read from config.yaml
- [ ] Omitted settings fall back to profile default

#### 3.3.3 Profile Defaults

Both existing profiles shall retain their current defaults:

| Profile | directory_structure | filename_format |
|---------|-------------------|-----------------|
| `ride-command` | `flat` | `artist_title` |
| `basic` | `flat` | `artist_title` |

- [ ] `ride-command` profile defaults unchanged
- [ ] `basic` profile defaults unchanged

### 3.4 Backward Compatibility

- [ ] Default behavior identical to current behavior (zero regression)
- [ ] `summary` command works with nested export directories
- [ ] `cover-art` commands work with nested export directories
- [ ] `sync-usb` preserves nested directory structure on target drive
- [ ] `tag` command works with nested export directories
- [ ] `restore` command works with nested export directories

### 3.5 Feature Parity (CLI & Web)

**CLI:**
- [ ] `--dir-structure` flag on `pipeline` command
- [ ] `--dir-structure` flag on `convert` command
- [ ] `--filename-format` flag on `pipeline` command
- [ ] `--filename-format` flag on `convert` command

**Web Dashboard:**
- [ ] Convert page: Directory Layout dropdown
- [ ] Convert page: Filename Format dropdown
- [ ] Pipeline page: Directory Layout dropdown
- [ ] Pipeline page: Filename Format dropdown
- [ ] Settings page: Profile comparison table includes directory structure
- [ ] Settings page: Profile comparison table includes filename format
- [ ] `/api/pipeline/run` accepts `dir_structure` parameter
- [ ] `/api/pipeline/run` accepts `filename_format` parameter
- [ ] `/api/convert/run` accepts `dir_structure` parameter
- [ ] `/api/convert/run` accepts `filename_format` parameter

### 3.6 Display

- [ ] Startup banner displays active directory structure
- [ ] Startup banner displays active filename format
- [ ] Log files record active directory structure and filename format
- [ ] `--dry-run` output shows full output path (including subdirectories for nested structures)

## 4. Edge Cases

### 4.1 Filename Collisions

- [ ] `title_only` format with duplicate titles: skip-if-exists behavior with warning suggesting `artist_title` format

### 4.2 Special Characters in Directory Names

- [ ] Artist/album directory names sanitized by `sanitize_filename()` (strips `/\:*?"<>|`)

### 4.3 Deeply Nested Paths

Very long artist + album + title combinations could exceed filesystem path length limits (255 chars on macOS/Linux). This is an existing limitation and is not addressed by this feature.

## 5. Validation

- [ ] Invalid `--dir-structure` value produces clear error with valid choices and non-zero exit
- [ ] Invalid `--filename-format` value produces clear error with valid choices and non-zero exit
- [ ] Invalid config.yaml values validated and rejected with clear error

## 6. Testing

- [ ] All 6 combinations (3 structures x 2 formats) tested with `--dry-run --verbose`
- [ ] Default behavior unchanged (flat + artist_title)
- [ ] CLI flag overrides config.yaml
- [ ] config.yaml overrides profile default
- [ ] `summary` command works with nested export directories
- [ ] `cover-art embed` correctly matches files with non-default formats
- [ ] `sync-usb` preserves nested structure on target drive
- [ ] Filename collisions with `title_only` format handled correctly
- [ ] Web UI dropdowns submit correct API parameters
