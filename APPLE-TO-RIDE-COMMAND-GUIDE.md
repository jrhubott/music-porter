# apple-to-ride-command - Usage Guide

The unified Apple Music to Ride Command MP3 converter combines download, conversion, tag management, and USB sync into a single powerful tool.

## Technical Notes

The tool uses the ffmpeg-python library for audio conversion, which provides a Pythonic API around the system ffmpeg binary. The ffmpeg binary must be installed on your system. The Python library is automatically installed when running the tool for the first time.

## Platform Support

The tool runs on **macOS**, **Linux**, and **Windows** with automatic platform detection.

| Feature | macOS | Linux | Windows |
|---------|-------|-------|---------|
| MP3 Conversion | ✅ | ✅ | ✅ |
| Tag Management | ✅ | ✅ | ✅ |
| USB Detection | ✅ Auto (`/Volumes/`) | ✅ Auto (`/media/`, `/mnt/`) | ✅ Auto (Drive letters) |
| USB Eject | ✅ Auto (`diskutil`) | ✅ Auto (`udisksctl`/`umount`) | ⚠️ Manual (Explorer) |

### Platform-Specific Setup

**FFmpeg Installation:**
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt-get install ffmpeg` (Ubuntu/Debian), `sudo dnf install ffmpeg` (Fedora/RHEL), `sudo pacman -S ffmpeg` (Arch)
- **Windows:** `choco install ffmpeg` or download from https://ffmpeg.org/download.html

**Virtual Environment Activation:**
- **macOS/Linux:** `source .venv/bin/activate`
- **Windows:** `.venv\Scripts\activate`

**USB Drive Locations:**
- **macOS:** `/Volumes/{drive-name}` (excludes system volumes)
- **Linux:** `/media/$USER/{drive-name}` or `/mnt/{drive-name}` (excludes boot, root)
- **Windows:** `{letter}:\` e.g., `D:\`, `E:\` (excludes C:)

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

# With quality preset (lossless, high, medium, low, custom)
./apple-to-ride-command pipeline --playlist "Pop_Workout" --preset high

# Include USB copy
./apple-to-ride-command pipeline --playlist "Pop_Workout" --copy-to-usb
```

## Cookie Management

The tool automatically manages Apple Music authentication cookies, validating them before downloads and offering to refresh when expired.

### Automatic Cookie Validation

Cookies are checked at **two points**:
1. **Startup** - Shows status (informational, doesn't block)
2. **Before downloads** - Validates and blocks if invalid

**Status messages:**
```bash
# Valid cookies
[OK] Cookie status: Cookies valid until 2026-08-16 (178 days remaining)

# Expired cookies
[WARN] Cookie status: Cookies expired on 2026-02-15 (3 days ago)
Downloads will fail until cookies are refreshed
```

### Interactive Auto-Refresh

When cookies are invalid, you'll be prompted:

```bash
[ERROR] Cookies expired on 2026-02-15 (3 days ago)

============================================================
Apple Music Cookie Refresh Required
============================================================
[... manual instructions ...]
============================================================

Attempt automatic cookie refresh? [Y/n]  ← Just press Enter!
```

**What happens:**
1. Tool detects and uses your OS default browser
2. Opens browser (headless if already logged in, visible if not)
3. Extracts cookies from your browser session
4. Creates backup: `cookies.txt.backup`
5. Saves new cookies and validates them
6. Continues with your operation

### Command-Line Flags

```bash
# Auto-refresh cookies (non-interactive)
./apple-to-ride-command pipeline --auto --auto-refresh-cookies

# Use custom cookie file
./apple-to-ride-command download --playlist 1 --cookies /path/to/cookies.txt

# Skip validation (not recommended)
./apple-to-ride-command download --playlist 1 --skip-cookie-validation
```

### Browser Support

Supports **Chrome**, **Firefox**, **Safari**, and **Edge**:
- Automatically detects your default browser
- Falls back to other installed browsers if needed
- Works on macOS, Linux, and Windows

### Optional Dependencies

For automatic cookie refresh:

```bash
source .venv/bin/activate
pip install -r requirements-optional.txt
```

Alternatively, the tool will **offer to auto-install** selenium when you first use `--auto-refresh-cookies`.

### Manual Cookie Refresh (Alternative)

If you prefer manual control or automation fails:

1. Open your browser and go to: https://music.apple.com
2. Log in to your Apple Music account
3. Install browser extension:
   - **Chrome**: "Get cookies.txt LOCALLY" extension
   - **Firefox**: "cookies.txt" extension
4. Click extension icon → Export cookies.txt
5. Save as `cookies.txt` in project directory

### Troubleshooting

**Selenium not installed:**
```
[ERROR] Selenium not installed
Install selenium now? [Y/n]  ← Press Enter to auto-install
```

**All browsers failed:**
- Update your browser to the latest version
- Try a different browser
- Use manual refresh method
- Check if you're logged in to Apple Music

**See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md) for complete troubleshooting and security details.**

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

# With quality preset
./apple-to-ride-command pipeline --playlist "Pop_Workout" --preset high
./apple-to-ride-command pipeline --auto --preset medium

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
# Basic conversion (default: lossless 320kbps)
./apple-to-ride-command convert music/Pop_Workout

# Specify output directory
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout

# With quality presets
./apple-to-ride-command convert music/Pop_Workout --preset high
./apple-to-ride-command convert music/Pop_Workout --preset medium
./apple-to-ride-command convert music/Pop_Workout --preset custom --quality 0

# Force re-conversion of existing files
./apple-to-ride-command convert music/Pop_Workout --force

# Combine flags
./apple-to-ride-command convert music/Pop_Workout --preset high --force
```

**Features:**
- Converts M4A → MP3 using ffmpeg with configurable quality (default: lossless 320kbps CBR)
- Quality presets: lossless, high, medium, low, custom (see Quality Presets section)
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

## Quality Presets

MP3 conversion supports configurable quality presets to balance file size and audio quality. All `convert` and `pipeline` commands accept the `--preset` flag.

### Available Presets

| Preset | Mode | Value | Est. Bitrate | Use Case |
|--------|------|-------|--------------|----------|
| `lossless` | CBR | 320kbps | 320kbps | **Default** - Maximum quality, no compromises |
| `high` | VBR | 2 | ~190-250kbps | High quality, smaller files than lossless |
| `medium` | VBR | 4 | ~165-210kbps | Balanced quality and file size |
| `low` | VBR | 6 | ~115-150kbps | Space-constrained devices |
| `custom` | VBR | 0-9 | Variable | Advanced users (0=best quality, 9=worst) |

### Understanding the Modes

**CBR (Constant Bit Rate):**
- Fixed bitrate throughout the entire file
- Predictable file sizes
- Used for `lossless` preset (320kbps)
- Best for maximum quality and compatibility

**VBR (Variable Bit Rate):**
- Bitrate varies based on audio complexity
- More efficient encoding (better quality per MB)
- Used for `high`, `medium`, `low`, and `custom` presets
- Quality scale: 0 (best) to 9 (worst)

### Usage Examples

#### Basic Usage
```bash
# Default (lossless 320kbps CBR)
./apple-to-ride-command convert music/Pop_Workout

# High quality VBR
./apple-to-ride-command convert music/Pop_Workout --preset high

# Medium quality VBR (balanced)
./apple-to-ride-command convert music/Pop_Workout --preset medium

# Low quality VBR (space-saving)
./apple-to-ride-command convert music/Pop_Workout --preset low
```

#### Custom Quality
```bash
# Custom VBR quality 0 (best possible)
./apple-to-ride-command convert music/Pop_Workout --preset custom --quality 0

# Custom VBR quality 5 (medium-low)
./apple-to-ride-command convert music/Pop_Workout --preset custom --quality 5

# Note: --preset custom REQUIRES --quality parameter
```

#### Pipeline Integration
```bash
# Full pipeline with high quality
./apple-to-ride-command pipeline --playlist "Pop_Workout" --preset high

# Batch process all playlists with medium quality
./apple-to-ride-command pipeline --auto --preset medium

# URL download with custom quality
./apple-to-ride-command pipeline --url "https://..." --preset custom --quality 0
```

#### Force Re-conversion with New Quality
```bash
# Re-convert existing files with different quality
./apple-to-ride-command convert music/Pop_Workout --preset high --force
```

### Quality Setting Display

When using `--verbose`, quality settings are displayed:
```bash
./apple-to-ride-command --verbose convert music/Pop_Workout --preset high
# Output includes:
# Quality: VBR quality 2 (preset: high)
```

Conversion summaries also show quality settings:
```
QUALITY SETTINGS
─────────────────────────────────────────────────────────
Preset:                  high
Mode:                    VBR quality 2
```

### Choosing the Right Preset

**Use `lossless` when:**
- Maximum quality is priority
- Storage space is not a concern
- You want bit-perfect audio
- Default for most users

**Use `high` when:**
- You want great quality with smaller files
- ~20-30% file size reduction vs lossless
- Good balance for most listening scenarios

**Use `medium` when:**
- File size is important
- ~40-50% file size reduction vs lossless
- Still good quality for casual listening
- Good for space-constrained USB drives

**Use `low` when:**
- Maximum space savings needed
- ~60-70% file size reduction vs lossless
- Acceptable for background music
- Limited storage devices

**Use `custom` when:**
- You know exactly what VBR quality you need
- Fine-tuning for specific requirements
- Advanced users only

### Error Handling

Invalid quality settings produce clear errors:
```bash
# Missing --quality with custom preset
./apple-to-ride-command convert music/Pop_Workout --preset custom
# Error: --preset custom requires --quality parameter (0-9)

# Out of range quality value
./apple-to-ride-command convert music/Pop_Workout --preset custom --quality 15
# Error: --quality must be between 0-9, got: 15

# --quality without custom preset (warning, not error)
./apple-to-ride-command convert music/Pop_Workout --preset high --quality 5
# Warning: --quality ignored unless --preset custom is specified
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
