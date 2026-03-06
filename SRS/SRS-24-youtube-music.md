# SRS-24: YouTube Music Integration

## Overview

Users want to download playlists from YouTube Music in addition to Apple Music. The system
currently only supports Apple Music via gamdl. YouTube Music integration adds yt-dlp as a
second downloader, routes pipeline operations to the correct downloader based on playlist
source type, and surfaces source type in the UI.

## Requirements

### 24.1 YouTube Music Download

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 24.1.1 | [ ] | N/A | N/A | [ ] | As a user, I can add a YouTube Music playlist URL so that my YouTube Music playlists are downloaded and converted alongside Apple Music playlists. Acceptance: a `music.youtube.com` playlist URL is accepted; the playlist is stored with source_type `youtube_music`; the downloader uses yt-dlp. |
| 24.1.2 | [ ] | N/A | N/A | N/A | As a user, I can run the pipeline on a YouTube Music playlist so that tracks are downloaded, converted to MP3, and synced using the same workflow as Apple Music. Acceptance: pipeline routes to yt-dlp downloader; M4A files appear in `library/source/ytdlp/<key>/`; Converter processes them normally. |
| 24.1.3 | [ ] | N/A | N/A | N/A | As a user, I can see real-time download progress for YouTube Music playlists so that I know how the download is proceeding. Acceptance: yt-dlp stdout is parsed for progress; log lines stream to the web UI via SSE. |
| 24.1.4 | [ ] | N/A | N/A | N/A | As a user, downloaded YouTube Music tracks carry standard metadata (title, artist, album, year, track number, cover art) so that the library and sync output are correctly tagged. Acceptance: yt-dlp is invoked with `--embed-metadata --embed-thumbnail`; Converter reads tags via mutagen; TrackDB is populated. |
| 24.1.5 | [ ] | N/A | N/A | N/A | As a user, tracks already downloaded from a YouTube Music playlist are skipped on re-run so that repeated pipeline runs are fast. Acceptance: Converter's existing source_m4a_path duplicate detection handles skips; no re-download of existing M4A files. |

### 24.2 Playlist Management

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 24.2.1 | [ ] | N/A | N/A | [ ] | As a user, when I add a playlist URL, the source type is detected automatically from the URL so that I don't need to specify it manually. Acceptance: `music.apple.com` → `apple_music`; `music.youtube.com` → `youtube_music`; unknown URLs are rejected with a clear error. |
| 24.2.2 | [ ] | N/A | N/A | [ ] | As a user, I can see the source type (Apple Music or YouTube Music) on each playlist card so that I can distinguish between sources. Acceptance: playlist list API returns `source_type`; web UI shows a badge; iOS shows a label. |
| 24.2.3 | [ ] | N/A | N/A | N/A | As a user, I can delete a YouTube Music playlist and its data using the same delete-data flow as Apple Music so that cleanup is consistent. Acceptance: delete-data removes `library/source/ytdlp/<key>/` and associated MP3s/artwork. |

### 24.3 Authentication

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 24.3.1 | [ ] | N/A | N/A | N/A | As a user, I can provide a YouTube Music cookies file so that yt-dlp can download premium-quality audio and private playlists. Acceptance: when `data/yt-cookies.txt` is present, yt-dlp is invoked with `--cookies data/yt-cookies.txt`; cookie presence is shown in the Settings page. |
| 24.3.2 | [ ] | N/A | N/A | N/A | As a user, I can see whether YouTube Music cookies are present in the Settings page so that I know whether premium downloads are enabled. Acceptance: Settings page shows a YouTube Music cookie status card with "present" or "missing" state. |

### 24.4 Dependency

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 24.4.1 | [ ] | N/A | N/A | N/A | As a user, if yt-dlp is not installed, I see a clear error message when attempting to download a YouTube Music playlist so that I know what to install. Acceptance: DependencyChecker includes yt-dlp; missing yt-dlp produces a user-readable error before download starts. |

### 24.5 Edge Cases

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 24.5.1 | [ ] | N/A | N/A | N/A | If a YouTube Music playlist is private or unavailable, the download fails gracefully with a descriptive error logged to the audit trail. Acceptance: yt-dlp non-zero exit code is caught; error is logged; pipeline reports failure without crashing. |
| 24.5.2 | [ ] | N/A | N/A | N/A | If yt-dlp produces a non-M4A audio format (e.g., webm), the system converts it to M4A so that the Converter can process it. Acceptance: yt-dlp is invoked with `--extract-audio --audio-format m4a`; only `.m4a` files appear in the source directory. |
| 24.5.3 | [ ] | N/A | N/A | N/A | Tracks with missing metadata fields (e.g., no album, no track number) from YouTube Music are stored with sensible defaults so that the library remains consistent. Acceptance: Converter falls back to "Unknown Album", empty strings, or None for missing fields — same as Apple Music fallback behavior. |
