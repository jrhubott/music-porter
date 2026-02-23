# iOS Companion App - User Guide

The Music Porter iOS companion app provides a mobile interface for managing your music library from your iPhone or iPad. It connects to the music-porter server over your local network, letting you browse playlists, trigger conversions, download MP3s, and export to USB drives.

## Requirements

- **iPhone or iPad** running iOS 17 or later
- **music-porter server** running on your Mac, Linux, or Windows machine
- Both devices on the **same local network** (Wi-Fi)
- Apple Developer account for building from source (TestFlight or direct install)

## Server Setup

Before using the iOS app, start the music-porter server on your computer. The `server` command enables authentication and network discovery, which the iOS app requires.

### Starting the Server

```bash
# Start server (recommended — enables auth + Bonjour discovery)
./music-porter server

# Custom port
./music-porter server --port 8080

# Show the full API key at startup (for copy/paste)
./music-porter server --show-api-key

# Disable Bonjour if discovery causes issues
./music-porter server --no-bonjour

# Disable authentication (not recommended)
./music-porter server --no-auth
```

### Server Startup Output

When the server starts, you'll see connection details in the terminal:

```text
  ── Music Porter API Server ──

  1. Connect to: http://192.168.1.100:5555
  2. API Key: AbCd...XyZ0 (use --show-api-key to display full key)
  3. Enter the API key in the iOS app when prompted
  4. Or scan the QR code below:

  ████████████████████████
  ██ ▄▄▄▄▄ ██▄▀█ ▄▄▄▄▄ ██
  ...

  Bonjour: advertising as _music-porter._tcp on 192.168.1.100:5555
```

The API key is generated once and saved to `config.yaml`. It persists across restarts.

### Server vs Web Command

| Feature | `./music-porter server` | `./music-porter web` |
|---------|------------------------|---------------------|
| Default host | `0.0.0.0` (network) | `127.0.0.1` (local only) |
| Authentication | Enabled (API key) | Disabled |
| Bonjour discovery | Enabled | Disabled |
| QR code pairing | Yes | No |
| iOS app support | Yes | No |
| Browser dashboard | Yes | Yes |

### Firewall Notes

If the iOS app cannot discover or connect to the server:

- **macOS:** Allow incoming connections for Python when prompted by the firewall dialog
- **Linux:** Open port 5555 (or your custom port) in iptables/ufw: `sudo ufw allow 5555/tcp`
- **Windows:** Allow Python through Windows Firewall when prompted

## Getting Started

### Discovering the Server

1. Launch the Music Porter app on your iOS device
2. The **Server Discovery** screen appears automatically
3. If the server is running with Bonjour enabled, it appears in the "Discovered Servers" list within a few seconds
4. Tap the server name to begin pairing

If the server doesn't appear automatically:

1. Scroll down to the **Manual Connection** section
2. Enter the server's IP address (shown in the server startup output)
3. Enter the port (default: 5555)
4. Tap **Connect**

Tip: Pull down or tap the refresh button in the toolbar to restart the Bonjour search.

### Pairing with API Key

After selecting a server, the **Pairing** screen appears:

1. Enter the API key displayed in the server's terminal output
2. Tap **Connect**
3. The app validates the key against the server
4. On success, you're taken to the main dashboard

The API key is stored securely in the iOS Keychain and the server address is saved for auto-reconnect. You won't need to enter it again unless you disconnect.

### QR Code Pairing

If the server terminal displays a QR code, you can scan it instead of typing the API key manually. The QR code contains the server address, port, and API key in a single scan.

### Auto-Reconnect

On subsequent launches, the app automatically reconnects to the last paired server using the saved credentials. This happens silently in the background with a 3-second timeout. If the server is unreachable, the app falls back to the discovery screen.

## Dashboard

The Dashboard is the first tab after connecting. It provides an overview of your server's status and library.

### Server Status Card

- **Version** — The music-porter version running on the server
- **Profile** — The active output profile (e.g., ride-command, basic)
- **Cookies** — Apple Music cookie status with a colored badge:
  - **Valid** (green) — Cookies are working, shows days until expiration
  - **Invalid** (red) — Cookies need refreshing on the server
- **Server Status** — Current activity:
  - **Idle** (green) — Ready for operations
  - **Busy** (orange) — An operation is in progress

### Library Statistics Card

- **Playlists** — Number of configured playlists
- **Files** — Total MP3 files across all playlists
- **Size** — Total library size in MB

### Playlist Overview

Below the cards, all playlists are listed with per-playlist file counts. Pull down to refresh the dashboard data.

## Managing Playlists

The **Playlists** tab lets you manage the playlists configured on the server.

### Viewing Playlists

Each playlist shows:

- Playlist display name
- Playlist key (directory name, shown in gray)
- Number of MP3 files on the server

Tap a playlist to view its tracks.

### Viewing Tracks

The track detail view shows all MP3 files in a playlist:

- **Album artwork** — Thumbnail loaded from the server (or a music note placeholder if no artwork)
- **Title** — Track title from ID3 tags
- **Artist** — Artist name
- **Size** — File size

Pull down to refresh the track list.

### Adding a Playlist

1. Tap the **+** button in the toolbar
2. Fill in:
   - **Key** — Short identifier used for directory names (e.g., `Pop_Workout`)
   - **URL** — Apple Music playlist URL
   - **Name** — Display name (e.g., "Pop Workout")
3. Tap **Add**

The playlist is added to the server's `config.yaml` and appears in the list.

### Deleting a Playlist

Swipe left on a playlist and tap **Delete**. This removes the playlist from the server configuration but does not delete downloaded or converted files.

## Running the Pipeline

The **Pipeline** tab lets you trigger the full download-convert-tag workflow on the server.

### Configuring a Pipeline Run

**Source Selection:**

- **Process all playlists** — Toggle on to run the pipeline for every configured playlist (auto mode)
- **Single playlist** — Select from the picker to process one playlist
- **Custom URL** — Enter an Apple Music URL directly

**Options:**

- **Quality Preset** — Choose conversion quality:
  - **Lossless** — 320kbps CBR (default, maximum quality)
  - **High** — VBR ~190-250kbps
  - **Medium** — VBR ~165-210kbps
  - **Low** — VBR ~115-150kbps
- **Copy to USB** — Toggle to sync files to USB after conversion

### Running the Pipeline

1. Configure your source and options
2. Tap **Run Pipeline**
3. The progress panel appears with:
   - A **progress bar** showing the current stage and percentage
   - A **log window** with real-time server output (color-coded by level)
4. When complete, a green checkmark confirms success (or a red X with error details)

The form is disabled while a pipeline is running. Only one server operation can run at a time.

### Real-Time Progress

Progress is streamed from the server via Server-Sent Events (SSE):

- **Stage names** — Shows which step is active (downloading, converting, tagging)
- **Log messages** — Color-coded: errors in red, warnings in orange, success in green, skipped in yellow
- **Progress percentage** — Updates as files are processed

## Browsing Apple Music

The **Apple Music** section (accessible from Settings) lets you browse your Apple Music library and send playlists directly to the server.

### Authorizing Apple Music

1. Navigate to **Settings > Apple Music**
2. Tap **Authorize Apple Music**
3. Grant access when prompted by iOS

Authorization is requested only when you explicitly tap the button, not at app launch.

### Browsing Your Library

After authorization, your Apple Music library playlists appear sorted by name. Each entry shows:

- Playlist name
- Description (if available)
- Send button (arrow icon)

### Searching the Catalog

Use the search bar to search the Apple Music catalog. Results are limited to 25 playlists and update as you type.

### Sending to Server

Tap the arrow button next to a playlist to send its URL to the server. This triggers the full pipeline (download, convert, tag) on the server, and you can monitor progress from the Pipeline tab.

Note: Due to DRM protection, MusicKit can browse playlists and metadata but cannot export audio files. All downloading and conversion happens on the server.

## Downloading Files

The **Downloads** tab lets you download converted MP3 files from the server to your iOS device.

### Downloading a Playlist

1. The Downloads tab shows all server playlists with file counts
2. If you've previously downloaded files, the local file count appears in green
3. Tap a playlist's download button to download all files as a ZIP
4. The ZIP is extracted to the device and individual MP3s are stored locally

### Local Storage

- Downloaded files are stored in `Documents/MusicPorter/<playlist>/` on your device
- The **Local Storage** section at the bottom shows total space used
- Files persist across app launches

### Managing Downloads

Pull down to refresh the playlist list and local file counts. Local storage usage updates automatically after downloads complete.

## USB Export

The **USB Export** section (accessible from Settings) lets you copy downloaded MP3s to a USB drive or external storage connected to your iOS device.

### Prerequisites

- Files must be downloaded to the device first (use the Downloads tab)
- A USB drive, SD card, or external storage must be connected to your iOS device
- Supported file systems: FAT, ExFAT, HFS+, APFS

### Exporting Files

1. Navigate to **Settings > USB Export**
2. Select playlists to export using the checkmark toggles
3. Tap **Export** (shows the count of selected playlists)
4. The iOS folder picker appears — navigate to your USB drive and select the destination folder
5. Files are copied with a progress bar
6. A result message confirms how many files were copied

### File System Access

iOS uses security-scoped URLs for accessing external storage. You'll need to grant folder access through the system document picker each time you export.

## Settings and Troubleshooting

### Settings Tab

The Settings tab provides:

- **Server** — Current host:port and server name, plus a Disconnect button
- **Profiles** — Available output profiles with descriptions
- **Operations** — View history of all background tasks (pipeline, convert, tag, etc.) with status badges
- **Apple Music** — Browse your Apple Music library (see above)
- **USB Export** — Export to external storage (see above)
- **About** — App version

### Disconnecting

Tap the red **Disconnect** button in Settings to:

- Clear the server connection
- Remove the API key from Keychain
- Return to the Server Discovery screen

You'll need to re-pair with the server to reconnect.

### Common Issues

**Server not discovered via Bonjour:**

- Ensure both devices are on the same Wi-Fi network
- Check that the server was started with `./music-porter server` (not `web`)
- Try `--no-bonjour` on the server and use manual connection instead
- Check firewall settings on the server machine
- Tap the refresh button to restart discovery

**Connection refused or timeout:**

- Verify the server is running (`./music-porter server`)
- Check the IP address matches (shown in server startup output)
- Ensure port 5555 is not blocked by a firewall
- Try manual connection if Bonjour fails

**"Unauthorized" error:**

- Double-check the API key matches the one shown in the server terminal
- Use `--show-api-key` flag on the server to display the full key
- If the key was regenerated, disconnect and re-pair from the app

**"Server Busy" (HTTP 409):**

- Only one operation can run at a time on the server
- Wait for the current operation to complete, then try again
- Check the Operations screen to see what's running

**Pipeline fails or shows errors:**

- Check the server terminal for detailed error output
- Verify Apple Music cookies are valid (Dashboard shows cookie status)
- Refresh cookies on the server if expired: `./music-porter server` and use the web dashboard's Settings page

**Downloads stuck or failing:**

- Check network connectivity between your device and server
- Ensure the server is still running
- Large playlists may take time to download as ZIP; be patient

**Apple Music playlists not loading:**

- Ensure you've authorized Apple Music access in the app
- Check that you have an active Apple Music subscription
- MusicKit requires network access to fetch library data

**USB export folder picker doesn't show drive:**

- Ensure the USB drive is properly connected and recognized by iOS
- Try the Files app to verify the drive appears
- Some USB drives may need a powered hub for iPad connectivity
