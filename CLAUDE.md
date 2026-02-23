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

### SRS Document Format

- Tables with columns: ID, Version, Tested, Requirement
- New requirements start with `[ ]` in the Tested column — mark `[x]` when implemented and tested
- **IDs must be globally unique** across all SRS documents in `SRS/SRS.md` — use the entry's sequential number as the first digit (e.g., entry 8 uses IDs `8.1.1`, `8.2.1`, etc.)
- When creating a new SRS, check `SRS/SRS.md` for the highest entry number and use the next one
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
- **Archive on merge:** completed SRS merged into `SRS/SRS.md` under the appropriate existing section. If no existing section fits, ask the user before creating one. Delete the individual SRS file from `SRS/` after archiving.

## Project Overview

RideCommandMP3Export is a music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format, and optionally copies them to USB drives. The system preserves original tag metadata while allowing customization for device compatibility.

## Architecture

### Core Workflow Pipeline

The system follows an integrated pipeline:

1. **Download** → Downloads Apple Music playlists as M4A files via gamdl
2. **Convert** → Converts M4A to MP3 using ffmpeg (libmp3lame, default: lossless 320kbps CBR)
3. **Tag** → Updates and preserves tags with TXXX frame protection
4. **Sync** → Optionally copies to USB drives

### Key Scripts

**music-porter** (python) - **RECOMMENDED**
- Unified tool combining all functionality in a single command
- Professional subcommand architecture: `pipeline`, `download`, `convert`, `tag`, `restore`, `reset`, `sync-usb`, `cover-art`, `summary`
- Interactive menu for easy operation
- Comprehensive error handling and statistics
- Full pipeline orchestration (download → convert → tag → USB)
- Modular design with 21 classes
- 4,270 lines of production-ready Python code
- See `MUSIC-PORTER-GUIDE.md` for complete documentation

**do-it-all** (bash) - **DEPRECATED**
- Legacy orchestration script (now a compatibility wrapper)
- Calls `music-porter` internally
- Will be removed in a future version
- Migrate to: `./music-porter`

**ride-command-mp3-export** (python) - **DEPRECATED**
- Legacy conversion and tag management tool (now a compatibility wrapper)
- Calls `music-porter` internally
- Will be removed in a future version
- Migrate to: `./music-porter`

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

The conversion system supports configurable quality presets to balance file size and audio quality:

| Preset | Mode | Value | Est. Bitrate | Use Case |
|--------|------|-------|--------------|----------|
| `lossless` | CBR | 320kbps | 320kbps | **Default** - Maximum quality, no compromises |
| `high` | VBR | 2 | ~190-250kbps | High quality, smaller files than lossless |
| `medium` | VBR | 4 | ~165-210kbps | Balanced quality and file size |
| `low` | VBR | 6 | ~115-150kbps | Space-constrained devices |
| `custom` | VBR | 0-9 | Variable | Advanced users (0=best quality, 9=worst) |

**Usage:**

- All `convert` and `pipeline` commands support `--preset` flag
- Default is `lossless` (320kbps CBR) for maximum quality
- VBR (Variable Bit Rate) adjusts bitrate dynamically based on audio complexity
- Custom quality requires both `--preset custom` and `--quality 0-9` flags

### Full Pipeline Workflows

```bash
# Process a specific playlist (download → convert → tag)
./music-porter pipeline --playlist "Pop_Workout"
./music-porter pipeline --playlist 1

# Process from direct URL
./music-porter pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (auto mode, no prompts)
./music-porter pipeline --auto

# With quality presets (lossless, high, medium, low, custom)
./music-porter pipeline --playlist "Pop_Workout" --preset high
./music-porter pipeline --auto --preset medium

# Include USB copy after processing
./music-porter pipeline --playlist "Pop_Workout" --copy-to-usb

# Custom USB directory
./music-porter pipeline --playlist "Pop_Workout" --copy-to-usb --usb-dir "RZR/Music"
```

### Granular Control (Individual Commands)

**Download:**

```bash
# Download specific playlist
./music-porter download --playlist "Pop_Workout"

# Download from URL
./music-porter download --url "https://music.apple.com/..."

# Custom output directory
./music-porter download --playlist "Pop_Workout" --output custom/path
```

**Convert:**

```bash
# Convert M4A files to MP3 (default: lossless 320kbps)
./music-porter convert music/Pop_Workout

# Specify output directory (profile-scoped by default)
./music-porter convert music/Pop_Workout --output export/ride-command/Pop_Workout

# Use quality presets (lossless, high, medium, low)
./music-porter convert music/Pop_Workout --preset high
./music-porter convert music/Pop_Workout --preset medium

# Custom VBR quality (0=best, 9=worst)
./music-porter convert music/Pop_Workout --preset custom --quality 0

# Force re-conversion of existing files
./music-porter convert music/Pop_Workout --force
```

**Tag Operations:**

```bash
# Update album tag
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout"

# Update album and artist
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout" --artist "Various"
```

**Restore Original Tags:**

```bash
# Restore all original tags
./music-porter restore export/ride-command/Pop_Workout --all

# Restore specific tags
./music-porter restore export/ride-command/Pop_Workout --album
./music-porter restore export/ride-command/Pop_Workout --title
./music-porter restore export/ride-command/Pop_Workout --artist
```

**Reset Tags from Source (⚠️ Overwrites Protection):**

```bash
# Reset all protection tags from source M4A files
./music-porter reset music/Pop_Workout export/ride-command/Pop_Workout
# Requires confirmation prompt
```

**USB Operations:**

```bash
# Copy to USB drive
./music-porter sync-usb export/ride-command/Pop_Workout

# Copy entire export directory
./music-porter sync-usb

# Custom USB directory
./music-porter sync-usb export/ride-command/Pop_Workout --usb-dir "RZR/Music"
```

**Library Summary:**

```bash
# Display export library statistics (default mode)
# Always checks all files for tag integrity
./music-porter summary

# Quick mode (aggregate statistics only)
./music-porter summary --quick

# Detailed mode (extended per-playlist information)
./music-porter summary --detailed

# Analyze custom directory
./music-porter summary --export-dir /path/to/export
```

**Cover Art Management:**

```bash
# Embed cover art from M4A sources into existing MP3s
./music-porter cover-art embed export/ride-command/Pop_Workout

# Embed with explicit source directory
./music-porter cover-art embed export/ride-command/Pop_Workout --source music/Pop_Workout

# Extract cover art to image files
./music-porter cover-art extract export/ride-command/Pop_Workout

# Replace cover art from a single image
./music-porter cover-art update export/ride-command/Pop_Workout --image artwork.jpg

# Strip cover art to reduce file size
./music-porter cover-art strip export/ride-command/Pop_Workout

# Convert without cover art
./music-porter convert music/Pop_Workout --no-cover-art
```

### Global Flags (Apply to All Commands)

```bash
# Preview changes without modifying files
./music-porter --dry-run convert music/Pop_Workout

# Verbose output for detailed information
./music-porter --verbose tag export/ride-command/Pop_Workout --album "Test"

# Combine flags
./music-porter --dry-run --verbose convert music/Pop_Workout

# Show version
./music-porter --version
```

### Output Type Profiles

Profiles control conversion behavior, tag handling, artwork, and quality defaults. Use `--output-type` to select.

| Profile | ID3 | Artwork | Quality | Album Tag | Artist Tag | Description |
|---------|-----|---------|---------|-----------|------------|-------------|
| `ride-command` | v2.3 | 100px | lossless | playlist name | "Various" | Polaris Ride Command (default) |
| `basic` | v2.4 | original | lossless | original | original | Standard MP3, original tags & art |

**Profile fields:**

- `artwork_size`: `>0` = resize to max px, `0` = embed original, `-1` = strip artwork
- `quality_preset`: Default conversion quality (`lossless`, `high`, `medium`, `low`)
- `pipeline_album`: `"playlist_name"` or `"original"` — controls album tag in pipeline
- `pipeline_artist`: `"various"` or `"original"` — controls artist tag in pipeline

**Precedence:** CLI flags override profile defaults (`--no-cover-art` > `artwork_size`, `--preset` > `quality_preset`).

### Legacy Commands (Deprecated)

⚠️ **The following commands still work but are deprecated:**

```bash
# Old commands (show deprecation warnings, call new tool internally)
./do-it-all                                    # Use: ./music-porter
./ride-command-mp3-export music/Pop_Workout/   # Use: ./music-porter convert music/Pop_Workout
```

**Migration:** Replace all `do-it-all` and `ride-command-mp3-export` calls with `music-porter`. See `MUSIC-PORTER-GUIDE.md` for detailed migration instructions.

## Development Setup

### Platform Support

The tool supports **macOS**, **Linux**, and **Windows**. Platform is auto-detected at startup.

| Platform | USB Detection | Eject Method | FFmpeg Install |
|----------|--------------|--------------|----------------|
| macOS | `/Volumes/` | `diskutil eject` | `brew install ffmpeg` |
| Linux | `/media/$USER/`, `/mnt/` | `udisksctl`, `umount` | `apt-get`, `dnf`, `pacman` |
| Windows | Drive letters (C:, D:, etc.) | Manual (Explorer) | Chocolatey or direct download |

### Prerequisites

- Python 3.8+ (uses Python virtual environment)
- ffmpeg (for audio conversion, system binary required)
  - **macOS:** `brew install ffmpeg`
  - **Linux:** `sudo apt-get install ffmpeg` (Ubuntu/Debian), `sudo dnf install ffmpeg` (Fedora/RHEL), `sudo pacman -S ffmpeg` (Arch)
  - **Windows:** `choco install ffmpeg` or download from <https://ffmpeg.org/download.html>
- gamdl (Apple Music downloader, installed via pip in venv)
- mutagen (Python ID3 tag library, installed via pip in venv)
- ffmpeg-python (Python wrapper for FFmpeg, installed via pip in venv)
- selenium (Browser automation for cookie extraction, installed via pip in venv)
- webdriver-manager (Automatic browser driver management, installed via pip in venv)
- Pillow (Image processing for cover art resizing, installed via pip in venv)
- PyYAML (YAML configuration file parsing, installed via pip in venv)

### Initial Setup

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure playlists
# Edit config.yaml (auto-created on first run with defaults)
```

### Testing Changes

- Use `--dry-run` flag extensively to preview behavior
- Use `--verbose` to inspect tag transformations
- Test tag preservation by running updates multiple times
- Verify TXXX frames with: `./music-porter --verbose tag export/ride-command/PlaylistName`

### Linting

The project uses **Ruff** (Python) and **PyMarkdown** (Markdown) for linting. All config lives in `pyproject.toml`.

```bash
# Install dev dependencies (once)
pip install -r requirements-dev.txt

# Python linting
ruff check .                # Check for issues
ruff check --fix .          # Auto-fix safe issues

# Markdown linting
pymarkdown scan -r .        # Check for issues
pymarkdown fix -r .         # Auto-fix safe issues
```

Both linters should pass clean before merging to main.

### Feature Branch Workflow

**When to use feature branches vs direct commits:**

| Use Feature Branch | Commit Directly to Main |
|---|---|
| New features | Single-commit bug fixes |
| Multi-commit changes | Documentation-only updates |
| Refactoring | Config changes (config.yaml) |
| Experimental or risky changes | Typo corrections |

**Branch naming conventions:**

| Prefix | Use Case | Example |
|--------|----------|---------|
| `feature/` | New features | `feature/playlist-search` |
| `bugfix/` | Bug fixes | `bugfix/tag-double-prefix` |
| `refactor/` | Refactoring | `refactor/converter-class` |
| `docs/` | Documentation | `docs/cookie-guide` |

- Lowercase with hyphens (no underscores or slashes in the description)
- Keep descriptions to 2-4 words

**Creating a feature branch:**

```bash
# 1. Start from up-to-date main
git checkout main
git pull origin main

# 2. Create and switch to feature branch
git checkout -b feature/my-feature

# 3. Set branch version in music-porter (line 68)
VERSION = "1.5.3-my-feature"

# 4. Commit the version change as first commit
git add music-porter
git commit -m "Start my-feature branch"
```

**Working on the branch:**

- Commit regularly with descriptive messages
- Keep the branch version (e.g. `1.5.3-my-feature`) throughout development
- Don't bump the base version number during dev — that happens at merge time
- For long-lived branches, periodically sync with main:
  
  ```bash
  # Option A: Rebase (cleaner history, preferred for solo branches)
  git fetch origin
  git rebase origin/main

  # Option B: Merge (safer for shared branches)
  git fetch origin
  git merge origin/main
  ```

**Pre-merge checklist:**

- [ ] Working tree is clean (`git status` shows nothing)
- [ ] All changes tested with `--dry-run` and `--verbose`
- [ ] No temporary or debug code left in
- [ ] Commit history is clean and descriptive
- [ ] Branch is up to date with main
- [ ] README future features updated if applicable (strikethrough implemented items)
- [ ] All SRS requirements marked `[x]` (if SRS exists for this branch)

**Merging to main:**
Use the `/merge-to-main` skill, which automates version bump, README updates, tagging, and branch cleanup. See the Version Management section below for version numbering details.

### Version Management

**IMPORTANT: Version number strategy depends on branch context.**

The version number is defined in `music-porter` at line 68:

```python
VERSION = "1.1.0"
```

**Branch-Based Version Workflow:**

**While working on a feature branch:**

- Include branch name in version: `VERSION = "1.1.0-feature-name"`
- Format: `MAJOR.MINOR.PATCH-branch-name`
- Use lowercase with hyphens (no underscores or slashes)
- Examples:
  - `VERSION = "1.1.0-cookie-management"`
  - `VERSION = "1.2.0-usb-sync-improvements"`
  - `VERSION = "1.1.1-bugfix-tag-restoration"`

**When merging to main:**

- Update to clean release version (remove branch name)
- Increment version number according to semantic versioning
- **Create a git tag** for the new version: `git tag v1.2.0`
- Examples:
  - `1.1.0-cookie-management` → `1.2.0` (new feature)
  - `1.1.1-bugfix-tag-restoration` → `1.1.1` (bug fix)
  - `2.0.0-breaking-cli-refactor` → `2.0.0` (breaking change)

**When committing directly to main:**

- **ALWAYS ask the user if the version should be bumped** before committing
- Present the current version and suggest appropriate bump level based on changes
- Examples of prompts:
  - "Current version is 1.2.1. Should I bump to 1.2.2 for this bug fix? [Y/n]"
  - "Current version is 1.2.0. Should I bump to 1.3.0 for this new feature? [Y/n]"
  - "Current version is 1.2.0. This is just documentation. Skip version bump? [Y/n]"
- After user confirms, update VERSION, commit, and **create a git tag** for the new version
- Never assume - always ask!

**Semantic Versioning (MAJOR.MINOR.PATCH):**

- **PATCH** (1.1.0 → 1.1.1): Bug fixes, documentation updates, minor improvements
- **MINOR** (1.1.0 → 1.2.0): New features, non-breaking changes
- **MAJOR** (1.1.0 → 2.0.0): Breaking changes, major refactors

**Complete Workflow Example:**

```bash
# Create feature branch
git checkout -b feature/cookie-management

# Update version to include branch name
# In music-porter line 68:
VERSION = "1.1.0-cookie-management"
git commit -m "Start cookie management feature"

# Work on feature... make commits...
# (version stays "1.1.0-cookie-management" throughout development)

# Ready to merge to main
git checkout main
git merge feature/cookie-management

# Update version to clean release number
# In music-porter line 68:
VERSION = "1.2.0"  # MINOR bump for new feature
git commit -m "Bump version to 1.2.0 for cookie management feature"

# Tag the release
git tag v1.2.0
```

**Benefits:**

- Branch versions clearly identify development builds
- Clean versions on main identify stable releases
- Easy to see if running development vs release build
- Version in startup banner shows branch: `v1.2.0-new-feature`

**Version Display:**

- Shown in startup banner: `Apple Music to Ride Command MP3 Converter v1.1.0`
- With branch: `Apple Music to Ride Command MP3 Converter v1.2.0-new-feature`
- Shown with `--version` flag
- Logged to all log files

### Common Gotchas

**Apple Music Authentication & Cookie Management:**

- Requires `cookies.txt` file with Apple Music session cookies
- Tool automatically validates cookies at startup and before downloads
- Expired cookies trigger interactive prompt: "Attempt automatic cookie refresh? [Y/n]"
- Automatic refresh uses selenium to extract cookies from browser (Chrome, Firefox, Safari, Edge)
- Selenium is installed via requirements.txt
- Backup created before overwriting: `cookies.txt.backup`
- Cookie validation checks `media-user-token` for `.music.apple.com` domain
- Expiration shown in days: "Cookies valid until 2026-08-16 (178 days remaining)"
- Use `--auto-refresh-cookies` flag for non-interactive refresh
- Use `--skip-cookie-validation` to bypass checks (not recommended)
- Manual refresh via browser extension still supported as fallback
- See `COOKIE-MANAGEMENT-GUIDE.md` for complete documentation

**Virtual Environment:**

- Must activate venv before running
  - **macOS/Linux:** `source .venv/bin/activate`
  - **Windows:** `.venv\Scripts\activate`
- Dependencies (gamdl, mutagen) only available inside venv
- Deactivate with `deactivate` command

**Temporary Directories:**

- gamdl creates `gamdl_temp_*` directories during downloads
- Safe to delete after successful downloads
- Not tracked in git (.gitignore)

**USB Drive Detection:**

- Tool auto-detects mounted volumes based on platform:
  - **macOS:** `/Volumes/` (excludes "Macintosh HD", "Macintosh HD - Data")
  - **Linux:** `/media/$USER/` and `/mnt/` (excludes "boot", "root")
  - **Windows:** Drive letters A:-Z: (excludes C:)
- If USB not detected, check mount status:
  - **macOS:** `ls /Volumes/`
  - **Linux:** `ls /media/$USER/` or `ls /mnt/`
  - **Windows:** Check File Explorer for removable drives

**USB Ejection:**

- **macOS:** Automatic via `diskutil eject`
- **Linux:** Automatic via `udisksctl` or `umount`
- **Windows:** Manual via Windows Explorer (automatic eject not implemented)

## Directory Structure

```text
.
├── music-porter            # ⭐ Unified tool (RECOMMENDED)
├── do-it-all                        # Legacy wrapper (deprecated)
├── ride-command-mp3-export          # Legacy wrapper (deprecated)
├── do-it-all.backup                 # Original bash script (backup)
├── ride-command-mp3-export.backup   # Original Python script (backup)
├── config.yaml                      # Configuration file (playlists + settings)
├── cookies.txt                      # Apple Music authentication cookies
├── cookies.txt.backup               # Automatic backup before refresh
├── music/                           # Downloaded M4A files (organized by playlist)
│   └── Pop_Workout/                 # Nested: Artist/Album/Track.m4a
├── export/                          # Converted MP3 files (profile-scoped, flat per playlist)
│   ├── ride-command/                # Profile: ride-command
│   │   └── Pop_Workout/            # Flat: "Artist - Title.mp3"
│   └── basic/                       # Profile: basic
│       └── Pop_Workout/            # Flat: "Artist - Title.mp3"
├── logs/                            # Execution logs (timestamped)
├── .venv/                           # Python virtual environment
├── requirements.txt                 # All Python dependencies
├── MUSIC-PORTER-GUIDE.md   # Complete usage guide
├── COOKIE-MANAGEMENT-GUIDE.md       # Cookie validation and refresh guide
├── QUICK-REFERENCE.md               # Command cheat sheet
└── IMPLEMENTATION-SUMMARY.md        # Technical documentation
```

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

- **Validation:** Uses `http.cookiejar.MozillaCookieJar` to parse Netscape format cookies
- **Browser Detection:** Detects OS default browser via LaunchServices (macOS), xdg-settings (Linux), registry (Windows)
- **Multi-Browser Support:** Chrome, Firefox, Safari, Edge with automatic fallback
- **Selenium Integration:** Launches browser headless first, falls back to visible if login needed
- **Login Detection:** Checks for sign-in button presence to determine if user is logged in
- **Cookie Extraction:** Converts Selenium cookies to `http.cookiejar.Cookie` objects
- **Backup Strategy:** Creates `.backup` file before overwriting (preserves working cookies)
- **Interactive Prompts:** Menu-level checks before batch operations, per-download checks for single operations
- **Dependencies:** Selenium and webdriver-manager installed via `requirements.txt`
- **Non-Interactive Mode:** Fails immediately with clear error if cookies invalid (prevents hanging)
- **Key Methods:** `validate()`, `auto_refresh()`, `_extract_with_selenium()`, `_detect_default_browser()`

### Error Handling

- Scripts continue on individual file errors (don't fail entire batch)
- Comprehensive logging to timestamped log files
- Summary statistics printed at completion (converted, skipped, errors)
- USB drive selection with auto-detection and excluded volume list
- Cookie validation errors fail fast with clear instructions
- Browser automation errors trigger fallback to manual instructions

### FFmpeg Integration

- Uses ffmpeg-python library for cleaner API and better error handling
- Still requires system ffmpeg binary (ffmpeg-python is a wrapper, not a replacement)
- Quality setting: VBR mode with libmp3lame, quality level 2 (high quality)
- Error handling: Catches ffmpeg.Error, logs details, continues processing remaining files
- Silent operation: Uses quiet=True to suppress ffmpeg output during batch processing

## Configuration

### config.yaml

YAML configuration file containing both playlists and application settings. Auto-created with defaults if missing.

**Format:**

```yaml
# Music Porter Configuration
# CLI flags override these settings when specified.

settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6

playlists:
  - key: Pop_Workout
    url: https://music.apple.com/us/playlist/...
    name: Pop Workout
  - key: Thumbs_Up
    url: https://music.apple.com/us/playlist/...
    name: Thumbs Up
```

**Playlist fields:**

- `key`: Short identifier (used for directory names)
- `url`: Apple Music playlist URL
- `name`: Display name for the playlist

**Settings fields:**

- `output_type`: Default output profile (`ride-command`, `basic`, etc.)
- `usb_dir`: Default USB subdirectory for sync operations
- `workers`: Number of parallel workers for batch operations

**Settings precedence:** CLI flag > `config.yaml` settings > hardcoded constant. For example, `--output-type basic` on the CLI overrides `output_type: ride-command` in config.yaml, which overrides the `DEFAULT_OUTPUT_TYPE` constant.

**Migration from playlists.conf:** The old pipe-delimited `playlists.conf` format (`key|url|name`) has been replaced by `config.yaml`. The `ConfigManager` class now reads and writes YAML exclusively.

### USB Drive Exclusions

Excluded volumes are configured in `music-porter` (constant: `EXCLUDED_USB_VOLUMES`):

```python
EXCLUDED_USB_VOLUMES = [
    "Macintosh HD",
    "Macintosh HD - Data",
]
```

## Unified Command Architecture

### Overview

The `music-porter` script is a modern, unified Python tool (3,065 lines) that replaces both legacy scripts with a professional subcommand architecture.

### Key Components

**21 Classes:**

1. `Logger` - Timestamped logging to console and file
2. `PlaylistConfig` - Playlist configuration representation
3. `ConfigManager` - Loads and manages config.yaml (playlists + settings)
4. `DependencyChecker` - Checks and installs dependencies
5. `TagStatistics` - Tracks tagging operation statistics
6. `TaggerManager` - Manages MP3 tag operations
7. `ConversionStatistics` - Tracks conversion statistics
8. `Converter` - M4A → MP3 conversion with ffmpeg
9. `Downloader` - Downloads from Apple Music via gamdl
10. `CookieStatus` - Cookie validation result data structure
11. `CookieManager` - Cookie validation, refresh, and browser automation
12. `USBManager` - USB drive detection and syncing
13. `PlaylistSummary` - Statistics for a single playlist
14. `LibrarySummaryStatistics` - Statistics for entire export library
15. `SummaryManager` - Generates export library summaries
16. `PipelineStatistics` - Aggregates statistics across stages
17. `PipelineOrchestrator` - Coordinates multi-stage workflows
18. `InteractiveMenu` - Interactive user interface
19. `PlaylistResult` - Results for single playlist in batch processing
20. `AggregateStatistics` - Cumulative statistics across multiple playlists
21. `CoverArtManager` - Cover art embed, extract, update, and strip operations

**Subcommands:**

- `pipeline` - Full download + convert + tag workflow (default)
- `download` - Download from Apple Music using gamdl
- `convert` - Convert M4A → MP3 with tag preservation
- `tag` - Update tags on existing MP3s
- `restore` - Restore original tags from TXXX frames
- `reset` - Reset tags from source M4A files (⚠️ overwrites TXXX frames)
- `sync-usb` - Copy files to USB drive
- `cover-art` - Cover art management (embed, extract, update, strip)
- `summary` - Display export library statistics

**Features:**

- Professional CLI with `--help` for every command
- Global flags: `--dry-run`, `--verbose`, `--version`
- Comprehensive error handling (continues on failures)
- Detailed statistics and summary reports
- Pipeline orchestration with stage tracking
- Interactive menu with playlist selection
- Backward compatible wrappers for legacy scripts

### Migration from Legacy Scripts

**Automatic migration via wrappers:**

- Old scripts still work but show deprecation warnings
- Internally call `music-porter` with mapped arguments
- No immediate changes required
- Update scripts gradually

**Recommended migration:**

```bash
# Old: do-it-all
./do-it-all --auto
# New: music-porter
./music-porter pipeline --auto

# Old: ride-command-mp3-export
./ride-command-mp3-export music/Pop_Workout/ --output export/Pop_Workout
# New: music-porter
./music-porter convert music/Pop_Workout --output export/ride-command/Pop_Workout
```

### Benefits Over Legacy Scripts

1. **Unified interface** - Single command for all operations
2. **Subcommand architecture** - Professional, extensible CLI
3. **Pipeline orchestration** - Automated multi-stage workflows
4. **Better error handling** - Continues on failures, detailed reporting
5. **Comprehensive statistics** - Aggregated across pipeline stages
6. **Pure Python** - No bash subprocess overhead
7. **Modular design** - 21 classes, easy to extend
8. **Interactive menu** - User-friendly for occasional use
9. **Complete documentation** - 3 comprehensive guides

### Implementation Notes for music-porter

**Tag Management (TaggerManager class):**

- Implements same TXXX hard-gate protection as legacy script
- Uses identical helper functions: `_get_txxx()`, `_txxx_exists()`, `save_original_tag()`
- Maintains full backward compatibility with tag format
- Statistics tracking for all operations

**Conversion (Converter class):**

- Uses ffmpeg with configurable quality presets
- Default: lossless 320kbps CBR (libmp3lame -b:a 320k)
- VBR presets: high (q:a 2), medium (q:a 4), low (q:a 6)
- Custom VBR quality 0-9 supported (0=best, 9=worst)
- Immediate tag application after conversion
- Preserves TXXX frames on force re-conversion
- Identical filename sanitization and output structure

**Configuration Management (ConfigManager class):**

- Reads and writes `config.yaml` using PyYAML
- Auto-creates default `config.yaml` if missing (`_create_default()`)
- Key methods: `get_setting()`, `update_setting()`, `_save()`, `_create_default()`
- Settings resolved via `resolve_config_settings()` helper: CLI flag > config.yaml > hardcoded constant
- Constant: `DEFAULT_CONFIG_FILE = "config.yaml"` (renamed from `DEFAULT_PLAYLISTS_CONF`)
- IMPORT_MAP includes `'PyYAML': 'yaml'` for dependency checking

**Profile-Scoped Export Directories:**

- Export paths are now scoped by output profile: `export/<profile>/<playlist>/`
- Examples: `export/ride-command/Pop_Workout/`, `export/basic/Pop_Workout/`
- Helper function `get_export_dir(profile_name, playlist_key=None)` builds these paths
- Without `playlist_key`: returns `export/<profile>/`
- With `playlist_key`: returns `export/<profile>/<playlist_key>/`

**Pipeline Orchestration (PipelineOrchestrator class):**

- Coordinates: download → convert → tag → USB sync
- Stage dependency handling
- Aggregate statistics across all stages
- Comprehensive summary reports
- Error recovery (continues on individual failures)

**Interactive Menu (InteractiveMenu class):**

- Beautiful formatted menu display with automatic loop-back
- Numbered playlist selection (1-N)
- Letter-based action options:
  - A (All playlists)
  - U (Enter URL)
  - C (Copy to USB)
  - S (Show library summary)
  - P (Change output profile — shows current profile, persists selection to config.yaml)
  - X (Exit)
- Case-insensitive input handling
- Post-processing prompts for USB copy
- Save new URLs to config
- Returns to main menu after each operation (except X to exit)
- Summary display with pause-to-review before returning to menu

**Library Summary (SummaryManager class):**

- Displays comprehensive export library statistics
- Three output modes: default (balanced), quick (aggregate only), detailed (extended)
- Always scans all files for both size/count and tag integrity (no sampling)
- Graceful error handling: continues on permission errors, displays partial results
- Performance: ~0.4 seconds for full library scan (643 files)
- Statistics tracked: total files, total size, per-playlist breakdowns, tag integrity percentages
- Uses same TXXX protection detection as other managers for consistency
- Available in interactive menu as "S. Show library summary" option
- Cover art statistics: tracks files with/without embedded APIC frames

**Cover Art Management (CoverArtManager class):**

- Manages cover art operations on existing MP3 files
- Four actions: `embed`, `extract`, `update`, `strip`
- `embed`: Reads cover art from matching M4A source files (auto-derives `export/` → `music/`)
- `extract`: Saves embedded cover art to image files in `cover-art/` subdirectory
- `update`: Replaces cover art on all MP3s from a single image file (.jpg or .png)
- `strip`: Removes all APIC frames to reduce file size
- Automatic cover art embedding during conversion (APIC frame from M4A source)
- SHA-256 hash prefix stored in `TXXX:OriginalCoverArtHash` with hard-gate protection
- `--no-cover-art` flag on `convert` and `pipeline` commands to skip embedding
- Progress bars for all operations
- Dry-run and verbose support

### Testing Workflow

```bash
# Always use --dry-run first for new operations
./music-porter --dry-run --verbose convert music/NewPlaylist

# Verify with verbose mode
./music-porter --verbose tag export/ride-command/NewPlaylist --album "Test"

# Check logs for detailed information
tail -100 logs/$(ls -t logs/ | head -1)
```

## Additional Resources

- **README.md** - Project overview, quick start guide, and future features roadmap
- **MUSIC-PORTER-GUIDE.md** - Complete usage guide with examples
- **QUICK-REFERENCE.md** - Command cheat sheet for quick lookup
- **IMPLEMENTATION-SUMMARY.md** - Technical implementation details
