# RideCommandMP3Export

A powerful music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format with configurable quality settings, and optionally syncs them to USB drives for motorcycle audio systems.

## Features

- **Download playlists** from Apple Music using gamdl
- **Convert to MP3** with configurable quality presets (lossless, high, medium, low, custom)
- **Multi-threaded conversion** with configurable parallel workers (`--workers N`)
- **Progress bars** for all operations (convert, tag, restore, download, USB sync)
- **Preserve metadata** with TXXX frame protection for original tags
- **USB sync** with automatic drive detection and intelligent copying
- **Pipeline orchestration** for automated multi-stage workflows
- **Interactive menu** for user-friendly operation
- **Automatic cookie management** with browser-based refresh and validation
- **Comprehensive statistics** and detailed logging
- **Tag management** with update, restore, and reset operations
- **Dry-run mode** for safe preview of all operations
- **Cross-platform support** for macOS, Linux, and Windows

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | ✅ Fully Supported | Primary development platform |
| **Linux** | ✅ Supported | USB detection via /media/ and /mnt/ |
| **Windows** | ✅ Supported | USB detection via drive letters |

### Platform-Specific Notes

**macOS:**
- USB drives detected in `/Volumes/`
- Automatic eject via `diskutil`
- Install ffmpeg: `brew install ffmpeg`
- Activate venv: `source .venv/bin/activate`

**Linux:**
- USB drives detected in `/media/$USER/` and `/mnt/`
- Automatic unmount via `udisksctl` or `umount`
- Install ffmpeg via package manager:
  - Ubuntu/Debian: `sudo apt-get install ffmpeg`
  - Fedora/RHEL: `sudo dnf install ffmpeg`
  - Arch: `sudo pacman -S ffmpeg`
- Activate venv: `source .venv/bin/activate`

**Windows:**
- USB drives detected as drive letters (D:, E:, etc.)
- Manual eject via Windows Explorer (automatic eject not implemented)
- Install ffmpeg:
  - Via Chocolatey: `choco install ffmpeg`
  - Or download from: https://ffmpeg.org/download.html (extract and add to PATH)
- Activate venv: `.venv\Scripts\activate`

## Quick Start

### Prerequisites

- Python 3.8+
- ffmpeg (system binary)
- Valid Apple Music subscription and cookies.txt file

### Installation

```bash
# Clone repository
cd RideCommandMP3Export

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure playlists
# Edit playlists.conf with format: key|url|name
```

### Basic Usage

```bash
# Interactive menu (easiest way to start)
./apple-to-ride-command

# Full pipeline for a specific playlist
./apple-to-ride-command pipeline --playlist "Pop_Workout"

# Process all playlists automatically
./apple-to-ride-command pipeline --auto

# Get help
./apple-to-ride-command --help
./apple-to-ride-command [command] --help
```

## Quality Presets

MP3 conversion supports configurable quality presets to balance file size and audio quality:

| Preset | Mode | Value | Est. Bitrate | Use Case |
|--------|------|-------|--------------|----------|
| `lossless` | CBR | 320kbps | 320kbps | **Default** - Maximum quality, no compromises |
| `high` | VBR | 2 | ~190-250kbps | High quality, smaller files |
| `medium` | VBR | 4 | ~165-210kbps | Balanced quality and size |
| `low` | VBR | 6 | ~115-150kbps | Space-constrained devices |
| `custom` | VBR | 0-9 | Variable | Advanced users (0=best, 9=worst) |

### Quality Examples

```bash
# Default lossless quality (320kbps CBR)
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout

# High quality (VBR)
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout --preset high

# Custom quality (VBR quality 0 - best)
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout --preset custom --quality 0

# Full pipeline with quality preset
./apple-to-ride-command pipeline --playlist "Pop_Workout" --preset medium
```

## Commands Overview

### Pipeline Commands

**Full Pipeline** - Download → Convert → Tag → USB (optional)
```bash
./apple-to-ride-command pipeline --playlist "Pop_Workout"
./apple-to-ride-command pipeline --url "https://music.apple.com/..."
./apple-to-ride-command pipeline --auto  # Process all playlists
./apple-to-ride-command pipeline --playlist 1 --copy-to-usb  # Include USB sync
```

### Individual Commands

**Download** - Download Apple Music playlists
```bash
./apple-to-ride-command download --playlist "Pop_Workout"
./apple-to-ride-command download --url "https://music.apple.com/..."
```

**Convert** - Convert M4A to MP3
```bash
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout
./apple-to-ride-command convert music/Pop_Workout --preset high --force
./apple-to-ride-command convert music/Pop_Workout --workers 4    # Parallel conversion
./apple-to-ride-command convert music/Pop_Workout --workers 1    # Sequential (single-threaded)
```

**Tag** - Update MP3 tags
```bash
./apple-to-ride-command tag export/Pop_Workout --album "Pop Workout"
./apple-to-ride-command tag export/Pop_Workout --album "Pop" --artist "Various"
```

**Restore** - Restore original tags from TXXX frames
```bash
./apple-to-ride-command restore export/Pop_Workout --all
./apple-to-ride-command restore export/Pop_Workout --album --artist
```

**Reset** - Reset tags from source M4A files (⚠️ overwrites TXXX protection)
```bash
./apple-to-ride-command reset music/Pop_Workout export/Pop_Workout
```

**USB Sync** - Copy to USB drive
```bash
./apple-to-ride-command sync-usb export/Pop_Workout
./apple-to-ride-command sync-usb  # Copy entire export directory
```

**Summary** - Display export library statistics
```bash
./apple-to-ride-command summary
./apple-to-ride-command summary --detailed
./apple-to-ride-command summary --quick
```

### Global Flags

```bash
--verbose, -v     Enable verbose output
--dry-run         Preview changes without modifying files
--workers N       Parallel conversion workers (default: min(cpu_count, 4))
--version         Show version information
```

## Documentation

- **[User Guide](APPLE-TO-RIDE-COMMAND-GUIDE.md)** - Complete usage guide with detailed examples
- **[Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md)** - Cookie validation, auto-refresh, and troubleshooting
- **[Quick Reference](QUICK-REFERENCE.md)** - Command cheat sheet for quick lookup
- **[Architecture](CLAUDE.md)** - Developer guide and AI assistant context
- **[Technical Details](IMPLEMENTATION-SUMMARY.md)** - Implementation architecture and design decisions

## Configuration

### playlists.conf Format

```
key|url|album_name
```

Example:
```
Pop_Workout|https://music.apple.com/us/playlist/...|Pop Workout
Thumbs_Up|https://music.apple.com/us/playlist/...|Thumbs Up
```

### Apple Music Authentication

Requires `cookies.txt` file with valid Apple Music session cookies. The tool automatically manages cookie validation and refresh:

**Automatic Cookie Management (Recommended):**
- Cookies are checked at startup and before downloads
- Expired cookies trigger automatic refresh prompt
- Uses your browser (Chrome, Firefox, Safari, or Edge) to extract fresh cookies
- No manual cookie export needed!

**Manual Cookie Export (Alternative):**
1. Log in to music.apple.com in your browser
2. Export cookies using a browser extension
3. Save as `cookies.txt` in the project root

See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md) for detailed instructions.

## Cookie Management

The tool includes intelligent cookie management to prevent authentication failures:

### Automatic Features

✅ **Cookie Validation**
- Checks cookies at startup (shows days remaining)
- Validates before download operations
- Clear status messages (valid/expired/missing)

✅ **Automatic Refresh**
- Interactive prompt when cookies expire: "Attempt automatic cookie refresh? [Y/n]"
- Uses your browser to extract fresh cookies (Chrome, Firefox, Safari, Edge)
- Auto-installs selenium if needed (just press Enter!)
- Creates backup before overwriting (cookies.txt.backup)

✅ **Multi-Browser Support**
- Automatically detects and uses your OS default browser
- Falls back to other installed browsers if needed
- Handles login flow if you're not already logged in

### Quick Examples

```bash
# Automatic refresh (interactive)
./apple-to-ride-command download --playlist 1
# If cookies expired, press Enter to auto-refresh

# Automatic refresh (command-line)
./apple-to-ride-command pipeline --auto --auto-refresh-cookies

# Use custom cookie file
./apple-to-ride-command download --playlist 1 --cookies /path/to/cookies.txt

# Skip validation (not recommended)
./apple-to-ride-command download --playlist 1 --skip-cookie-validation
```

### Optional Dependencies

For automatic cookie refresh, install optional dependencies:

```bash
source .venv/bin/activate
pip install -r requirements-optional.txt
```

This installs `selenium` and `webdriver-manager` for browser automation. Alternatively, the tool will offer to install these automatically when you first use auto-refresh.

**See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md) for complete documentation including troubleshooting, security details, and manual refresh instructions.**

## Project Structure

```
.
├── apple-to-ride-command            # Main unified tool (RECOMMENDED)
├── do-it-all                        # Legacy wrapper (deprecated)
├── ride-command-mp3-export          # Legacy wrapper (deprecated)
├── playlists.conf                   # Playlist configuration
├── cookies.txt                      # Apple Music authentication
├── music/                           # Downloaded M4A files (nested structure)
│   └── Pop_Workout/                 # Artist/Album/Track.m4a
├── export/                          # Converted MP3 files (flat structure)
│   └── Pop_Workout/                 # "Artist - Title.mp3"
├── logs/                            # Execution logs (timestamped)
├── .venv/                           # Python virtual environment
└── docs/                            # Documentation
```

## Troubleshooting

### Common Issues

**Cookies expired / Downloads fail with authentication error**
- Tool automatically detects expired cookies at startup
- Use auto-refresh: `./apple-to-ride-command download --playlist 1` → press Enter when prompted
- Or use `--auto-refresh-cookies` flag for non-interactive refresh
- Manual refresh: Export cookies from music.apple.com browser extension
- See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md) for detailed troubleshooting

**FFmpeg not found**
- Install ffmpeg: `brew install ffmpeg` (macOS) or equivalent
- Verify installation: `ffmpeg -version`

**USB drive not detected**
- Check drive is mounted: `ls /Volumes/`
- Ensure drive is not in excluded volumes list
- System drives (Macintosh HD) are automatically excluded

**Tags not updating correctly**
- Original tags are protected in TXXX frames and never overwritten
- Use `--restore-*` flags to restore from protected originals
- Use `reset` command to re-read from source M4A files (⚠️ overwrites protection)

**Virtual environment issues**
- Activate venv: `source .venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (requires 3.8+)

For more detailed troubleshooting, see the [User Guide](APPLE-TO-RIDE-COMMAND-GUIDE.md).

## Architecture Highlights

### Tag Preservation System

The tool uses a "hard gate" protection system for original metadata:
- Original tags stored in TXXX (user-defined text) ID3 frames
- Frame names: `OriginalTitle`, `OriginalArtist`, `OriginalAlbum`
- Once written, these frames are **never overwritten**
- Restoration always possible via `--restore-*` flags

### ID3 Tag Standards

- Default output: ID3v2.3 (older device compatibility)
- ID3v1 tags stripped by default (clean metadata)
- Duplicate frames automatically removed
- Override with `--keep-id3v1`, `--keep-id3v24`, `--keep-duplicates`

### FFmpeg Integration

- Uses ffmpeg-python library for cleaner API
- Requires system ffmpeg binary (wrapper, not replacement)
- Lossless: 320kbps CBR with libmp3lame
- VBR: Quality levels 0-9 (0=best, 9=worst)
- Multi-threaded: parallel ffmpeg workers via `--workers N` (default: min(cpu_count, 4))
- Error handling: continues processing on individual failures

## Future Features

### High Priority
1. **Playlist sync detection** - Compare local library to Apple Music, download only new/changed tracks
2. **Incremental updates** - Smart detection of changed tracks without full re-download
3. ~~**Multi-threaded conversion** - Parallel processing for faster batch conversions~~ *(implemented in v1.3.0)*
4. **Batch tag operations** - Apply tag changes to multiple playlists at once
5. **Configuration presets** - Save and load common conversion/tagging configurations

### Medium Priority
6. **Web UI** - Browser-based interface for remote management
7. **Automatic USB detection** - Start sync when USB drive is plugged in
8. ~~**Progress indicators** - Real-time progress bars for long-running operations~~ *(implemented in v1.4.0)*
9. **Download resume** - Resume interrupted downloads
10. ~~**Cover art management** - Embed, extract, and update album artwork~~ *(implemented in v1.5.0)*
11. **Playlist merging** - Combine multiple playlists into one
12. **Smart playlists** - Auto-generate playlists based on criteria (genre, artist, etc.)
13. **Duplicate detection** - Find and remove duplicate tracks across playlists
14. **Tag validation** - Verify tag integrity and fix common issues
15. **Export formats** - Support for additional formats (FLAC, AAC, OGG)

### Low Priority / Nice to Have
16. **Spotify integration** - Download from Spotify playlists
17. **YouTube Music integration** - Download from YouTube Music playlists
18. **Metadata enrichment** - Fetch additional metadata from online databases
19. **Lyrics embedding** - Download and embed synchronized lyrics
20. **BPM detection** - Analyze and tag tracks with BPM information
21. **Playlist statistics** - Detailed analytics (genre distribution, duration, etc.)
22. **Tag history** - Track changes to tags over time
23. **Backup and restore** - Backup entire library with metadata
24. **Cloud storage sync** - Sync to Dropbox, Google Drive, etc.
25. **Mobile app** - iOS/Android app for remote control
26. **Scheduling** - Automatic periodic syncing on schedule
27. **Notification system** - Email/SMS alerts for completed operations
28. **Custom filename templates** - Configurable output filename patterns
29. **Equalizer presets** - Apply audio processing (normalization, compression)
30. **Collaborative playlists** - Share playlists with others for collaborative management

## Version

Current version: **v1.5.0**

## License

See project license file for details.

## Contributing

This is a personal project, but suggestions and improvements are welcome via GitHub issues.
