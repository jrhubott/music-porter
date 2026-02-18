# apple-to-ride-command - Usage Guide

The unified Apple Music to Ride Command MP3 converter combines download, conversion, tag management, and USB sync into a single powerful tool.

## Quick Start

### Interactive Menu (Recommended)
```bash
./apple-to-ride-command
```
Shows an interactive menu for easy playlist selection and processing.

### Full Pipeline (One Command)
```bash
# Process a configured playlist
./apple-to-ride-command pipeline --playlist "Pop_Workout"

# Process from URL
./apple-to-ride-command pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (auto mode)
./apple-to-ride-command pipeline --auto

# Include USB copy
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb
```

## Commands Overview

### 1. pipeline
**Full download + convert + tag workflow**

```bash
# Process specific playlist
./apple-to-ride-command pipeline --playlist "Pop_Workout"
./apple-to-ride-command pipeline --playlist 1

# Process from URL
./apple-to-ride-command pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (no prompts)
./apple-to-ride-command pipeline --auto

# Include USB sync
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb --usb-dir "RZR/Music"
```

**What it does:**
1. Downloads playlist from Apple Music → `music/{key}/`
2. Converts M4A → MP3 → `export/{key}/`
3. Updates tags (Album = playlist name, Artist = "Various")
4. Optionally copies to USB drive

### 2. download
**Download from Apple Music using gamdl**

```bash
# Download by playlist name/number
./apple-to-ride-command download --playlist "Pop_Workout"
./apple-to-ride-command download --playlist 1

# Download by URL
./apple-to-ride-command download --url "https://music.apple.com/us/playlist/..."

# Custom output directory
./apple-to-ride-command download --playlist "Pop_Workout" --output custom/path
```

**Output:** M4A files in `music/{key}/` directory

### 3. convert
**Convert M4A → MP3 with tag preservation**

```bash
# Basic conversion
./apple-to-ride-command convert music/Pop_Workout

# Specify output directory
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout

# Force re-conversion of existing files
./apple-to-ride-command convert music/Pop_Workout --force
```

**Features:**
- Converts M4A → MP3 using ffmpeg (high quality: -q:a 2)
- Preserves original tags in TXXX frames (OriginalTitle, OriginalArtist, OriginalAlbum)
- Formats title as "Artist - Title"
- Flat output structure: all files saved as "Artist - Title.mp3"
- Skips existing files unless `--force` is used

### 4. tag
**Update tags on existing MP3s**

```bash
# Update album tag
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout"

# Update both album and artist
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout" --artist "Various"
```

**Features:**
- Updates album and/or artist tags
- Stores originals in TXXX frames (hard-gate protection: never overwritten)
- Automatically updates title format to "Artist - Title"
- ID3v2.3 tags by default (better device compatibility)

### 5. restore
**Restore original tags from TXXX frames**

```bash
# Restore all original tags
./apple-to-ride-command restore export/Pop_Workout --all

# Restore specific tags
./apple-to-ride-command restore export/Pop_Workout --album
./apple-to-ride-command restore export/Pop_Workout --title
./apple-to-ride-command restore export/Pop_Workout --artist
```

**Features:**
- Reads values from TXXX:OriginalTitle, TXXX:OriginalArtist, TXXX:OriginalAlbum
- Restores to TIT2, TPE1, TALB frames
- Original TXXX frames remain intact (can restore again later)

### 6. sync-usb
**Copy files to USB drive**

```bash
# Copy default export directory
./apple-to-ride-command sync-usb

# Copy specific directory
./apple-to-ride-command sync-usb export/Pop_Workout

# Custom USB path
./apple-to-ride-command sync-usb export/Pop_Workout --usb-dir "RZR/Music"
```

**Features:**
- Auto-detects USB drives (excludes system volumes)
- Interactive selection if multiple drives found
- Uses rsync for reliable copying with progress display
- Creates destination directory if needed

## Global Options

### --dry-run
Preview changes without modifying any files

```bash
./apple-to-ride-command --dry-run convert music/Pop_Workout
./apple-to-ride-command --dry-run tag export/Pop_Workout --album "Test"
```

### --verbose / -v
Show detailed information during processing

```bash
./apple-to-ride-command --verbose convert music/Pop_Workout
./apple-to-ride-command -v tag export/Pop_Workout --album "Test"
```

### Combined
```bash
./apple-to-ride-command --dry-run --verbose convert music/Pop_Workout
```

## Configuration

### playlists.conf
Format: `key|url|name`

```conf
# Format: key|url|name
Pop_Workout|https://music.apple.com/us/playlist/pop-workout/...|Pop Workout
Thumbs_Up|https://music.apple.com/us/playlist/thumbs-up/...|Thumbs Up
```

**Adding new playlists:**
- Edit `playlists.conf` manually, or
- Use the interactive menu "Enter URL" option (asks to save after download)

## Directory Structure

```
.
├── apple-to-ride-command    # Main script
├── playlists.conf           # Playlist configuration
├── music/                   # Downloaded M4A files (nested by artist/album)
│   └── Pop_Workout/
│       └── Artist/Album/Track.m4a
├── export/                  # Converted MP3 files (flat structure)
│   └── Pop_Workout/
│       └── Artist - Title.mp3
└── logs/                    # Timestamped execution logs
    └── YYYY-MM-DD_HH-MM-SS.log
```

## Tag Preservation System

### How It Works

1. **First conversion/tag update:**
   - Original Title, Artist, Album stored in TXXX frames
   - TXXX:OriginalTitle, TXXX:OriginalArtist, TXXX:OriginalAlbum

2. **Subsequent updates:**
   - TXXX frames are NEVER overwritten (hard-gate protection)
   - You can always restore to true originals

3. **Title formatting:**
   - Converted to "Artist - Title" format
   - Prevents double-compounding (strips existing "Artist - " prefix)

### Example Flow

```bash
# 1. Convert M4A → MP3
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout
# Result: Title = "Ava Max - My Oh My"
#         TXXX:OriginalTitle = "My Oh My"

# 2. Update album tag
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout"
# Result: Album = "Pop Workout"
#         TXXX:OriginalAlbum = "My Oh My - Single" (protected)

# 3. Restore original album
./apple-to-ride-command restore export/Pop_Workout --album
# Result: Album = "My Oh My - Single" (restored from TXXX)
```

## Common Workflows

### Workflow 1: Download and Convert New Playlist
```bash
# Interactive (recommended)
./apple-to-ride-command
# Select playlist, choose to copy to USB

# Or one command
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb
```

### Workflow 2: Update All Playlists
```bash
# Process all configured playlists automatically
./apple-to-ride-command pipeline --auto --copy-to-usb
```

### Workflow 3: One-Time URL Download
```bash
# Download, convert, and copy from a direct URL
./apple-to-ride-command pipeline --url "https://music.apple.com/us/playlist/..."
# Asks to save to playlists.conf after download
```

### Workflow 4: Re-convert with Different Settings
```bash
# Re-convert existing M4A files
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout --force
```

### Workflow 5: Batch Tag Update
```bash
# Update tags on all playlists
for dir in export/*/; do
    name=$(basename "$dir")
    ./apple-to-ride-command tag "$dir" --album "$name" --artist "Various"
done
```

### Workflow 6: Copy Multiple Playlists to USB
```bash
# Copy all exported playlists
./apple-to-ride-command sync-usb export/
```

## Logging

All operations are logged to timestamped files in `logs/`:
- Format: `logs/YYYY-MM-DD_HH-MM-SS.log`
- Includes all console output plus detailed execution info
- Useful for debugging and audit trails

**View recent log:**
```bash
tail -f logs/$(ls -t logs/ | head -1)
```

## Statistics and Summaries

Each command provides detailed summary reports:

### Conversion Summary
```
============================================================
  CONVERSION SUMMARY
============================================================
  Run date:                2026-02-17 23:00:00
  Input directory:         'music/Pop_Workout'
  Output directory:        'export/Pop_Workout'
  Duration:                125.3s
────────────────────────────────────────────────────────────
  FILES
────────────────────────────────────────────────────────────
  Total found:             42
  Converted:               42
  Overwritten:             0
  Skipped (exists):        0
  Errors:                  0
────────────────────────────────────────────────────────────
  TAGGING
────────────────────────────────────────────────────────────
  Title updated:           42
  OriginalTitle stored:    42
  OriginalArtist stored:   42
  OriginalAlbum stored:    42
  OriginalTitle protected: 0
  OriginalArtist protected:0
  OriginalAlbum protected: 0
────────────────────────────────────────────────────────────
  Status:                  ✅ Completed successfully
============================================================
```

### Pipeline Summary
```
======================================================================
  PIPELINE SUMMARY
======================================================================
  Run date:                2026-02-17 23:00:00
  Playlist:                Pop Workout (Pop_Workout)
  Duration:                245.3s
──────────────────────────────────────────────────────────────────────
  DOWNLOAD STAGE
──────────────────────────────────────────────────────────────────────
  Status:                  ✅ Success
  Tracks downloaded:       42
──────────────────────────────────────────────────────────────────────
  CONVERSION STAGE
──────────────────────────────────────────────────────────────────────
  Files converted:         42
  Files overwritten:       0
  Files skipped:           0
  Conversion errors:       0
──────────────────────────────────────────────────────────────────────
  TAGGING STAGE
──────────────────────────────────────────────────────────────────────
  Title updated:           42
  OriginalTitle stored:    42
  OriginalArtist stored:   42
  OriginalAlbum stored:    42
──────────────────────────────────────────────────────────────────────
  USB SYNC STAGE
──────────────────────────────────────────────────────────────────────
  Status:                  ✅ Success
  USB destination:         /Volumes/RZR_MUSIC/RZR/Music
──────────────────────────────────────────────────────────────────────
  Status:                  ✅ Completed successfully
======================================================================
```

## Troubleshooting

### gamdl not found
```bash
# Install gamdl in virtual environment
source .venv/bin/activate
pip install gamdl
```

### ffmpeg not found
```bash
# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg
```

### mutagen not found
```bash
# Auto-installs when script runs, or manually:
pip install mutagen
```

### USB drive not detected
- Check excluded volumes list at top of script
- Ensure drive is mounted in `/Volumes/`
- Check drive permissions

### Conversion fails
- Verify input files are valid M4A
- Check ffmpeg installation
- Try with `--verbose` for detailed error messages
- Check logs in `logs/` directory

## Comparison with Old Scripts

| Feature | do-it-all | ride-command-mp3-export | apple-to-ride-command |
|---------|-----------|-------------------------|----------------------|
| Download | ✅ | ❌ | ✅ |
| Convert | ✅ (calls script) | ✅ | ✅ |
| Tag update | ✅ (calls script) | ✅ | ✅ |
| Tag restore | ❌ | ✅ | ✅ |
| USB sync | ✅ | ❌ | ✅ |
| Interactive menu | ✅ | ❌ | ✅ |
| Pipeline mode | ❌ | ❌ | ✅ |
| Subcommands | ❌ | ❌ | ✅ |
| Dry-run | ❌ | ✅ | ✅ |
| Statistics | Basic | Detailed | Detailed |
| Language | Bash | Python | Python |

## Tips and Best Practices

1. **Always use dry-run first** for new operations
   ```bash
   ./apple-to-ride-command --dry-run --verbose convert music/NewPlaylist
   ```

2. **Keep originals safe** - TXXX frames preserve true originals forever

3. **Use pipeline for new downloads** - handles everything in one command
   ```bash
   ./apple-to-ride-command pipeline --playlist "New_Playlist"
   ```

4. **Check logs** if something goes wrong
   ```bash
   tail -100 logs/$(ls -t logs/ | head -1)
   ```

5. **Test USB sync without copying** using dry-run
   ```bash
   ./apple-to-ride-command --dry-run sync-usb export/Pop_Workout
   ```

6. **Use interactive menu** for occasional use - most user-friendly

7. **Use --auto flag** for scheduled/scripted operations

8. **Backup playlists.conf** before making changes

## Version

Current version: 1.0.0

For bug reports or feature requests, see the project repository.
