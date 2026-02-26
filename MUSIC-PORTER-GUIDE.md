# music-porter - Usage Guide

The unified Apple Music to Ride Command MP3 converter combines download, conversion, tag management, and USB sync into a single powerful tool.

## Technical Notes

The tool uses the ffmpeg-python library for audio conversion, which provides a Pythonic API around the system ffmpeg binary. The ffmpeg binary must be installed on your system. The Python library is automatically installed when running the tool for the first time.

Configuration is stored in `config.yaml` (YAML format), which requires the `PyYAML>=6.0` dependency (installed via `requirements.txt`). If `config.yaml` does not exist, a default one is auto-created on first run.

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
- **Windows:** `choco install ffmpeg` or download from <https://ffmpeg.org/download.html>

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
./music-porter
```

Shows an interactive menu for easy playlist selection and processing.

**Menu options:**
- **1-N** - Select a numbered playlist to process
- **A** - Process all playlists (auto mode)
- **U** - Enter a URL to download
- **C** - Sync to destination (USB drives, saved paths, custom paths)
- **P** - Change output profile (shows current profile, persists choice to `config.yaml`)
- **S** - Show library summary
- **X** - Exit

### Full Pipeline (One Command)

```bash
# Process a configured playlist
./music-porter pipeline --playlist "Pop_Workout"

# Process from URL
./music-porter pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (auto mode)
./music-porter pipeline --auto

# With quality preset (lossless, high, medium, low, custom)
./music-porter pipeline --playlist "Pop_Workout" --preset high

# Include USB copy
./music-porter pipeline --playlist "Pop_Workout" --copy-to-usb
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
./music-porter pipeline --auto --auto-refresh-cookies

# Use custom cookie file
./music-porter download --playlist 1 --cookies /path/to/cookies.txt

# Skip validation (not recommended)
./music-porter download --playlist 1 --skip-cookie-validation
```

### Browser Support

Supports **Chrome**, **Firefox**, **Safari**, and **Edge**:
- Automatically detects your default browser
- Falls back to other installed browsers if needed
- Works on macOS, Linux, and Windows

### Manual Cookie Refresh (Alternative)

If you prefer manual control or automation fails:

1. Open your browser and go to: <https://music.apple.com>
2. Log in to your Apple Music account
3. Install browser extension:
   - **Chrome**: "Get cookies.txt LOCALLY" extension
   - **Firefox**: "cookies.txt" extension
4. Click extension icon → Export cookies.txt
5. Save as `cookies.txt` in project directory

### Troubleshooting

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
./music-porter pipeline --playlist "Pop_Workout"
./music-porter pipeline --playlist 1

# Process from URL
./music-porter pipeline --url "https://music.apple.com/us/playlist/..."

# Process all playlists (no prompts)
./music-porter pipeline --auto

# With quality preset
./music-porter pipeline --playlist "Pop_Workout" --preset high
./music-porter pipeline --auto --preset medium

# Include USB sync
./music-porter pipeline --playlist "Pop_Workout" --copy-to-usb --usb-dir "RZR/Music"
```

**What it does:**
1. Downloads playlist from Apple Music → `music/{key}/`
2. Converts M4A → MP3 → `export/{profile}/{key}/`
3. Updates tags (Album = playlist name, Artist = "Various")
4. Optionally copies to USB drive

### 2. download

**Download from Apple Music using gamdl**

```bash
# Download by playlist name/number
./music-porter download --playlist "Pop_Workout"
./music-porter download --playlist 1

# Download by URL
./music-porter download --url "https://music.apple.com/us/playlist/..."

# Custom output directory
./music-porter download --playlist "Pop_Workout" --output custom/path
```

**Output:** M4A files in `music/{key}/` directory

### 3. convert

**Convert M4A → MP3 with tag preservation**

```bash
# Basic conversion (default: lossless 320kbps)
./music-porter convert music/Pop_Workout

# Specify output directory
./music-porter convert music/Pop_Workout --output export/ride-command/Pop_Workout

# With quality presets
./music-porter convert music/Pop_Workout --preset high
./music-porter convert music/Pop_Workout --preset medium
./music-porter convert music/Pop_Workout --preset custom --quality 0

# Force re-conversion of existing files
./music-porter convert music/Pop_Workout --force

# Combine flags
./music-porter convert music/Pop_Workout --preset high --force
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
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout"

# Update both album and artist
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout" --artist "Various"
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
./music-porter restore export/ride-command/Pop_Workout --all

# Restore specific tags
./music-porter restore export/ride-command/Pop_Workout --album
./music-porter restore export/ride-command/Pop_Workout --title
./music-porter restore export/ride-command/Pop_Workout --artist
```

**Features:**
- Reads values from TXXX:OriginalTitle, TXXX:OriginalArtist, TXXX:OriginalAlbum
- Restores to TIT2, TPE1, TALB frames
- Original TXXX frames remain intact (can restore again later)

### 6. sync

**Sync files to destinations (USB drives, saved paths, custom paths)**

```bash
# Interactive destination picker
./music-porter sync

# Sync to saved destination
./music-porter sync --dest nas-backup

# Sync to custom path
./music-porter sync --dest /Volumes/NAS/Music

# Sync specific directory
./music-porter sync export/ride-command/Pop_Workout --dest nas-backup

# Manage saved destinations
./music-porter sync --list-destinations
./music-porter sync --add-dest nas-backup /Volumes/NAS/Music
./music-porter sync --remove-dest nas-backup

# View sync tracking status
./music-porter sync --status
./music-porter sync --status --usb-key nas-backup

# Legacy USB sync (backwards compatible)
./music-porter sync-usb export/ride-command/Pop_Workout --usb-dir "RZR/Music"
```

**Features:**
- Unified destination picker: USB drives, saved destinations, and custom paths
- Saved destinations stored in config.yaml for quick reuse
- Auto-detects USB drives (excludes system volumes)
- Incremental sync with size+mtime comparison
- Persistent sync tracking across sessions
- USB eject offered only for USB destinations

## Global Options

### --dry-run

Preview changes without modifying any files

```bash
./music-porter --dry-run convert music/Pop_Workout
./music-porter --dry-run tag export/ride-command/Pop_Workout --album "Test"
```

### --verbose / -v

Show detailed information during processing

```bash
./music-porter --verbose convert music/Pop_Workout
./music-porter -v tag export/ride-command/Pop_Workout --album "Test"
```

### Combined

```bash
./music-porter --dry-run --verbose convert music/Pop_Workout
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
./music-porter convert music/Pop_Workout

# High quality VBR
./music-porter convert music/Pop_Workout --preset high

# Medium quality VBR (balanced)
./music-porter convert music/Pop_Workout --preset medium

# Low quality VBR (space-saving)
./music-porter convert music/Pop_Workout --preset low
```

#### Custom Quality

```bash
# Custom VBR quality 0 (best possible)
./music-porter convert music/Pop_Workout --preset custom --quality 0

# Custom VBR quality 5 (medium-low)
./music-porter convert music/Pop_Workout --preset custom --quality 5

# Note: --preset custom REQUIRES --quality parameter
```

#### Pipeline Integration

```bash
# Full pipeline with high quality
./music-porter pipeline --playlist "Pop_Workout" --preset high

# Batch process all playlists with medium quality
./music-porter pipeline --auto --preset medium

# URL download with custom quality
./music-porter pipeline --url "https://..." --preset custom --quality 0
```

#### Force Re-conversion with New Quality

```bash
# Re-convert existing files with different quality
./music-porter convert music/Pop_Workout --preset high --force
```

### Quality Setting Display

When using `--verbose`, quality settings are displayed:

```bash
./music-porter --verbose convert music/Pop_Workout --preset high
# Output includes:
# Quality: VBR quality 2 (preset: high)
```

Conversion summaries also show quality settings:

```text
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
./music-porter convert music/Pop_Workout --preset custom
# Error: --preset custom requires --quality parameter (0-9)

# Out of range quality value
./music-porter convert music/Pop_Workout --preset custom --quality 15
# Error: --quality must be between 0-9, got: 15

# --quality without custom preset (warning, not error)
./music-porter convert music/Pop_Workout --preset high --quality 5
# Warning: --quality ignored unless --preset custom is specified
```

## Configuration

### config.yaml

The tool uses a YAML configuration file (`config.yaml`) for playlists and settings. If `config.yaml` does not exist, a default one is auto-created on first run.

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6

playlists:
  - key: Pop_Workout
    url: https://music.apple.com/us/playlist/pop-workout/...
    name: Pop Workout
  - key: Thumbs_Up
    url: https://music.apple.com/us/playlist/thumbs-up/...
    name: Thumbs Up
```

**Settings fields:**
- `output_type`: Default output profile (e.g., `ride-command`, `basic`). Overridden by `--output-type` CLI flag.
- `usb_dir`: Default USB destination directory. Overridden by `--usb-dir` CLI flag.

A `destinations` section can also be added to save named sync destinations:

```yaml
destinations:
  - name: nas-backup
    path: /Volumes/NAS/Music
  - name: studio-pc
    path: /mnt/studio/Music
```

- `workers`: Number of parallel workers for batch operations.

**Playlist fields:**
- `key`: Short identifier (used for directory names)
- `url`: Apple Music playlist URL
- `name`: Display name for the playlist

**Settings precedence:** CLI flag > config.yaml > hardcoded constant

**Adding new playlists:**
- Edit `config.yaml` manually, or
- Use the interactive menu "Enter URL" option (asks to save after download)

## Directory Structure

```text
.
├── music-porter    # Main script
├── config.yaml              # Playlist and settings configuration
├── music/                   # Downloaded M4A files (nested by artist/album)
│   └── Pop_Workout/
│       └── Artist/Album/Track.m4a
├── export/                  # Converted MP3 files (profile-scoped, flat structure)
│   └── ride-command/        # Output profile directory
│       └── Pop_Workout/
│           └── Artist - Title.mp3
└── logs/                    # Timestamped execution logs
    └── YYYY-MM-DD_HH-MM-SS.log
```

Export directories are scoped by the active output profile: `export/<profile>/<playlist>/` (e.g., `export/ride-command/Pop_Workout/`, `export/basic/Pop_Workout/`). This keeps outputs from different profiles separate.

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
./music-porter convert music/Pop_Workout --output export/ride-command/Pop_Workout
# Result: Title = "Ava Max - My Oh My"
#         TXXX:OriginalTitle = "My Oh My"

# 2. Update album tag
./music-porter tag export/ride-command/Pop_Workout --album "Pop Workout"
# Result: Album = "Pop Workout"
#         TXXX:OriginalAlbum = "My Oh My - Single" (protected)

# 3. Restore original album
./music-porter restore export/ride-command/Pop_Workout --album
# Result: Album = "My Oh My - Single" (restored from TXXX)
```

## Common Workflows

### Workflow 1: Download and Convert New Playlist

```bash
# Interactive (recommended)
./music-porter
# Select playlist, choose to copy to USB

# Or one command
./music-porter pipeline --playlist "Pop_Workout" --copy-to-usb
```

### Workflow 2: Update All Playlists

```bash
# Process all configured playlists automatically
./music-porter pipeline --auto --copy-to-usb
```

### Workflow 3: One-Time URL Download

```bash
# Download, convert, and copy from a direct URL
./music-porter pipeline --url "https://music.apple.com/us/playlist/..."
# Asks to save to config.yaml after download
```

### Workflow 4: Re-convert with Different Settings

```bash
# Re-convert existing M4A files
./music-porter convert music/Pop_Workout --output export/ride-command/Pop_Workout --force
```

### Workflow 5: Batch Tag Update

```bash
# Update tags on all playlists for the ride-command profile
for dir in export/ride-command/*/; do
    name=$(basename "$dir")
    ./music-porter tag "$dir" --album "$name" --artist "Various"
done
```

### Workflow 6: Sync to Destinations

```bash
# Sync all exports to a saved destination
./music-porter sync --dest nas-backup

# Sync all exports to USB (legacy)
./music-porter sync-usb export/ride-command/
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

```text
============================================================
  CONVERSION SUMMARY
============================================================
  Run date:                2026-02-17 23:00:00
  Input directory:         'music/Pop_Workout'
  Output directory:        'export/ride-command/Pop_Workout'
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

```text
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

| Feature | do-it-all | ride-command-mp3-export | music-porter |
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
   ./music-porter --dry-run --verbose convert music/NewPlaylist
   ```

2. **Keep originals safe** - TXXX frames preserve true originals forever

3. **Use pipeline for new downloads** - handles everything in one command

   ```bash
   ./music-porter pipeline --playlist "New_Playlist"
   ```

4. **Check logs** if something goes wrong

   ```bash
   tail -100 logs/$(ls -t logs/ | head -1)
   ```

5. **Test sync without copying** using dry-run

   ```bash
   ./music-porter sync --dest nas-backup --dry-run
   ```

6. **Use interactive menu** for occasional use - most user-friendly

7. **Use --auto flag** for scheduled/scripted operations

8. **Backup config.yaml** before making changes

## Version

Current version: 1.0.0

For bug reports or feature requests, see the project repository.
