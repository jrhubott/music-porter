# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RideCommandMP3Export is a music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format, and optionally copies them to USB drives. The system preserves original tag metadata while allowing customization for device compatibility.

## Architecture

### Core Workflow Pipeline

The system follows an integrated pipeline:

1. **Download** → Downloads Apple Music playlists as M4A files via gamdl
2. **Convert** → Converts M4A to MP3 using ffmpeg (libmp3lame, quality: -q:a 2)
3. **Tag** → Updates and preserves tags with TXXX frame protection
4. **Sync** → Optionally copies to USB drives

### Key Scripts

**apple-to-ride-command** (python) - **RECOMMENDED**
- Unified tool combining all functionality in a single command
- Professional subcommand architecture: `pipeline`, `download`, `convert`, `tag`, `restore`, `reset`, `sync-usb`
- Interactive menu for easy operation
- Comprehensive error handling and statistics
- Full pipeline orchestration (download → convert → tag → USB)
- Modular design with 15 classes
- 2,458 lines of production-ready Python code
- See `APPLE-TO-RIDE-COMMAND-GUIDE.md` for complete documentation

**do-it-all** (bash) - **DEPRECATED**
- Legacy orchestration script (now a compatibility wrapper)
- Calls `apple-to-ride-command` internally
- Will be removed in a future version
- Migrate to: `./apple-to-ride-command`

**ride-command-mp3-export** (python) - **DEPRECATED**
- Legacy conversion and tag management tool (now a compatibility wrapper)
- Calls `apple-to-ride-command` internally
- Will be removed in a future version
- Migrate to: `./apple-to-ride-command`

### Tag Preservation System

The codebase uses a "hard gate" protection system for original metadata:

- Original tags are stored in TXXX (user-defined text) ID3 frames
- Frame names: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`
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
./apple-to-ride-command

# Full pipeline for one playlist
./apple-to-ride-command pipeline --playlist "Pop_Workout"

# Process all playlists automatically
./apple-to-ride-command pipeline --auto

# Get help
./apple-to-ride-command --help
./apple-to-ride-command [command] --help
```

### Full Pipeline Workflows

```bash
# Process a specific playlist (download → convert → tag)
./apple-to-ride-command pipeline --playlist "Pop_Workout"
./apple-to-ride-command pipeline --playlist 1

# Process from direct URL
./apple-to-ride-command pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (auto mode, no prompts)
./apple-to-ride-command pipeline --auto

# Include USB copy after processing
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb

# Custom USB directory
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb --usb-dir "RZR/Music"
```

### Granular Control (Individual Commands)

**Download:**
```bash
# Download specific playlist
./apple-to-ride-command download --playlist "Pop_Workout"

# Download from URL
./apple-to-ride-command download --url "https://music.apple.com/..."

# Custom output directory
./apple-to-ride-command download --playlist "Pop_Workout" --output custom/path
```

**Convert:**
```bash
# Convert M4A files to MP3
./apple-to-ride-command convert music/Pop_Workout

# Specify output directory
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout

# Force re-conversion of existing files
./apple-to-ride-command convert music/Pop_Workout --force
```

**Tag Operations:**
```bash
# Update album tag
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout"

# Update album and artist
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout" --artist "Various"
```

**Restore Original Tags:**
```bash
# Restore all original tags
./apple-to-ride-command restore export/Pop_Workout --all

# Restore specific tags
./apple-to-ride-command restore export/Pop_Workout --album
./apple-to-ride-command restore export/Pop_Workout --title
./apple-to-ride-command restore export/Pop_Workout --artist
```

**Reset Tags from Source (⚠️ Overwrites Protection):**
```bash
# Reset all protection tags from source M4A files
./apple-to-ride-command reset music/Pop_Workout export/Pop_Workout
# Requires confirmation prompt
```

**USB Operations:**
```bash
# Copy to USB drive
./apple-to-ride-command sync-usb export/Pop_Workout

# Copy entire export directory
./apple-to-ride-command sync-usb

# Custom USB directory
./apple-to-ride-command sync-usb export/Pop_Workout --usb-dir "RZR/Music"
```

### Global Flags (Apply to All Commands)

```bash
# Preview changes without modifying files
./apple-to-ride-command --dry-run convert music/Pop_Workout

# Verbose output for detailed information
./apple-to-ride-command --verbose tag export/Pop_Workout --album "Test"

# Combine flags
./apple-to-ride-command --dry-run --verbose convert music/Pop_Workout

# Show version
./apple-to-ride-command --version
```

### Legacy Commands (Deprecated)

⚠️ **The following commands still work but are deprecated:**

```bash
# Old commands (show deprecation warnings, call new tool internally)
./do-it-all                                    # Use: ./apple-to-ride-command
./ride-command-mp3-export music/Pop_Workout/   # Use: ./apple-to-ride-command convert music/Pop_Workout
```

**Migration:** Replace all `do-it-all` and `ride-command-mp3-export` calls with `apple-to-ride-command`. See `APPLE-TO-RIDE-COMMAND-GUIDE.md` for detailed migration instructions.

## Development Setup

### Prerequisites
- Python 3.8+ (uses Python virtual environment)
- ffmpeg (for audio conversion)
- gamdl (Apple Music downloader, installed via pip in venv)
- mutagen (Python ID3 tag library, auto-installed by scripts)

### Initial Setup
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install gamdl mutagen

# Configure playlists
# Edit playlists.conf with format: key|url|name
```

### Testing Changes
- Use `--dry-run` flag extensively to preview behavior
- Use `--verbose` to inspect tag transformations
- Test tag preservation by running updates multiple times
- Verify TXXX frames with: `./apple-to-ride-command --verbose tag export/PlaylistName`

### Common Gotchas

**Apple Music Authentication:**
- Requires `cookies.txt` file with Apple Music session cookies
- Get cookies from browser after logging into music.apple.com
- Cookie file expires periodically and needs refresh
- gamdl will fail without valid authentication

**Virtual Environment:**
- Must activate venv before running: `source .venv/bin/activate`
- Dependencies (gamdl, mutagen) only available inside venv
- Deactivate with `deactivate` command

**Temporary Directories:**
- gamdl creates `gamdl_temp_*` directories during downloads
- Safe to delete after successful downloads
- Not tracked in git (.gitignore)

**USB Drive Detection:**
- Tool auto-detects mounted volumes in `/Volumes/`
- System drives (Macintosh HD) are automatically excluded
- If USB not detected, check mount status: `ls /Volumes/`

## Directory Structure

```
.
├── apple-to-ride-command            # ⭐ Unified tool (RECOMMENDED)
├── do-it-all                        # Legacy wrapper (deprecated)
├── ride-command-mp3-export          # Legacy wrapper (deprecated)
├── do-it-all.backup                 # Original bash script (backup)
├── ride-command-mp3-export.backup   # Original Python script (backup)
├── playlists.conf                   # Playlist configuration
├── music/                           # Downloaded M4A files (organized by playlist)
│   └── Pop_Workout/                 # Nested: Artist/Album/Track.m4a
├── export/                          # Converted MP3 files (flat structure)
│   └── Pop_Workout/                 # Flat: "Artist - Title.mp3"
├── logs/                            # Execution logs (timestamped)
├── .venv/                           # Python virtual environment
├── APPLE-TO-RIDE-COMMAND-GUIDE.md   # Complete usage guide
├── QUICK-REFERENCE.md               # Command cheat sheet
└── IMPLEMENTATION-SUMMARY.md        # Technical documentation
```

## Important Implementation Notes

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

### Error Handling
- Scripts continue on individual file errors (don't fail entire batch)
- Comprehensive logging to timestamped log files
- Summary statistics printed at completion (converted, skipped, errors)
- USB drive selection with auto-detection and excluded volume list

## Configuration

### playlists.conf
Format: `key|url|album_name`
- `key`: Short identifier (used for directory names)
- `url`: Apple Music playlist URL
- `album_name`: Display name for the playlist

Example:
```
Pop_Workout|https://music.apple.com/us/playlist/...|Pop Workout
Thumbs_Up|https://music.apple.com/us/playlist/...|Thumbs Up
```

### USB Drive Exclusions
Excluded volumes are configured in `apple-to-ride-command` (constant: `EXCLUDED_USB_VOLUMES`):
```python
EXCLUDED_USB_VOLUMES = [
    "Macintosh HD",
    "Macintosh HD - Data",
]
```

## Unified Command Architecture

### Overview

The `apple-to-ride-command` script is a modern, unified Python tool (2,458 lines) that replaces both legacy scripts with a professional subcommand architecture.

### Key Components

**15 Classes:**
1. `Logger` - Timestamped logging to console and file
2. `PlaylistConfig` - Playlist configuration representation
3. `ConfigManager` - Loads and manages playlists.conf
4. `DependencyChecker` - Checks and installs dependencies
5. `TagStatistics` - Tracks tagging operation statistics
6. `TaggerManager` - Manages MP3 tag operations
7. `ConversionStatistics` - Tracks conversion statistics
8. `Converter` - M4A → MP3 conversion with ffmpeg
9. `Downloader` - Downloads from Apple Music via gamdl
10. `USBManager` - USB drive detection and syncing
11. `PipelineStatistics` - Aggregates statistics across stages
12. `PipelineOrchestrator` - Coordinates multi-stage workflows
13. `InteractiveMenu` - Interactive user interface
14. `PlaylistResult` - Results for single playlist in batch processing
15. `AggregateStatistics` - Cumulative statistics across multiple playlists

**Subcommands:**
- `pipeline` - Full download + convert + tag workflow (default)
- `download` - Download from Apple Music using gamdl
- `convert` - Convert M4A → MP3 with tag preservation
- `tag` - Update tags on existing MP3s
- `restore` - Restore original tags from TXXX frames
- `reset` - Reset tags from source M4A files (⚠️ overwrites TXXX frames)
- `sync-usb` - Copy files to USB drive

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
- Internally call `apple-to-ride-command` with mapped arguments
- No immediate changes required
- Update scripts gradually

**Recommended migration:**
```bash
# Old: do-it-all
./do-it-all --auto
# New: apple-to-ride-command
./apple-to-ride-command pipeline --auto

# Old: ride-command-mp3-export
./ride-command-mp3-export music/Pop_Workout/ --output export/Pop_Workout
# New: apple-to-ride-command
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout
```

### Benefits Over Legacy Scripts

1. **Unified interface** - Single command for all operations
2. **Subcommand architecture** - Professional, extensible CLI
3. **Pipeline orchestration** - Automated multi-stage workflows
4. **Better error handling** - Continues on failures, detailed reporting
5. **Comprehensive statistics** - Aggregated across pipeline stages
6. **Pure Python** - No bash subprocess overhead
7. **Modular design** - 15 classes, easy to extend
8. **Interactive menu** - User-friendly for occasional use
9. **Complete documentation** - 3 comprehensive guides

### Implementation Notes for apple-to-ride-command

**Tag Management (TaggerManager class):**
- Implements same TXXX hard-gate protection as legacy script
- Uses identical helper functions: `_get_txxx()`, `_txxx_exists()`, `save_original_tag()`
- Maintains full backward compatibility with tag format
- Statistics tracking for all operations

**Conversion (Converter class):**
- Uses ffmpeg with same settings: `libmp3lame -q:a 2`
- Immediate tag application after conversion
- Preserves TXXX frames on force re-conversion
- Identical filename sanitization and output structure

**Pipeline Orchestration (PipelineOrchestrator class):**
- Coordinates: download → convert → tag → USB sync
- Stage dependency handling
- Aggregate statistics across all stages
- Comprehensive summary reports
- Error recovery (continues on individual failures)

**Interactive Menu (InteractiveMenu class):**
- Beautiful formatted menu display
- Numbered playlist selection
- "All playlists", "Enter URL", "Copy to USB" options
- Post-processing prompts for USB copy
- Save new URLs to config

### Testing Workflow

```bash
# Always use --dry-run first for new operations
./apple-to-ride-command --dry-run --verbose convert music/NewPlaylist

# Verify with verbose mode
./apple-to-ride-command --verbose tag export/NewPlaylist --album "Test"

# Check logs for detailed information
tail -100 logs/$(ls -t logs/ | head -1)
```

## Additional Resources

- **APPLE-TO-RIDE-COMMAND-GUIDE.md** - Complete usage guide with examples
- **QUICK-REFERENCE.md** - Command cheat sheet for quick lookup
- **IMPLEMENTATION-SUMMARY.md** - Technical implementation details
