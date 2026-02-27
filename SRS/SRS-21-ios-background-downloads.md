# SRS 21: iOS Background Downloads & Export

**Version:** 1.0  |  **Date:** 2026-02-26  |  **Status:** Draft

---

## Purpose

Enable iOS file downloads and USB exports to continue when the app is backgrounded or the phone is locked. Downloads use a background `URLSession` (system-managed, survives app backgrounding and termination). USB exports use `beginBackgroundTask` for ~30 seconds of extended execution to finish in-progress file copies.

---

## Requirements

### 21.1 Background Download Continuation

Downloads shall continue when the app is backgrounded or the device is locked, using a background `URLSession`.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.1.1 | | [ ] | A dedicated `BackgroundDownloadManager` class owns a `URLSessionConfiguration.background` session with identifier `com.musicporter.background-downloads` |
| 21.1.2 | | [ ] | `isDiscretionary` is set to `false` so downloads start immediately (user-initiated over LAN) |
| 21.1.3 | | [ ] | `sessionSendsLaunchEvents` is set to `true` so the system can relaunch the app after background downloads complete |
| 21.1.4 | | [ ] | `BackgroundDownloadManager` implements `URLSessionDownloadDelegate` to handle download completion, errors, and session-level events |
| 21.1.5 | | [ ] | Active downloads are tracked in a dictionary keyed by `URLSessionTask.taskIdentifier`, storing playlist name, filename, and destination directory |
| 21.1.6 | | [ ] | Auth headers (Bearer token) are set per-request via `authenticatedRequest(for:)`, not per-session |
| 21.1.7 | | [ ] | `FileDownloadManager.downloadAll(playlist:)` enqueues files on the background session instead of using `URLSession.shared` |
| 21.1.8 | | [ ] | `FileDownloadManager.downloadFile(playlist:filename:)` uses the background session for individual file downloads |
| 21.1.9 | | [ ] | Download progress (`downloadProgress`) is updated as each background download completes |

### 21.2 Export Background Task Protection

USB export operations shall request extended execution time when the app goes to background.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.2.1 | | [ ] | `USBExportService.exportFiles(groups:to:cacheToDevice:)` calls `UIApplication.shared.beginBackgroundTask(withName:)` before starting work |
| 21.2.2 | | [ ] | The background task identifier is stored and `endBackgroundTask` is called in a `defer` block after `copyGroupedFiles` returns |
| 21.2.3 | | [ ] | The expiration handler logs that background time expired (the in-flight copy stops naturally when suspended) |

### 21.3 Progress Restoration on App Foreground

When the app returns to the foreground, download progress shall reflect the actual state of completed downloads.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.3.1 | | [ ] | `FileDownloadManager.reconcileBackgroundDownloads()` is called when the app transitions to `.active` scene phase |
| 21.3.2 | | [ ] | Reconciliation loads persisted download state, checks what files exist on disk, and updates `downloadProgress` accordingly |
| 21.3.3 | | [ ] | If all pending downloads are complete, stored state is cleared and progress shows completion |

### 21.4 State Persistence Across App Termination

Download state shall persist across app termination so progress can be restored when the app relaunches.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.4.1 | | [ ] | A `DownloadStateStore` persists pending download state (playlist, total files, completed files, failed files) in `UserDefaults` |
| 21.4.2 | | [ ] | `BackgroundDownloadManager` updates `DownloadStateStore` on each delegate callback (file complete or file failed) |
| 21.4.3 | | [ ] | `DownloadStateStore` is read by `reconcileBackgroundDownloads()` on app foreground to restore progress |
| 21.4.4 | | [ ] | Stored state is cleared when all downloads in a batch are complete or when the user cancels |

### 21.5 App Delegate Integration

The app shall handle background URLSession reconnection via an `AppDelegate`.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.5.1 | | [ ] | `MusicPorterApp` registers an `AppDelegate` via `@UIApplicationDelegateAdaptor` |
| 21.5.2 | | [ ] | `AppDelegate` implements `application(_:handleEventsForBackgroundURLSession:completionHandler:)` and stores the completion handler on `BackgroundDownloadManager.shared` |
| 21.5.3 | | [ ] | `BackgroundDownloadManager` calls the stored completion handler on the main thread in `urlSessionDidFinishEvents(forBackgroundURLSession:)` |
| 21.5.4 | | [ ] | Info.plist includes `fetch` in `UIBackgroundModes` to enable system relaunch after background downloads |

### 21.6 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 21.6.1 | | [ ] | Server unreachable during background download: individual file failures are tracked; completed files are preserved on disk |
| 21.6.2 | | [ ] | Download cancellation: `BackgroundDownloadManager.cancelAll()` invalidates all pending tasks and clears stored state |
| 21.6.3 | | [ ] | App termination mid-download: background URLSession resumes downloads when the app relaunches; completed files are on disk |
| 21.6.4 | | [ ] | App returns to foreground with no pending state: `reconcileBackgroundDownloads()` is a no-op |
| 21.6.5 | | [ ] | Export background task expiration: the expiration handler is logged; no crash or data corruption occurs |
| 21.6.6 | | [ ] | Thread safety: `BackgroundDownloadManager` uses a serial `DispatchQueue` to protect its `activeDownloads` dictionary from concurrent access |

---
