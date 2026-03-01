# SRS 22: Sync Functionality

**Version:** 1.0  |  **Date:** 2026-03-01  |  **Status:** Draft

---

## 22.1 Sync Operation

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.1.1 | 1.0 | [ ] | As a user, I can sync all playlists to a selected destination so that my entire library is available at the target location. Acceptance: all playlists in the library are processed; files are copied to the destination path. |
| 22.1.2 | 1.0 | [ ] | As a user, I can sync a specific playlist to a selected destination so that only the tracks I want are copied. Acceptance: only files belonging to the chosen playlist are synced; other playlists are unaffected. |
| 22.1.3 | 1.0 | [ ] | As a user, I can expect that files are tagged according to the selected output profile during sync so that the destination files have the correct metadata without modifying my library. Acceptance: destination files have profile-specific ID3 tags, artwork, and filenames; library MP3s remain unchanged. |
| 22.1.4 | 1.0 | [ ] | As a user, I can expect that only new or changed files are copied during sync (incremental sync) so that repeated syncs are fast. Acceptance: files already present and unchanged at the destination are skipped; only new or modified files are transferred. |
| 22.1.5 | 1.0 | [ ] | As a user, I can see real-time progress during a sync operation so that I know how far along the process is. Acceptance: progress updates (file count, percentage) are displayed in real time via the web dashboard or client interface. |
| 22.1.6 | 1.0 | [ ] | As a user, I can perform a dry run to preview what would be synced without actually copying any files. Acceptance: the system reports which files would be copied, skipped, or updated, but no files are written to the destination. |
| 22.1.7 | 1.0 | [ ] | As a user, I can see a summary of results after a sync completes so that I know what happened. Acceptance: summary includes counts for files copied, skipped, and failed, along with the total duration. |
| 22.1.8 | 1.0 | [ ] | As a user, I can cancel a sync operation in progress so that I can stop it if needed. Acceptance: cancellation stops the sync promptly; files already copied remain at the destination; no partial files are left behind. |

---

## 22.2 Saved Destinations

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.2.1 | 1.0 | [ ] | As a user, I can add a named destination with a folder path so that I can reuse it for future syncs. Acceptance: the destination is saved persistently in configuration with its name and path; it appears in the destination list on subsequent sessions. |
| 22.2.2 | 1.0 | [ ] | As a user, I can remove a saved destination so that outdated or unwanted entries are cleaned up. Acceptance: the destination is deleted from configuration; its sync tracking data (sync key) is not deleted unless explicitly requested. |
| 22.2.3 | 1.0 | [ ] | As a user, I can rename a saved destination so that I can update its display name. Acceptance: the destination name changes everywhere it appears; its path, sync key association, and tracking data remain intact. |
| 22.2.4 | 1.0 | [ ] | As a user, I can view all saved destinations with their type, path, and availability so that I can choose where to sync. Acceptance: each destination shows its name, type (USB, folder, or browser client), path, and whether the path currently exists or is connected. |
| 22.2.5 | 1.0 | [ ] | As a user, I can see three destination types — USB drive, folder, and browser client — so that I can sync to different kinds of targets. Acceptance: USB destinations use a `usb://` scheme, folder destinations use a `folder://` scheme, and browser client destinations are identified by their client type. |

---

## 22.3 USB Drive Detection

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.3.1 | 1.0 | [ ] | As a user, I can see connected USB drives automatically appear as available sync destinations so that I don't have to manually enter paths. Acceptance: when a USB drive is connected, it appears in the destination list without user action. |
| 22.3.2 | 1.0 | [ ] | As a user, I can expect that system volumes (e.g., boot drives) are excluded from the USB destination list so that I don't accidentally sync to the wrong drive. Acceptance: on macOS, "Macintosh HD" and "Macintosh HD - Data" are excluded; on Windows, "C:" is excluded; on Linux, "boot" and "root" are excluded. |
| 22.3.3 | 1.0 | [ ] | As a user, I can expect USB drive detection to work on macOS, Linux, and Windows so that the feature is available regardless of my platform. Acceptance: macOS scans `/Volumes/`, Linux scans `/media/$USER/` and `/mnt/`, Windows scans drive letters. |
| 22.3.4 | 1.0 | [ ] | As a user, I can eject a USB drive after sync completes so that I can safely remove it. Acceptance: on macOS and Linux, the drive is ejected automatically or on request; on Windows, the user is informed to eject manually. |

---

## 22.4 Sync Keys

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.4.1 | 1.0 | [ ] | As a user, I can expect each destination to have a tracking key that records which files have been synced so that incremental sync works correctly. Acceptance: a sync key is created or associated when a destination is first synced; subsequent syncs reference this key to determine what is new. |
| 22.4.2 | 1.0 | [ ] | As a user, I can view all sync keys with their total synced file counts so that I can see the tracking state. Acceptance: a list of all sync keys is shown, each with the number of files recorded as synced. |
| 22.4.3 | 1.0 | [ ] | As a user, I can delete a sync key and all its tracking data so that I can reset sync state for a destination. Acceptance: the sync key and all associated file records are removed from the database; files at the destination are not affected. |
| 22.4.4 | 1.0 | [ ] | As a user, I can remove tracking for a specific playlist from a sync key so that only that playlist is re-synced next time. Acceptance: file records for the specified playlist are deleted from the sync key; records for other playlists remain. |
| 22.4.5 | 1.0 | [ ] | As a user, I can prune stale records from a sync key so that tracking data stays accurate when files are removed from the library. Acceptance: file records that reference tracks no longer in the library are removed; valid records remain. |
| 22.4.6 | 1.0 | [ ] | As a user, I can rename a sync key so that its name reflects its current purpose. Acceptance: the sync key name changes in the database; all destination references and file records update automatically. |

---

## 22.5 Destination Linking

Sync keys track which files have been synced to a physical device. Some devices (e.g., USB drives on macOS/Linux/Windows) are detected directly, but others (e.g., a USB drive connected via an iOS device) appear only as a folder path. Destination linking allows a folder destination to share a sync key with a USB destination so that the system knows they refer to the same physical device and tracks them together.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.5.1 | 1.0 | [ ] | As a user, when I sync to a new folder destination for the first time, I am prompted to either create a new sync key or associate this destination with an existing sync key so that I can indicate whether this folder is a new device or the same device already tracked under another name. Acceptance: a prompt appears with two choices — "Create new sync key" or "Use existing sync key"; if I choose existing, I see a list of all available sync keys to select from. |
| 22.5.2 | 1.0 | [ ] | As a user, I can link a destination to an existing sync key so that multiple destinations (e.g., a USB drive and a folder path on the same physical device) share the same tracking data. Acceptance: the destination is associated with the specified sync key; syncing to this destination uses the shared key's records. |
| 22.5.3 | 1.0 | [ ] | As a user, I can unlink a destination from a shared sync key so that it gets its own independent tracking. Acceptance: the destination is disassociated from the shared key; a new independent sync key is created or the destination has no key until next sync. |
| 22.5.4 | 1.0 | [ ] | As a user, I can expect that when linking, existing tracking data merges automatically so that no sync history is lost. Acceptance: if the destination already had its own sync records, those records are combined with the shared key's records. |
| 22.5.5 | 1.0 | [ ] | As a user, I can expect that shared tracking means syncing to one linked destination updates the sync status for all destinations sharing that key. Acceptance: after syncing to destination A (USB drive) and then syncing to destination B (folder on the same device), the files synced via A are recognized and skipped. |

---

## 22.6 Sync Status

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.6.1 | 1.0 | [ ] | As a user, I can view a summary across all sync keys showing total files, synced files, and new files so that I can see overall sync health. Acceptance: a summary table or card displays aggregate counts across all tracked sync keys. |
| 22.6.2 | 1.0 | [ ] | As a user, I can view a per-playlist breakdown for a specific sync key so that I can see detailed sync status. Acceptance: for a given sync key, each playlist shows its total file count, synced count, and new (unsynced) count. |
| 22.6.3 | 1.0 | [ ] | As a user, I can see which playlists have never been synced to a given key so that I know what's missing. Acceptance: playlists with zero synced files for the selected key are clearly identified. |
| 22.6.4 | 1.0 | [ ] | As a user, I can see how many new (unsynced) files exist per playlist for a given key so that I can prioritize what to sync. Acceptance: each playlist shows the count of files not yet recorded in the sync key. |
| 22.6.5 | 1.0 | [ ] | As a user, I can view which sync keys have received each individual file so that I can trace where a specific track has been synced. Acceptance: for a given file, a list of sync keys that include it is displayed. |

---

## 22.7 Browser-Based Sync

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.7.1 | 1.0 | [ ] | As a user, I can sync files directly to a local folder from the web browser (in Chromium-based browsers) so that I can download music without a separate client. Acceptance: using the File System Access API, the user selects a local folder and files are written directly to it. |
| 22.7.2 | 1.0 | [ ] | As a user, I can select which playlists to include in a browser sync so that I only download what I need. Acceptance: a playlist selection interface is presented before sync begins; only selected playlists are processed. |
| 22.7.3 | 1.0 | [ ] | As a user, I can see a progress bar with percentage and file counts during browser sync so that I can track the download. Acceptance: a progress indicator updates in real time showing completed files, total files, and percentage. |
| 22.7.4 | 1.0 | [ ] | As a user, I can expect that previously synced files are skipped during browser sync (incremental) so that repeated syncs are fast. Acceptance: files already present in the local manifest are skipped; only new or changed files are downloaded. |
| 22.7.5 | 1.0 | [ ] | As a user, I can cancel a browser sync in progress so that I can stop the download if needed. Acceptance: cancellation stops the sync promptly; files already written remain; no partial files are left. |
| 22.7.6 | 1.0 | [ ] | As a user, I can download playlists as ZIP archives in non-Chromium browsers so that I have a fallback when the File System Access API is unavailable. Acceptance: a download button produces a ZIP file containing the tagged MP3s with human-readable filenames. |
| 22.7.7 | 1.0 | [ ] | As a user, I can download a single playlist as a ZIP or multiple playlists as a combined ZIP so that I can get exactly what I need in one download. Acceptance: single-playlist ZIP contains that playlist's files; multi-playlist ZIP contains all selected playlists' files organized by playlist. |
| 22.7.8 | 1.0 | [ ] | As a user, I can expect that browser sync activity is recorded for tracking purposes just like server sync so that my sync history is consistent. Acceptance: files synced via the browser are recorded under a sync key associated with the browser client destination. |

---

## 22.8 GUI Sync (Desktop Sync Client)

### Server Connection & Offline Support

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.1 | 1.0 | [ ] | As a user, I can discover servers automatically on the local network so that I don't have to manually configure a connection. Acceptance: the client uses mDNS/Bonjour to find running music-porter servers and presents them for selection. |
| 22.8.2 | 1.0 | [ ] | As a user, I can enter a server URL and API key manually so that I can connect to servers not on the local network. Acceptance: the client accepts a URL and API key, validates the connection, and saves the configuration. |
| 22.8.3 | 1.0 | [ ] | As a user, I can connect via local network or external URL, with the client trying local first and falling back to external so that the fastest connection is used automatically. Acceptance: the client attempts the local address first; if unreachable, it connects via the external URL without user intervention. |
| 22.8.4 | 1.0 | [ ] | As a user, I can continue working offline using locally cached files when the server is unavailable so that I can still sync from cache. Acceptance: when the server is unreachable, the client operates in offline mode using cached metadata and audio files. |
| 22.8.5 | 1.0 | [ ] | As a user, I can reconnect, disconnect, or go offline from settings so that I have control over the connection state. Acceptance: settings provide explicit actions to reconnect to the server, disconnect cleanly, or switch to offline mode. |

### Playlist Selection & Caching

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.6 | 1.0 | [ ] | As a user, I can view all server playlists with file counts, sizes, and freshness status so that I can see what's available. Acceptance: each playlist shows its track count, total size, and whether it has new content since the last sync. |
| 22.8.7 | 1.0 | [ ] | As a user, I can select individual playlists or all playlists for sync so that I can control what gets synced. Acceptance: checkboxes or a select-all option allow choosing which playlists to include in the next sync operation. |
| 22.8.8 | 1.0 | [ ] | As a user, I can pin playlists for offline caching so that they are available without a server connection. Acceptance: pinned playlists are downloaded to the local cache and remain available when offline. |
| 22.8.9 | 1.0 | [ ] | As a user, I can enable auto-pin so that new playlists are automatically pinned as they appear on the server. Acceptance: when auto-pin is enabled, any playlist added to the server is automatically marked as pinned and cached. |
| 22.8.10 | 1.0 | [ ] | As a user, I can view per-playlist cache status (fully cached, partially cached, not cached) so that I know what's available offline. Acceptance: each playlist displays its cache state with a visual indicator (e.g., icon or label). |
| 22.8.11 | 1.0 | [ ] | As a user, I can expect background prefetch to automatically cache pinned playlists during idle time so that they are ready when I need them. Acceptance: when the client is idle and connected to the server, pinned playlists are downloaded in the background without user action. |
| 22.8.12 | 1.0 | [ ] | As a user, I can manage cache by setting a maximum cache size, clearing individual playlists, or clearing all cached files so that I can control disk usage. Acceptance: cache settings allow setting a size limit; clearing a playlist removes its cached files; clearing all removes the entire cache. |

### Destination Selection

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.13 | 1.0 | [ ] | As a user, I can see connected USB drives auto-detected with free space shown so that I can choose where to sync. Acceptance: USB drives appear in the destination list with their name and available free space displayed. |
| 22.8.14 | 1.0 | [ ] | As a user, I can browse for a local folder as a sync destination so that I can sync to any directory on my computer. Acceptance: a folder picker dialog allows selecting any local directory as the sync target. |
| 22.8.15 | 1.0 | [ ] | As a user, I can select from recently used destinations via a dropdown so that I can quickly pick familiar targets. Acceptance: a dropdown lists previously used destinations; selecting one sets it as the active destination. |
| 22.8.16 | 1.0 | [ ] | As a user, I can expect that when a USB drive is selected, files sync to the output profile's configured USB directory within the drive so that files are organized consistently. Acceptance: files are placed in the subdirectory specified by the profile's `usb_dir` setting on the selected drive. |

### Sync Execution

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.17 | 1.0 | [ ] | As a user, I can start a sync to copy new or changed files to the destination so that my music is up to date. Acceptance: pressing the sync button begins transferring files; only new or changed files are copied. |
| 22.8.18 | 1.0 | [ ] | As a user, I can force a re-sync to re-download all files regardless of sync status so that I can refresh everything. Acceptance: a force re-sync option ignores the local sync manifest and re-downloads all files from the server. |
| 22.8.19 | 1.0 | [ ] | As a user, I can see a real-time progress bar with file count, percentage, and current filename during sync so that I know what's happening. Acceptance: the progress display updates continuously showing files completed out of total, percentage, and the name of the file currently being transferred. |
| 22.8.20 | 1.0 | [ ] | As a user, I can see live counters for copied, skipped, and failed files during sync so that I can monitor the operation. Acceptance: counters update in real time as each file is processed. |
| 22.8.21 | 1.0 | [ ] | As a user, I can cancel a sync in progress so that I can stop the operation if needed. Acceptance: cancellation stops the sync promptly; files already copied remain; no partial files are left. |
| 22.8.22 | 1.0 | [ ] | As a user, I can see a summary after sync showing copied, skipped, and failed counts along with the total duration so that I know the outcome. Acceptance: a summary screen or notification displays the final statistics after sync completes or is cancelled. |

### USB Drive Features

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.23 | 1.0 | [ ] | As a user, I can eject USB drives safely from within the desktop sync client so that I can remove them without data loss. Acceptance: an eject button is available for connected USB drives; the drive is unmounted safely before removal. |
| 22.8.24 | 1.0 | [ ] | As a user, I can toggle auto-eject so that USB drives are ejected automatically after sync completes. Acceptance: when auto-eject is enabled, the USB drive is ejected immediately after a successful sync without user action. |
| 22.8.25 | 1.0 | [ ] | As a user, I can configure auto-sync for specific USB drives so that syncing starts automatically when I plug them in. Acceptance: the client remembers which USB drives have auto-sync enabled; when one of those drives is connected, sync begins automatically. |

### Output Profile & Settings

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.8.26 | 1.0 | [ ] | As a user, I can select an output profile in the desktop sync client that controls file naming, tags, and artwork so that synced files match my preferences. Acceptance: a profile selector lists available profiles from the server; the selected profile is applied during sync. |
| 22.8.27 | 1.0 | [ ] | As a user, I can adjust parallel download concurrency (1–8 concurrent downloads) so that I can balance speed and system load. Acceptance: a concurrency setting allows choosing between 1 and 8 simultaneous downloads; the setting is saved for future sessions. |
| 22.8.28 | 1.0 | [ ] | As a user, I can view the server version and release notes from the desktop sync client so that I know what version I'm connected to. Acceptance: the client displays the connected server's version number and its release notes. |

---

## 22.9 Output Profiles in Sync

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.9.1 | 1.0 | [ ] | As a user, I can select an output profile before syncing so that I control how files are tagged and named at the destination. Acceptance: a profile selection option is available before starting a sync; the chosen profile is applied to all files during that sync. |
| 22.9.2 | 1.0 | [ ] | As a user, I can expect the profile to control file naming, directory structure, ID3 tags, and artwork for synced files so that the output matches my requirements. Acceptance: destination files use the profile's filename template, directory template, tag settings, and artwork size. |
| 22.9.3 | 1.0 | [ ] | As a user, I can compare available profiles side-by-side so that I can choose the right one for my use case. Acceptance: profile details (tag settings, filename format, artwork size) are viewable for comparison before selection. |
| 22.9.4 | 1.0 | [ ] | As a user, I can expect the profile to be applied on-the-fly during sync so that library files are never modified. Acceptance: the original library MP3s retain only their UUID tag; profile-specific tags and filenames are generated at sync time. |

---

## 22.10 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 22.10.1 | 1.0 | [ ] | As a user, if a destination becomes unavailable mid-sync (e.g., drive disconnected, folder deleted), the sync stops gracefully with an error message and files already copied remain intact. |
| 22.10.2 | 1.0 | [ ] | As a user, if multiple tracks produce the same filename at the destination, the system resolves the collision (e.g., by appending a number) so that no files are overwritten. |
| 22.10.3 | 1.0 | [ ] | As a user, if I sync when the library is empty, the system reports that there are no files to sync rather than failing silently or producing an error. |
| 22.10.4 | 1.0 | [ ] | As a user, if I cancel a sync mid-operation, files already copied to the destination remain intact and are not deleted. |
| 22.10.5 | 1.0 | [ ] | As a user, syncing a large library with thousands of files completes reliably without memory exhaustion or timeouts. |
| 22.10.6 | 1.0 | [ ] | As a user, if a USB drive is disconnected during sync, the system detects the loss and stops with a clear error rather than producing corrupted files. |
| 22.10.7 | 1.0 | [ ] | As a user, if I perform an offline sync from the desktop client when the cache is incomplete, only cached files are synced and the system reports which files were skipped due to missing cache. |
| 22.10.8 | 1.0 | [ ] | As a user, if the server becomes unreachable during a GUI sync, the client degrades gracefully by stopping new downloads and reporting the partial result. |
