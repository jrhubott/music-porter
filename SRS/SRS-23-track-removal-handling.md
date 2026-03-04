# SRS 23: Playlist Track Removal Handling

**Version:** 1.2  |  **Date:** 2026-03-03  |  **Status:** Complete

---

## 23.1 Removed Track Detection

After downloading a playlist, the system identifies tracks that exist in the library for that playlist but are no longer part of the current Apple Music playlist.

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.1.1 | [x] | N/A | N/A | N/A | As a user, I can see which tracks were removed from an Apple Music playlist after a download completes so that I know what changed. Acceptance: the download result includes a list of removed tracks with their title, artist, and album; the count of removed tracks is shown in the operation summary. |
| 23.1.2 | [x] | N/A | N/A | N/A | As a user, I can see removed track detection results in the pipeline and download operation logs so that I have visibility into what the system found. Acceptance: removed track details are logged with track title and artist; the log clearly distinguishes removed tracks from downloaded/skipped tracks. |

---

## 23.2 Library Cleanup

When removed tracks are detected during a download, the user can choose to clean them up from the library. Cleanup performs a full cascade: source M4A, converted MP3, artwork file, and TrackDB record are all removed.

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.2.1 | [x] | N/A | N/A | N/A | As a user, I can enable a "clean up removed tracks" option when running a download or pipeline operation so that tracks no longer in the Apple Music playlist are purged from my library. Acceptance: when enabled, removed tracks are deleted (source M4A, converted MP3, artwork, and TrackDB record); when disabled (the default), removed tracks are kept in the library untouched. |
| 23.2.2 | [x] | N/A | N/A | N/A | As a user, I can configure a server setting that controls the default behavior for removed track cleanup so that I don't have to set the option every time. Acceptance: a setting in server settings controls whether cleanup defaults to enabled or disabled; the per-operation option overrides this setting; the default value of the setting is "disabled" (keep removed tracks). |
| 23.2.3 | [x] | N/A | N/A | N/A | As a user, I can see a summary of what was cleaned up after a download with cleanup enabled so that I know what was removed. Acceptance: the operation result includes the count of tracks cleaned up and the total disk space freed; individual track details (title, artist) are in the operation log. |
| 23.2.4 | [x] | N/A | N/A | N/A | As a user, I can expect that cleanup also removes the sync tracking records for cleaned-up tracks so that sync destinations correctly reflect the library state. Acceptance: SyncTracker records for removed tracks are deleted as part of the cascade; subsequent sync status queries no longer count the removed tracks. |

---

## 23.3 Orphaned File Tracking & Visibility

The system persistently tracks which synced files are orphaned (previously synced but no longer in the library) per sync group. This information is always available, not just during sync operations.

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.3.1 | [x] | [x] | [x] | N/A | As a user, I can see orphaned file counts per sync group at any time so that I know which destinations have out-of-date files without running a sync. Acceptance: the sync status API includes an `orphaned_files` count per sync group; this count reflects files recorded in SyncTracker whose source tracks no longer exist in the library. |
| 23.3.2 | [x] | N/A | N/A | N/A | As a user, I can see orphaned file counts on the web dashboard sync page so that I have visibility into stale files at each destination. Acceptance: each destination/group on the sync page displays the number of orphaned files alongside synced and new file counts; zero orphans shows no indicator. |
| 23.3.3 | [x] | N/A | N/A | N/A | As a user, I can view the list of orphaned files for a sync group on the web dashboard so that I can see exactly which files are stale. Acceptance: expanding or drilling into a destination shows the orphaned file names grouped by playlist. |

---

## 23.4 Sync Destination Cleanup

During a sync operation, the system detects orphaned files at the destination and reports them. The user can optionally remove these orphaned files.

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.4.1 | [x] | [x] | [x] | N/A | As a user, I can see a report of orphaned files at a sync destination after a sync completes so that I know what is out of date. Acceptance: the sync result includes the count of orphaned files detected at the destination; orphaned file names are listed in the sync log. |
| 23.4.2 | [x] | [x] | [x] | N/A | As a user, I can enable a "clean destination" option when running a sync so that orphaned files are removed from the destination. Acceptance: when enabled, files at the destination that correspond to tracks no longer in the library are deleted; their SyncTracker records are also removed; when disabled (the default), orphaned files are reported but not deleted. |
| 23.4.3 | [x] | [x] | [x] | N/A | As a user, I can configure a server setting that controls the default behavior for destination cleanup so that I don't have to set the option every time. Acceptance: a setting controls whether destination cleanup defaults to enabled or disabled; the per-operation option overrides this setting; the default value is "disabled" (keep orphaned files). |
| 23.4.4 | [x] | [x] | [x] | N/A | As a user, I can see a summary of what was cleaned up at the destination after a sync with cleanup enabled so that I know what was removed. Acceptance: the sync result includes the count of files removed from the destination and the total disk space freed. |
| 23.4.5 | [x] | [x] | [x] | N/A | As a user, I can expect that orphaned file detection uses SyncTracker records to identify files that were previously synced but whose source tracks no longer exist in the library. Acceptance: only files recorded in SyncTracker are considered for cleanup; files placed at the destination by other means are never touched. |

---

## 23.5 Client Cache Cleanup

The server provides information about removed tracks so that sync clients (iOS, desktop) can proactively clean up their local cache.

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.5.1 | N/A | [x] | [x] | [x] | As a user, I can expect the server API to report which tracks have been removed from a playlist since a given point in time so that my sync client can clean up its local cache. Acceptance: an API parameter allows querying for tracks removed since a timestamp; the response includes the UUIDs and display filenames of removed tracks. |
| 23.5.2 | N/A | [x] | [x] | [x] | As a user, I can expect my sync client to automatically remove cached audio files for tracks that are no longer on the server so that my cache stays in sync. Acceptance: during a sync or prefetch operation, the client queries the server for removed tracks and deletes the corresponding cached audio files and cache index entries. |
| 23.5.3 | N/A | [x] | [x] | N/A | As a user, I can expect my sync client to remove files from the sync destination for tracks that are no longer on the server when destination cleanup is enabled so that my destination stays in sync. Acceptance: during a folder sync with cleanup enabled, the client queries the server for removed tracks and deletes the corresponding files at the destination; the manifest is updated to remove those entries. |
| 23.5.4 | N/A | [x] | [x] | [x] | As a user, I can expect the client to log which files were removed from cache or destination so that I have visibility into what changed. Acceptance: the sync log shows each removed file with its display filename and the reason for removal (track removed from server). |

---

## 23.6 Edge Cases

| ID | Web | CLI | GUI | iOS | Requirement |
|----|-----|-----|-----|-----|-------------|
| 23.6.1 | [x] | [x] | [x] | [x] | As a user, if the removed track detection mechanism fails or produces an error, the download operation still completes successfully and I am informed that detection was not possible. Acceptance: the download succeeds regardless of detection outcome; an informational message notes that removal detection was skipped due to the error. |
| 23.6.2 | [x] | [x] | [x] | N/A | As a user, if a sync destination is read-only or becomes unavailable during cleanup, orphaned files are reported but cleanup is skipped with a clear message. Acceptance: the sync does not fail; a warning message explains that cleanup could not be performed due to the destination state. |
| 23.6.3 | [x] | [x] | [x] | N/A | As a user, if cleanup is enabled and the destination disconnects mid-cleanup, files already removed stay removed and the operation stops gracefully. Acceptance: no partial or corrupted files are left; a summary of what was completed before the failure is shown. |
| 23.6.4 | [x] | N/A | N/A | N/A | As a user, if all tracks in a playlist are detected as removed, I receive a clear warning before cleanup proceeds so that I can verify this is intentional. Acceptance: a warning is logged indicating that the entire playlist would be purged; cleanup still proceeds if the option is enabled (no interactive prompt in the web context). |
| 23.6.5 | [x] | [x] | [x] | [x] | As a user, destination cleanup only removes files that were placed by music-porter (tracked in SyncTracker) and never removes unrelated files that happen to exist at the destination. Acceptance: files not recorded in SyncTracker are never modified or deleted, even if they have similar names. |
| 23.6.6 | [x] | N/A | N/A | N/A | As a user, if I run a pipeline (download + convert + sync) with both library cleanup and destination cleanup enabled, the cleanup cascades correctly: removed tracks are purged from the library first, then orphaned files are removed from the destination during the sync step. Acceptance: the pipeline stages execute in order; the sync step correctly identifies orphans based on the post-cleanup library state. |
