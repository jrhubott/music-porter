# SRS 22: Sync Functionality

**Version:** 2.0  |  **Date:** 2026-03-01  |  **Status:** Draft

---

## 22.1 Sync Operation

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.1.1 | [x] | [x] | [x] | [ ] | As a user, I can sync all playlists to a selected destination so that my entire library is available at the target location. Acceptance: all playlists in the library are processed; files are copied to the destination path. |
| 22.1.2 | [x] | [x] | [x] | [ ] | As a user, I can sync a specific playlist to a selected destination so that only the tracks I want are copied. Acceptance: only files belonging to the chosen playlist are synced; other playlists are unaffected. |
| 22.1.3 | [x] | [x] | [x] | [ ] | As a user, I can expect that files are tagged according to the selected output profile during sync so that the destination files have the correct metadata without modifying my library. Acceptance: destination files have profile-specific ID3 tags, artwork, and filenames; library MP3s remain unchanged. |
| 22.1.4 | [x] | [x] | [x] | [ ] | As a user, I can expect that only new or changed files are copied during sync (incremental sync) so that repeated syncs are fast. Acceptance: files already present and unchanged at the destination are skipped; only new or modified files are transferred. |
| 22.1.5 | [x] | [x] | [x] | [ ] | As a user, I can see real-time progress during a sync operation so that I know how far along the process is. Acceptance: progress updates (file count, percentage) are displayed in real time via the web dashboard or client interface. |
| 22.1.6 | [ ] | [x] | N/A | [ ] | As a user, I can perform a dry run to preview what would be synced without actually copying any files. Acceptance: the system reports which files would be copied, skipped, or updated, but no files are written to the destination. |
| 22.1.7 | [x] | [x] | [x] | [ ] | As a user, I can see a summary of results after a sync completes so that I know what happened. Acceptance: summary includes counts for files copied, skipped, and failed, along with the total duration. |
| 22.1.8 | [x] | [x] | [x] | [ ] | As a user, I can cancel a sync operation in progress so that I can stop it if needed. Acceptance: cancellation stops the sync promptly; files already copied remain at the destination; no partial files are left behind. |

---

## 22.2 Saved Destinations

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.2.1 | [x] | N/A | N/A | [ ] | As a user, I can add a named destination with a folder path so that I can reuse it for future syncs. Acceptance: the destination is saved persistently with its name and path; it appears in the destination list on subsequent sessions. |
| 22.2.2 | [ ] | [ ] | [ ] | [ ] | As a user, I can remove a saved destination so that outdated or unwanted entries are cleaned up. Acceptance: the destination entry is deleted; if other destinations share the same tracking group, tracking data is preserved for the remaining destinations; if this is the last destination in the group, tracking data is also cleaned up. |
| 22.2.3 | [x] | N/A | N/A | [ ] | As a user, I can rename a saved destination so that I can update its display name. Acceptance: the destination name changes everywhere it appears; its path, group associations, and tracking data remain intact. |
| 22.2.4 | [ ] | [ ] | [ ] | [ ] | As a user, I can view all saved destinations with their type, path, availability, and group membership so that I can choose where to sync. Acceptance: each destination shows its name, type (USB, folder, or browser client), path, whether the path currently exists or is connected, and which other destinations it is linked with. |
| 22.2.5 | [x] | [x] | [x] | [ ] | As a user, I can see three destination types — USB drive, folder, and browser client — so that I can sync to different kinds of targets. Acceptance: USB destinations use a `usb://` scheme, folder destinations use a `folder://` scheme, and browser client destinations are identified by their client type. |
| 22.2.6 | [ ] | [ ] | [ ] | [ ] | As a user, when I sync to a new destination for the first time, I am prompted to choose whether this is a new sync location or should share tracking with an existing destination so that I can avoid re-syncing files that have already been synced elsewhere. Acceptance: a prompt appears with two choices — "New sync location" or "Share tracking with existing destination"; if the user chooses to share, they select an existing destination from a list. |
| 22.2.7 | [ ] | [ ] | [ ] | [ ] | As a user, I can reset sync tracking for a destination so that the next sync treats all files as new. Acceptance: all records of previously synced files for the destination's tracking group are cleared; the destination itself and its configuration remain intact; files at the destination are not affected. |

---

## 22.3 USB Drive Detection

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.3.1 | [x] | [x] | [x] | N/A | As a user, I can see connected USB drives automatically appear as available sync destinations so that I don't have to manually enter paths. Acceptance: when a USB drive is connected, it appears in the destination list without user action. |
| 22.3.2 | [x] | [x] | [x] | N/A | As a user, I can expect that system volumes (e.g., boot drives) are excluded from the USB destination list so that I don't accidentally sync to the wrong drive. Acceptance: on macOS, "Macintosh HD" and "Macintosh HD - Data" are excluded; on Windows, "C:" is excluded; on Linux, "boot" and "root" are excluded. |
| 22.3.3 | [x] | [x] | [x] | N/A | As a user, I can expect USB drive detection to work on macOS, Linux, and Windows so that the feature is available regardless of my platform. Acceptance: macOS scans `/Volumes/`, Linux scans `/media/$USER/` and `/mnt/`, Windows scans drive letters. |
| 22.3.4 | [x] | [x] | [x] | N/A | As a user, I can eject a USB drive after sync completes so that I can safely remove it. Acceptance: on macOS and Linux, the drive is ejected automatically or on request; on Windows, the user is informed to eject manually. |

---

## 22.4 Destination Association

Destinations can be associated to share sync tracking. When multiple destinations share tracking, syncing to one destination means the other destinations recognize those files as already synced. This is useful when the same physical storage is accessed through different paths (e.g., a USB drive accessed directly on the server and via a folder path from a client).

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.4.1 | [ ] | [ ] | [ ] | [ ] | As a user, I can link a destination to an existing destination so that they share sync tracking. Acceptance: the linked destination joins the target's tracking group; syncing to either destination updates the shared tracking for all destinations in the group. |
| 22.4.2 | [ ] | [ ] | [ ] | [ ] | As a user, I can unlink a destination from a shared tracking group so that it gets its own independent tracking. Acceptance: the destination is disassociated from the group and receives its own independent tracking; previously synced files are not re-synced until tracking is explicitly reset. |
| 22.4.3 | [ ] | [ ] | [ ] | [ ] | As a user, I can expect that when linking destinations, existing tracking data merges automatically so that no sync history is lost. Acceptance: if the destination being linked already had its own sync records, those records are combined with the group's records. |
| 22.4.4 | [ ] | [ ] | [ ] | [ ] | As a user, I can expect that shared tracking means syncing to one destination in a group updates the sync status for all destinations in that group. Acceptance: after syncing to destination A and then syncing to destination B (which shares tracking with A), the files synced via A are recognized and skipped. |
| 22.4.5 | [ ] | [ ] | [ ] | [ ] | As a user, I can see linked destinations displayed as a visual group so that I can understand which destinations share tracking. Acceptance: destinations sharing tracking are visually grouped together in the destination list; each group shows the shared sync status. |

---

## 22.5 Sync Status

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.5.1 | [ ] | [ ] | [ ] | [ ] | As a user, I can view a summary across all destinations showing total files, synced files, and new files so that I can see overall sync health. Acceptance: a summary table or card displays aggregate counts across all destination tracking groups. |
| 22.5.2 | [ ] | [ ] | [ ] | [ ] | As a user, I can view a per-playlist breakdown for a specific destination so that I can see detailed sync status. Acceptance: for a given destination (or its tracking group), each playlist shows its total file count, synced count, and new (unsynced) count. |
| 22.5.3 | [ ] | [ ] | [ ] | [ ] | As a user, I can see which playlists have never been synced to a given destination so that I know what's missing. Acceptance: playlists with zero synced files for the selected destination's tracking group are clearly identified. |
| 22.5.4 | [ ] | [ ] | [ ] | [ ] | As a user, I can see how many new (unsynced) files exist per playlist for a given destination so that I can prioritize what to sync. Acceptance: each playlist shows the count of files not yet recorded as synced for the destination's tracking group. |
| 22.5.5 | [ ] | [ ] | [ ] | [ ] | As a user, I can view which destinations have received each individual file so that I can trace where a specific track has been synced. Acceptance: for a given file, a list of destination names that include it is displayed. |

---

## 22.6 Client Sync

All sync clients (web dashboard, desktop app, iOS app) share core sync capabilities. This section describes the common functionality available across clients and notes client-specific features where they differ.

### Server Connection & Discovery (Desktop & iOS)

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.1 | N/A | [x] | [x] | [x] | As a user, I can discover servers automatically on the local network so that I don't have to manually configure a connection. Acceptance: the client uses mDNS/Bonjour to find running music-porter servers and presents them for selection. |
| 22.6.2 | N/A | [x] | [x] | [x] | As a user, I can enter a server URL and API key manually so that I can connect to servers not on the local network. Acceptance: the client accepts a URL and API key, validates the connection, and saves the configuration. |
| 22.6.3 | N/A | [x] | [x] | [x] | As a user, I can connect via local network or external URL, with the client trying local first and falling back to external so that the fastest connection is used automatically. Acceptance: the client attempts the local address first; if unreachable, it connects via the external URL without user intervention. |
| 22.6.4 | N/A | [ ] | [x] | [x] | As a user, I can reconnect, disconnect, or go offline from settings so that I have control over the connection state. Acceptance: settings provide explicit actions to reconnect to the server, disconnect cleanly, or switch to offline mode. |

### Playlist Selection

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.5 | [x] | [x] | [x] | [x] | As a user, I can view all playlists with file counts, sizes, and freshness status so that I can see what's available. Acceptance: each playlist shows its track count, total size, and whether it has new content since the last sync. |
| 22.6.6 | [x] | [x] | [x] | [ ] | As a user, I can select individual playlists or all playlists for sync so that I can control what gets synced. Acceptance: checkboxes or a select-all option allow choosing which playlists to include in the next sync operation. |

### Sync Execution

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.7 | [x] | [x] | [x] | [ ] | As a user, I can start a sync to copy new or changed files to the destination so that my music is up to date. Acceptance: pressing the sync button begins transferring files; only new or changed files are copied. |
| 22.6.8 | [x] | [x] | [x] | [ ] | As a user, I can force a re-sync to re-download all files regardless of sync status so that I can refresh everything. Acceptance: a force re-sync option ignores the sync tracking and re-copies all files. |
| 22.6.9 | [x] | [x] | [x] | [ ] | As a user, I can see a real-time progress bar with file count, percentage, and current filename during sync so that I know what's happening. Acceptance: the progress display updates continuously showing files completed out of total, percentage, and the name of the file currently being transferred. |
| 22.6.10 | [x] | [x] | [x] | [ ] | As a user, I can see live counters for copied, skipped, and failed files during sync so that I can monitor the operation. Acceptance: counters update in real time as each file is processed. |
| 22.6.11 | [x] | [x] | [x] | [ ] | As a user, I can cancel a sync in progress so that I can stop the operation if needed. Acceptance: cancellation stops the sync promptly; files already copied remain; no partial files are left. |
| 22.6.12 | [x] | [x] | [x] | [ ] | As a user, I can see a summary after sync showing copied, skipped, and failed counts along with the total duration so that I know the outcome. Acceptance: a summary is displayed after sync completes or is cancelled. |
| 22.6.13 | [x] | [x] | [x] | [ ] | As a user, I can expect that sync activity is recorded for tracking purposes regardless of which client I use so that my sync history is consistent. Acceptance: files synced via any client (web, desktop, iOS) are recorded under the destination's tracking group. |

### Offline Caching (Desktop & iOS)

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.14 | N/A | [x] | [x] | [x] | As a user, I can continue working offline using locally cached files when the server is unavailable so that I can still sync from cache. Acceptance: when the server is unreachable, the client operates in offline mode using cached metadata and audio files. |
| 22.6.15 | N/A | [x] | [x] | [x] | As a user, I can pin playlists for offline caching so that they are available without a server connection. Acceptance: pinned playlists are downloaded to the local cache and remain available when offline. |
| 22.6.16 | N/A | [x] | [x] | [x] | As a user, I can enable auto-pin so that new playlists are automatically pinned as they appear on the server. Acceptance: when auto-pin is enabled, any playlist added to the server is automatically marked as pinned and cached. |
| 22.6.17 | N/A | [x] | [x] | [x] | As a user, I can view per-playlist cache status (fully cached, partially cached, not cached) so that I know what's available offline. Acceptance: each playlist displays its cache state with a visual indicator. |
| 22.6.18 | N/A | [ ] | [x] | [x] | As a user, I can expect background prefetch to automatically cache pinned playlists during idle time so that they are ready when I need them. Acceptance: when the client is idle and connected to the server, pinned playlists are downloaded in the background without user action. |
| 22.6.19 | N/A | [x] | [x] | [x] | As a user, I can manage cache by setting a maximum cache size, clearing individual playlists, or clearing all cached files so that I can control disk usage. Acceptance: cache settings allow setting a size limit; clearing a playlist removes its cached files; clearing all removes the entire cache. |

### Destination Selection

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.20 | [x] | [x] | [x] | N/A | As a user, I can see connected USB drives auto-detected with free space shown so that I can choose where to sync. Acceptance: USB drives appear in the destination list with their name and available free space displayed. |
| 22.6.21 | [x] | [x] | [x] | [ ] | As a user, I can browse for a local folder as a sync destination so that I can sync to any directory on my computer. Acceptance: a folder picker dialog allows selecting any local directory as the sync target. |
| 22.6.22 | [ ] | [ ] | [x] | [ ] | As a user, I can select from recently used destinations via a dropdown so that I can quickly pick familiar targets. Acceptance: a dropdown lists previously used destinations; selecting one sets it as the active destination. |
| 22.6.23 | [x] | [x] | [x] | [ ] | As a user, I can expect that when a USB drive is selected, files sync to the output profile's configured USB directory within the drive so that files are organized consistently. Acceptance: files are placed in the subdirectory specified by the profile's `usb_dir` setting on the selected drive. |

### USB Drive Features (Desktop & Server)

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.24 | [x] | [x] | [x] | N/A | As a user, I can eject USB drives safely from within the application so that I can remove them without data loss. Acceptance: an eject button is available for connected USB drives; the drive is unmounted safely before removal. |
| 22.6.25 | [ ] | [ ] | [x] | N/A | As a user, I can toggle auto-eject so that USB drives are ejected automatically after sync completes. Acceptance: when auto-eject is enabled, the USB drive is ejected immediately after a successful sync without user action. |
| 22.6.26 | [ ] | [ ] | [x] | N/A | As a user, I can configure auto-sync for specific USB drives so that syncing starts automatically when I plug them in. Acceptance: the client remembers which USB drives have auto-sync enabled; when one of those drives is connected, sync begins automatically. |

### Browser-Specific Features (Web Dashboard)

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.27 | [x] | N/A | N/A | N/A | As a user, I can sync files directly to a local folder from the web browser (in Chromium-based browsers) so that I can download music without a separate client. Acceptance: using the File System Access API, the user selects a local folder and files are written directly to it. |
| 22.6.28 | [x] | N/A | N/A | N/A | As a user, I can download playlists as ZIP archives in non-Chromium browsers so that I have a fallback when direct folder sync is unavailable. Acceptance: a download button produces a ZIP file containing the tagged MP3s with human-readable filenames. |
| 22.6.29 | [x] | N/A | N/A | N/A | As a user, I can download a single playlist as a ZIP or multiple playlists as a combined ZIP so that I can get exactly what I need in one download. Acceptance: single-playlist ZIP contains that playlist's files; multi-playlist ZIP contains all selected playlists' files organized by playlist. |

### Settings (Desktop & iOS)

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.6.30 | [x] | [x] | [x] | [x] | As a user, I can select an output profile that controls file naming, tags, and artwork so that synced files match my preferences. Acceptance: a profile selector lists available profiles from the server; the selected profile is applied during sync. |
| 22.6.31 | [ ] | [x] | [x] | [ ] | As a user, I can adjust parallel download concurrency (1–8 concurrent downloads) so that I can balance speed and system load. Acceptance: a concurrency setting allows choosing between 1 and 8 simultaneous downloads; the setting is saved for future sessions. |
| 22.6.32 | [ ] | [ ] | [x] | [x] | As a user, I can view the server version and release notes from the client so that I know what version I'm connected to. Acceptance: the client displays the connected server's version number and its release notes. |

---

## 22.7 Output Profiles in Sync

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.7.1 | [x] | [x] | [x] | [ ] | As a user, I can select an output profile before syncing so that I control how files are tagged and named at the destination. Acceptance: a profile selection option is available before starting a sync; the chosen profile is applied to all files during that sync. |
| 22.7.2 | [x] | [x] | [x] | [ ] | As a user, I can expect the profile to control file naming, directory structure, ID3 tags, and artwork for synced files so that the output matches my requirements. Acceptance: destination files use the profile's filename template, directory template, tag settings, and artwork size. |
| 22.7.3 | [ ] | N/A | N/A | [ ] | As a user, I can compare available profiles side-by-side so that I can choose the right one for my use case. Acceptance: profile details (tag settings, filename format, artwork size) are viewable for comparison before selection. |
| 22.7.4 | [x] | [x] | [x] | [ ] | As a user, I can expect the profile to be applied on-the-fly during sync so that library files are never modified. Acceptance: the original library MP3s retain only their UUID tag; profile-specific tags and filenames are generated at sync time. |

---

## 22.8 Edge Cases

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 22.8.1 | [x] | [x] | [x] | [ ] | As a user, if a destination becomes unavailable mid-sync (e.g., drive disconnected, folder deleted), the sync stops gracefully with an error message and files already copied remain intact. |
| 22.8.2 | [x] | [x] | [x] | [ ] | As a user, if multiple tracks produce the same filename at the destination, the system resolves the collision (e.g., by appending a number) so that no files are overwritten. |
| 22.8.3 | [x] | [x] | [x] | [ ] | As a user, if I sync when the library is empty, the system reports that there are no files to sync rather than failing silently or producing an error. |
| 22.8.4 | [x] | [x] | [x] | [ ] | As a user, if I cancel a sync mid-operation, files already copied to the destination remain intact and are not deleted. |
| 22.8.5 | [x] | [x] | [x] | [ ] | As a user, syncing a large library with thousands of files completes reliably without memory exhaustion or timeouts. |
| 22.8.6 | [x] | [x] | [x] | [ ] | As a user, if a USB drive is disconnected during sync, the system detects the loss and stops with a clear error rather than producing corrupted files. |
| 22.8.7 | N/A | [x] | [x] | [ ] | As a user, if I perform an offline sync from a client when the cache is incomplete, only cached files are synced and the client reports which files were skipped due to missing cache. |
| 22.8.8 | N/A | [x] | [x] | [ ] | As a user, if the server becomes unreachable during a client sync, the client degrades gracefully by stopping new downloads and reporting the partial result. |
