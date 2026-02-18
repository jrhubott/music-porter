# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RideCommandMP3Export is a music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format, and optionally copies them to USB drives. The system preserves original tag metadata while allowing customization for device compatibility.

## Architecture

### Core Workflow Pipeline

The system follows a two-stage pipeline:

1. **Download** (`gamdl` via `do-it-all`) → Downloads Apple Music playlists as M4A files
2. **Convert & Tag** (`ride-command-mp3-export`) → Converts M4A to MP3 with tag preservation and standardization

### Key Scripts

**do-it-all** (bash)
- Main orchestration script for the complete workflow
- Manages virtual environment, playlist selection, and USB copying
- Supports interactive menu, auto mode, and direct URL processing
- Configuration: `playlists.conf` (format: `key|url|name`)
- Logs all operations to `logs/YYYY-MM-DD_HH-MM-SS.log`

**ride-command-mp3-export** (python)
- Primary conversion and tag management tool
- Converts M4A → MP3 using ffmpeg with libmp3lame codec (quality: -q:a 2)
- Implements tag preservation system using TXXX frames (OriginalTitle, OriginalArtist, OriginalAlbum)
- Can perform conversion and tag updates in a single operation
- Modes: conversion, tag update, tag restore, rescan from source
- Output: flat directory structure with "Artist - Title.mp3" naming
- Sets album/artist tags and formats titles as "Artist - Title"
- Removes extraneous tags, keeps only: Title, Artist, Album, Length, Date, Album Artist

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

### Full Pipeline
```bash
# Interactive menu (recommended for first-time users)
./do-it-all

# Auto mode - process all configured playlists
./do-it-all --auto

# Process a specific playlist
./do-it-all --playlist "Pop_Workout"
./do-it-all --playlist 3

# Process a direct URL
./do-it-all --url "https://music.apple.com/us/playlist/..."
```

### Conversion Only
```bash
# Convert M4A files to MP3
./ride-command-mp3-export music/Thumbs_Up/

# Specify custom output directory
./ride-command-mp3-export music/Thumbs_Up/ --output converted_mp3/Thumbs_Up

# Force re-conversion of existing files
./ride-command-mp3-export music/Thumbs_Up/ --force
```

### Tag Operations
```bash
# Update album tag on existing MP3s
./ride-command-mp3-export converted_mp3/ --new-album "Pop Workout"

# Update album and artist
./ride-command-mp3-export converted_mp3/ --new-album "Pop Workout" --new-artist "Compilations"

# Convert and tag in one step
./ride-command-mp3-export music/Pop_Workout/ --output export/Pop_Workout --new-album "Pop Workout"

# Restore original tags
./ride-command-mp3-export converted_mp3/ --restore-all
./ride-command-mp3-export converted_mp3/ --restore-album
./ride-command-mp3-export converted_mp3/ --restore-title

# Rescan from source M4A files (resets protection tags)
./ride-command-mp3-export music/Pop_Workout/ --output export/Pop_Workout --rescan
```

### USB Operations
```bash
# Copy to USB after processing
./do-it-all --copy-to-usb

# Specify custom USB directory
./do-it-all --copy-to-usb --usb-dir "RZR/Music"
```

### Testing and Debugging
```bash
# Preview changes without modifying files
./ride-command-mp3-export music/Thumbs_Up/ --dry-run

# Verbose output for tag inspection
./ride-command-mp3-export music/Thumbs_Up/ --verbose

# Dry run with verbose
./ride-command-mp3-export music/Thumbs_Up/ --dry-run --verbose
```

## Development Setup

### Prerequisites
- Python 3.14+ (uses Python virtual environment)
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
- Verify TXXX frames with: `./ride-command-mp3-export --verbose`

## Directory Structure

```
.
├── do-it-all                   # Main orchestration script
├── ride-command-mp3-export     # Primary conversion/tagging tool
├── playlists.conf              # Playlist configuration
├── music/                      # Downloaded M4A files (organized by playlist)
├── export/                     # Converted MP3 files (flat structure)
├── converted_mp3/              # Default conversion output
├── logs/                       # Execution logs (timestamped)
└── .venv/                      # Python virtual environment
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
Edit `excluded_volumes` array in `do-it-all`:
```bash
excluded_volumes=(
    "Macintosh HD"
    "Macintosh HD - Data"
)
```
