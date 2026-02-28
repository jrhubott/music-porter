# Music Porter

A server-based music playlist management and conversion tool that downloads Apple Music playlists, converts them to MP3 format with configurable quality settings, and syncs to USB drives and other destinations. All operations are managed through a web dashboard and REST API.

## Features

- **Web dashboard** with real-time progress via Server-Sent Events
- **REST API** (~62 endpoints) for programmatic access
- **Download playlists** from Apple Music using gamdl
- **Convert to MP3** with configurable quality presets (lossless, high, medium, low)
- **Multi-threaded conversion** with configurable parallel workers
- **DB-centric metadata** — track info stored in SQLite, MP3s carry only a UUID tag
- **Profile-based tagging** — TagApplicator applies ID3 tags on-the-fly during sync/download
- **Sync destinations** with USB auto-detection, saved destinations, and custom paths
- **Pipeline orchestration** for automated download → convert workflows
- **Automatic cookie management** with browser-based refresh and validation
- **iOS companion app** (SwiftUI, iOS 17+) with Bonjour discovery
- **Desktop sync client** (TypeScript, CLI + Electron GUI)
- **Comprehensive audit trail** and task history
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
  - Or download from: <https://ffmpeg.org/download.html> (extract and add to PATH)
- Activate venv: `.venv\Scripts\activate`

## Quick Start

### Prerequisites

- Python 3.8+
- ffmpeg (system binary)
- Valid Apple Music subscription and cookies.txt file

### Installation

```bash
# Clone repository
cd music-porter

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Start the Server

```bash
# Start server (opens web dashboard at http://localhost:5555)
./music-porter

# With options
./music-porter server --port 8080
./music-porter server --show-api-key
./music-porter --version
```

Open your browser to `http://localhost:5555` to access the web dashboard. All operations (pipeline, conversion, sync, settings) are managed from there.

## Quality Presets

MP3 conversion supports configurable quality presets to balance file size and audio quality:

| Preset | Mode | Value | Est. Bitrate | Use Case |
|--------|------|-------|--------------|----------|
| `lossless` | CBR | 320kbps | 320kbps | **Default** - Maximum quality, no compromises |
| `high` | VBR | 2 | ~190-250kbps | High quality, smaller files |
| `medium` | VBR | 4 | ~165-210kbps | Balanced quality and size |
| `low` | VBR | 6 | ~115-150kbps | Space-constrained devices |

Quality is configured in the web dashboard Settings page or in `data/config.yaml`.

## Architecture

### Library Storage Model

Library MP3s are stored with UUID-based filenames and carry only a `TXXX:TrackUUID` identifier tag. All human-readable metadata (title, artist, album) lives in a SQLite database (`tracks` table). This DB-centric approach enables:

- **Profile-based tagging** — TagApplicator applies ID3 tags on-the-fly during sync/download
- **Template-based output** — filenames and tags are formatted per-profile (e.g., `{artist} - {title}`)
- **Clean library** — source MP3s are never modified after conversion

### Output Profiles

Profiles control how tags and filenames are applied when files leave the library:

| Profile | ID3 | Artwork | Album Tag | Artist Tag |
|---------|-----|---------|-----------|------------|
| `ride-command` (default) | v2.3 | 100px | playlist name | "Various" |
| `basic` | v2.4 | original | original | original |

Profiles are fully customizable in `data/config.yaml` under `output_types`.

## Documentation

- **[User Guide](MUSIC-PORTER-GUIDE.md)** - Complete usage guide with examples
- **[Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md)** - Cookie validation, auto-refresh, and troubleshooting
- **[iOS Companion Guide](IOS-COMPANION-GUIDE.md)** - iOS app setup, pairing, and usage
- **[Architecture](CLAUDE.md)** - Developer guide and AI assistant context

## Configuration

### config.yaml Format

Configuration is stored in `data/config.yaml` (auto-created on first run):

```yaml
schema_version: 2

settings:
  output_type: ride-command
  workers: 6
  quality_preset: lossless
  server_name: Music Porter

playlists:
  - key: Pop_Workout
    url: https://music.apple.com/us/playlist/...
    name: Pop Workout

destinations:
  - name: nas-backup
    path: folder:///Volumes/NAS/Music
```

### Apple Music Authentication

Requires `data/cookies.txt` file with valid Apple Music session cookies. The server validates cookies at startup and before download operations.

**Cookie Refresh:**
- Use the web dashboard Settings page to refresh cookies
- Or manually export cookies from music.apple.com using a browser extension

See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md) for detailed instructions.

## Project Structure

```text
.
├── music-porter                # Server entry point
├── porter_core.py              # Business logic
├── web_ui.py                   # Flask app, page routes
├── web_api.py                  # REST API blueprint
├── data/
│   ├── config.yaml             # Playlists and settings
│   ├── cookies.txt             # Apple Music authentication
│   └── music-porter.db         # SQLite (tracks, audit, tasks, sync)
├── library/                    # All music data (source + output)
│   └── Pop_Workout/
│       ├── source/             # Downloaded M4A files (Artist/Album/Track.m4a)
│       ├── output/
│       │   └── <uuid>.mp3      # Clean MP3 with TrackUUID tag only
│       └── artwork/
│           └── <uuid>.jpg      # Extracted cover art
├── templates/                  # Jinja2 HTML templates
├── ios/                        # iOS companion app (SwiftUI)
├── sync-client/                # Desktop sync client (TypeScript)
└── logs/                       # Execution logs
```

## Companion Apps

### iOS Companion App

Native SwiftUI app (iOS 17+) for managing Music Porter from your phone. Features Bonjour discovery, playlist management, pipeline operations, audio playback, and USB export.

### Desktop Sync Client

Cross-platform sync client (`sync-client/` subdirectory) with both a CLI tool (`mporter-sync`) and an Electron desktop app. Syncs playlists to USB drives or local folders with profile-specific tags.

## Troubleshooting

**Cookies expired / Downloads fail**
- Use the web dashboard to refresh cookies
- See [Cookie Management Guide](COOKIE-MANAGEMENT-GUIDE.md)

**FFmpeg not found**
- Install: `brew install ffmpeg` (macOS) or equivalent for your platform

**USB drive not detected**
- Ensure drive is mounted
- System drives are automatically excluded

**Virtual environment issues**
- Activate: `source .venv/bin/activate`
- Reinstall: `pip install -r requirements.txt`

## Future Features

### High Priority

1. **Playlist sync detection** - Compare local library to Apple Music, download only new/changed tracks
2. **Incremental updates** - Smart detection of changed tracks without full re-download
3. ~~**Multi-threaded conversion** - Parallel processing for faster batch conversions~~ *(implemented in v1.3.0)*
4. **Batch tag operations** - Apply tag changes to multiple playlists at once
5. ~~**Configuration presets** - Save and load common conversion/tagging configurations~~ *(implemented in v1.8.0)*

### Medium Priority

1. ~~**Web UI** - Browser-based interface for remote management~~ *(implemented in v2.0.0)*
2. **Automatic USB detection** - Start sync when USB drive is plugged in
3. ~~**Progress indicators** - Real-time progress bars for long-running operations~~ *(implemented in v1.4.0)*
4. **Download resume** - Resume interrupted downloads
5. ~~**Cover art management** - Embed, extract, and update album artwork~~ *(implemented in v1.5.0)*
6. **Playlist merging** - Combine multiple playlists into one
7. **Smart playlists** - Auto-generate playlists based on criteria (genre, artist, etc.)
8. ~~**Duplicate detection** - Find and remove duplicate tracks across playlists~~ *(implemented in v2.16.0)*
9. **Tag validation** - Verify tag integrity and fix common issues
10. **Export formats** - Support for additional formats (FLAC, AAC, OGG)
11. **Cover art resize on embed/convert** - Add `--cover-art-size` flag to `embed`, `update`, `convert`, and `pipeline` commands for automatic resizing during processing
12. **Lock screen artwork** - Load album artwork image into MPNowPlayingInfoCenter for lock screen and Control Center display during iOS playback
13. **Web file browser** - File-level browsing page with per-file USB sync indicators showing which drives each track has been synced to
14. **Sync key owns paths** - Restructure config so sync keys are first-class entities that own multiple destination paths, replacing the current destination-links-to-key model with a more intuitive key-centric architecture

### Low Priority / Nice to Have

1. **Spotify integration** - Download from Spotify playlists
2. **YouTube Music integration** - Download from YouTube Music playlists
3. **Metadata enrichment** - Fetch additional metadata from online databases
4. **Lyrics embedding** - Download and embed synchronized lyrics
5. **BPM detection** - Analyze and tag tracks with BPM information
6. **Playlist statistics** - Detailed analytics (genre distribution, duration, etc.)
7. **Tag history** - Track changes to tags over time
8. **Backup and restore** - Backup entire library with metadata
9. ~~**Cloud storage sync** - Sync to Dropbox, Google Drive, etc.~~ *(partially addressed in v2.26.0 — sync destinations support any mounted path including NAS/network shares)*
10. ~~**Mobile app** - iOS/Android app for remote control~~ *(implemented in v2.9.0)*
11. **Scheduling** - Automatic periodic syncing on schedule
12. **Notification system** - Email/SMS alerts for completed operations
13. ~~**Custom filename templates** - Configurable output filename patterns~~ *(implemented in v2.3.0)*
14. ~~**Equalizer presets** - Apply audio processing (normalization, compression)~~ *(implemented in v2.32.0)*
15. **Collaborative playlists** - Share playlists with others for collaborative management
16. ~~**Additional output type profiles** - Add device-specific profiles beyond Ride Command (e.g., generic car stereo, nested directory structures, alternative filename formats)~~ *(implemented in v1.7.0)*

## Version

Current version: **v2.36.1**

## License

See project license file for details.

## Contributing

This is a personal project, but suggestions and improvements are welcome via GitHub issues.
