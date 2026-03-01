# iOS Cache Module — Integration TODO

Parity checklist for the iOS companion app cache module against the sync
client (`sync-client/packages/`). The cache infrastructure (actors, types,
utilities) exists on the `feature/ios-cache-module` branch. This document
describes the remaining work to reach feature parity with the sync client.

---

## Reference: Sync Client Cache Features

The sync client uses its cache in four places:

1. **SyncEngine** — cache hit (copy from cache instead of downloading),
   write-through (store into cache after downloading), offline sync (copy
   entirely from cache with no server contact).
2. **PrefetchEngine** — background download of pinned playlists into cache
   with eviction, triggered on connect and on a 5-minute timer.
3. **APIClient** — ETag-based conditional requests for playlists list
   (in-memory) and file lists (persistent via MetadataCache).
4. **Settings/UI** — playlist pinning, auto-pin, max cache size, cache
   status display, manual prefetch button, clear cache, per-playlist
   cache counts, background prefetch progress in sidebar.

---

## 1. Playlist Pinning & Persistence

**Sync client equivalent:** `ConfigStore.pinPlaylist()`,
`unpinPlaylist()`, `syncPinsWithServer()`, `autoPinNewPlaylists`,
`unpinnedPlaylists` exclusion list. Persisted in `config.json`.

**What to build:**

Add a `CachePreferences` model persisted in UserDefaults with:

- `pinnedPlaylists: [String]` — playlist keys the user has pinned
- `unpinnedPlaylists: [String]` — exclusion list for auto-pin
  (playlists the user explicitly unpinned while auto-pin is on)
- `maxCacheBytes: Int64` — cache size limit (default 10 GB)
- `autoPinNewPlaylists: Bool` — when true, new server playlists are
  auto-pinned unless in the exclusion list

Add helper methods on AppState (or a dedicated `CachePreferencesStore`):

- `pinPlaylist(_:)` — add to pinned, remove from exclusion list
- `unpinPlaylist(_:)` — remove from pinned, add to exclusion list
  if auto-pin is on
- `syncPinsWithServer(_:)` — when auto-pin is on, pin any server
  playlists not already pinned and not in exclusion list; return
  newly pinned keys
- `setAutoPinNewPlaylists(_:)` — toggle auto-pin; clear exclusion
  list on disable

**Files to create/modify:**

- New: `CachePreferencesStore.swift` (or inline on AppState)
- Modify: `AppState.swift` — expose pin/unpin/auto-pin methods

---

## 2. ETag-Aware File List Fetching

**Sync client equivalent:** `APIClient.getFiles()` accepts optional
`metadataCache` parameter. Sends `If-None-Match` with cached ETag,
returns cached data on 304, stores fresh data on 200.
`APIClient.getPlaylists()` uses in-memory ETag.

**What exists:** `APIClient.getFilesWithETag()` and `getPlaylists()`
with in-memory ETag are implemented. `MetadataCache` actor is complete.

**What to wire:**

Every call site that fetches file lists should use the ETag path when
a MetadataCache is available. This matches how the sync client passes
`metadataCache` through `SyncOptions` and `PrefetchOptions`.

**Files to modify:**

- `PlaylistDetailViewModel.swift` — use `getFilesWithETag` when
  `appState.metadataCache` is available
- `LibraryView.swift` — use `getFilesWithETag` in export flow
- `PipelineView.swift` — same for any `getFiles` calls

**Pattern:**

```swift
if let cache = appState.metadataCache {
    response = try await apiClient.getFilesWithETag(
        playlist: key, profile: appState.activeProfile, metadataCache: cache)
} else {
    response = try await apiClient.getFiles(playlist: key)
}
```

---

## 3. Cache-Aware Downloads (Write-Through)

**Sync client equivalent:** `SyncEngine` calls
`cache.storeFromFile(file, playlistKey, filePath)` after every
successful download (write-through). Before downloading, checks
`cache.copyToDestination(uuid, filePath)` for a cache hit.

**What to build:**

`FileDownloadManager` should write through to the audio cache after
downloading, and check the cache before downloading.

**Files to modify:**

- `FileDownloadManager.swift`:
  - After a successful file download to Documents, call
    `audioCacheManager.storeFromFile(sourcePath, file:, playlistKey:)`
  - Before downloading, call `audioCacheManager.isCached(uuid)`. If
    cached, copy from cache to Documents instead of re-downloading.
  - Accept `audioCacheManager: AudioCacheManager?` via a `configure()`
    call or read from AppState at the call site.

---

## 4. Cache-Aware USB Export (Cache Hit)

**Sync client equivalent:** `SyncEngine` checks
`cache.copyToDestination(uuid, filePath)` before downloading. If the
file is in cache, it copies directly from cache to destination.

**What to build:**

`exportToFolder` in LibraryView and PipelineView should check the
audio cache for files not available in Documents. Use
`audioCacheManager.copyToDestination(uuid, destPath)` to export
cached files directly to USB.

**Files to modify:**

- `LibraryView.swift` — in `exportToFolder`, after collecting local
  files, query the cache for any files not locally available
- `PipelineView.swift` — same pattern

---

## 5. Cache-Aware Playback

**Sync client equivalent:** N/A (sync client has no playback). This is
iOS-specific but natural for a cache module.

**What to build:**

`AudioPlayerService` streams tracks from the server via URL. When a
track is in the audio cache, play from the local cache URL instead.

**Files to modify:**

- `AudioPlayerService.swift` — before building a server streaming URL,
  check `audioCacheManager.isCached(uuid)`. If it returns a local URL,
  use `AVPlayer(url: localURL)` for instant playback.
  - Requires access to `audioCacheManager` — either accept it via a
    new `configure(audioCacheManager:)` call, or read from `AppState`
    at the call site in views that invoke playback.

---

## 6. Background Prefetch

**Sync client equivalent:** `BackgroundPrefetchService` class in the
GUI. Runs on a 5-minute interval timer. Triggered immediately on
connect via `notifyConnected()`. Auto-syncs pins with server when
auto-pin is enabled. Uses `PrefetchEngine.prefetch()` with
`maxCacheBytes`, `pinnedPlaylists`, and `metadataCache`. Sends
progress events to the renderer. The CLI exposes
`mporter-sync cache prefetch` as a manual command.

**What exists:** `PrefetchEngine` actor is complete. Nothing invokes it.

**What to build:**

Add a background prefetch service that:

1. Triggers on connect (after `initializeCacheServices()`)
2. Runs on a repeating timer (5-minute interval, matching
   `CacheConstants.backgroundPrefetchIntervalSeconds`)
3. If auto-pin is enabled, syncs pins with server before prefetching
4. Calls `prefetchEngine.prefetch()` with pinned playlists,
   `maxCacheBytes`, and `metadataCache`
5. Publishes progress for UI display
6. Cancels on disconnect

**Files to create/modify:**

- New: `BackgroundPrefetchService.swift` — actor or class that owns
  a repeating `Task`, calls `prefetchEngine.prefetch()`, publishes
  progress via a callback or `@Observable` properties
- Modify: `AppState.swift`:
  - Add `backgroundPrefetchService: BackgroundPrefetchService?`
  - Create in `initializeCacheServices()`
  - Start on connect, stop on disconnect
  - Expose `isPrefetching`, `prefetchProgress`, `lastPrefetchResult`
    for UI binding

---

## 7. Manual Prefetch Trigger

**Sync client equivalent:** CLI `mporter-sync cache prefetch` command.
GUI "Prefetch Now" button on Settings page and Sync page header. GUI
IPC handler `cache:prefetch` and `cache:triggerPrefetch`.

**What to build:**

A "Prefetch Now" button that triggers an immediate prefetch cycle
outside the background timer. Show progress inline.

**Files to modify:**

- `SettingsView.swift` — add "Prefetch Now" button in cache section
- `AppState.swift` — add `triggerPrefetch()` method that calls
  `backgroundPrefetchService.runOnce()` or directly invokes
  `prefetchEngine.prefetch()`

---

## 8. Offline Mode (Cache-Only Sync)

**Sync client equivalent:** `SyncEngine.syncOffline()` — when
`offlineOnly: true`, syncs entirely from local cache with no server
contact. Uses `cache.getCachedPlaylists()` and
`cache.getCachedFileInfos(key)` as the source of truth. CLI:
`mporter-sync sync --offline`. GUI: offline toggle on SyncPage.

**What to build (if desired):**

USB export from cache when the server is unreachable. The iOS app
doesn't have a full sync engine, but `exportToFolder` could work
offline by reading entirely from the audio cache:

- Use `audioCacheManager.getCachedPlaylists()` to discover available
  playlists
- Use `audioCacheManager.getCachedFileInfos(key)` for file lists
- Use `audioCacheManager.copyToDestination(uuid, path)` to copy
  files to USB

This is lower priority since the iOS app requires a server connection
for most operations, but it would allow USB export to work with
cached content when connectivity drops after initial sync.

---

## 9. Cache Management UI

**Sync client equivalent:** GUI SettingsPage shows:

- Total cache size (formatted bytes)
- Max cache size dropdown (5 GB, 10 GB, 20 GB, 50 GB, Unlimited)
- Auto-pin new playlists toggle
- Per-playlist cache status (cached count / total count, pin state)
- Per-playlist "Clear" button
- "Clear All Cache" button
- "Prefetch Now" button
- Background prefetch status (running/idle, last run time, last result)
- Prefetch progress bar during active prefetch

GUI SyncPage shows:

- Pin toggle button on each playlist card
- Per-playlist cache count badge (shows "cached" when fully cached,
  or numeric count when partially cached)
- Cache status indicator in header (color-coded: green = complete,
  yellow = near full, red = incomplete)
- "Prefetch Now" button in sync header

GUI sidebar (App.tsx) shows:

- Cache progress bar during active prefetch
- "Cache updated" transient notification (5-second auto-dismiss)
- "Cache good" indicator (green dot) when all pinned playlists are
  fully cached
- "Cache incomplete" indicator (red dot) when pinned playlists have
  missing files

**What to build in SettingsView.swift:**

```
Section("Cache") {
    LabeledContent("Cache Size", value: "2.3 GB / 10 GB")

    Picker("Max Cache Size", selection: $maxCacheSize) {
        Text("5 GB").tag(5 GB)
        Text("10 GB").tag(10 GB)
        Text("20 GB").tag(20 GB)
        Text("50 GB").tag(50 GB)
        Text("Unlimited").tag(0)
    }

    Toggle("Auto-Pin New Playlists", isOn: $autoPinNewPlaylists)

    Button("Prefetch Now") { ... }
        // Show progress bar when prefetching

    Button("Clear Cache", role: .destructive) { ... }
}
```

**What to build in LibraryView.swift:**

- Pin toggle on each playlist row (swipe action or button)
- Cache count badge per playlist (e.g., "3/12 cached" or "cached")

**Files to modify:**

- `SettingsView.swift` — cache management section
- `LibraryView.swift` — pin toggles and cache badges on playlist rows

---

## 10. Profile Switching

**Sync client equivalent:** Cache instances are created per-profile.
`CacheManager` and `MetadataCache` constructors take `profile` string.
GUI recreates instances when profile changes.

**What exists:** `AppState.switchProfile(_:)` reinitializes cache
services with the new profile. No view calls it yet.

**What to wire:**

- `SettingsView.swift` — call `appState.switchProfile(newProfile)`
  instead of directly setting `activeProfile`
- This ensures cache services, background prefetch, and pin state
  all reinitialize for the new profile

---

## 11. Cache Size Enforcement with Immediate Eviction

**Sync client equivalent:** GUI IPC handler `cache:setMaxSize` calls
`configStore.updatePreferences({ maxCacheBytes })` then immediately
runs `cacheManager.evictToLimit(maxBytes, pinnedSet)` to enforce the
new limit. Also triggers a background prefetch cycle to rebalance.

**What to build:**

When the user changes the max cache size setting:

1. Persist the new value
2. Immediately call `audioCacheManager.evictToLimit(maxBytes,
   pinnedPlaylists)` to enforce
3. Optionally trigger a prefetch cycle to fill newly available space

**Files to modify:**

- `AppState.swift` or `CachePreferencesStore.swift` — method to
  update max cache size with immediate eviction
- `SettingsView.swift` — call this method from the picker's onChange

---

## Implementation Order

1. **Playlist pinning & preferences** (foundation for everything else)
2. **ETag-aware file list fetching** (wire existing code to views)
3. **Write-through downloads** (populate cache from existing download flow)
4. **Cache hit for downloads** (serve from cache before downloading)
5. **Cache hit for USB export** (export from cache when available)
6. **Cache-aware playback** (play from cache URL)
7. **Background prefetch service** (auto-download pinned playlists)
8. **Manual prefetch trigger** (button in Settings)
9. **Cache management UI** (Settings section with size, limits, clear)
10. **Playlist pin UI** (toggles in LibraryView, badges)
11. **Cache size enforcement** (immediate eviction on limit change)
12. **Offline USB export** (optional, lower priority)

---

## Parity Matrix

| Feature | Sync Client | iOS App (Built) | iOS App (TODO) |
|---------|-------------|-----------------|----------------|
| MetadataCache (ETag file lists) | Yes | Yes (actor) | Wire to views |
| AudioCacheManager (file cache) | Yes | Yes (actor) | Wire to downloads/export |
| PrefetchEngine | Yes | Yes (actor) | Wire to background service |
| In-memory ETag for playlists | Yes | Yes | Done |
| ETag for file lists via MetadataCache | Yes | Yes (APIClient method) | Wire to views |
| Write-through on download | Yes | No | TODO |
| Cache hit before download | Yes | No | TODO |
| Cache hit for USB export | Yes | No | TODO |
| Offline sync from cache | Yes | No | TODO (low priority) |
| Playlist pinning | Yes | No | TODO |
| Auto-pin new playlists | Yes | No | TODO |
| Pin exclusion list | Yes | No | TODO |
| Max cache size setting | Yes (persisted) | No | TODO |
| Immediate eviction on limit change | Yes | No | TODO |
| Background prefetch on timer | Yes (5 min) | No | TODO |
| Prefetch on connect | Yes | No | TODO |
| Manual "Prefetch Now" button | Yes | No | TODO |
| Cache size display | Yes | No | TODO |
| Per-playlist cache count badges | Yes | No | TODO |
| Per-playlist pin toggle | Yes | No | TODO |
| Per-playlist clear button | Yes | No | TODO |
| Clear all cache button | Yes | No | TODO |
| Prefetch progress display | Yes (sidebar + page) | No | TODO |
| Background prefetch status | Yes (sidebar indicator) | No | TODO |
| Cache-aware playback | N/A | No | TODO |
| Profile switching reinit | Yes | Yes | Wire to views |
| Staleness detection | Yes | Yes (actor) | Used by PrefetchEngine |

---

## Files Summary

| File | Status | Changes Needed |
|------|--------|----------------|
| `CacheConstants.swift` | Done | — |
| `CacheTypes.swift` | Done | — |
| `CacheUtils.swift` | Done | — |
| `MetadataCache.swift` | Done | — |
| `AudioCacheManager.swift` | Done | — |
| `PrefetchEngine.swift` | Done | — |
| `Track.swift` | Done | — |
| `APIClient.swift` | Done | — |
| `AppState.swift` | Done | Add pin/prefetch/cache-size methods |
| `CachePreferencesStore.swift` | New | Pinning, max size, auto-pin persistence |
| `BackgroundPrefetchService.swift` | New | Timer-based prefetch, connect trigger |
| `PlaylistDetailViewModel.swift` | Modify | Use `getFilesWithETag` |
| `FileDownloadManager.swift` | Modify | Write-through + cache hit |
| `AudioPlayerService.swift` | Modify | Cache-aware playback |
| `USBExportService.swift` | Modify | Cache hit for export (or handle in views) |
| `LibraryView.swift` | Modify | Pin toggles, cache badges, cache-aware export |
| `PipelineView.swift` | Modify | Cache-aware export |
| `SettingsView.swift` | Modify | Cache management section |
