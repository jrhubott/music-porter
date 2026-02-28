# iOS Cache Module — Integration TODO

What has been built (this branch) and what remains to fully integrate
the cache module into the iOS companion app.

---

## What Exists Now

The cache infrastructure is complete and compiles cleanly. All files are
in `ios/MusicPorter/MusicPorter/Services/Cache/`.

| File | Purpose |
|------|---------|
| `CacheConstants.swift` | Named constants (dir names, filenames, schema version, limits) |
| `CacheTypes.swift` | Codable structs for JSON serialization, ETagResult, PrefetchResult, etc. |
| `CacheUtils.swift` | Atomic JSON read/write, file ops, formatting helpers |
| `MetadataCache.swift` | Actor managing metadata-cache.json (playlist file lists + ETags) |
| `AudioCacheManager.swift` | Actor managing cache-index.json + audio files with eviction |
| `PrefetchEngine.swift` | Actor for concurrent background prefetching via TaskGroup |

Modified files:

- `Track.swift` — Added optional `createdAt`/`updatedAt` fields
- `APIClient.swift` — Added `getWithETag`, `getFilesWithETag`, `downloadFileData`, in-memory ETag cache for playlists
- `AppState.swift` — Added `metadataCache`, `audioCacheManager`, `prefetchEngine` properties; `initializeCacheServices()` on connect; `switchProfile()` method; cleanup on disconnect

**None of the views or existing services use the cache yet.** The module
is wired into AppState but no call sites consume it.

---

## Integration Steps

### 1. Cache-Aware File List Fetching

Views that fetch file lists should use ETag-aware requests via MetadataCache
so repeated refreshes return cached data when nothing changed (304).

**Files to modify:**

- `PlaylistDetailViewModel.swift` — Change `apiClient.getFiles(playlist:)` to
  `apiClient.getFilesWithETag(playlist:profile:metadataCache:)`. Fall back to
  the non-ETag version if `metadataCache` is nil.
- `LibraryView.swift` — Any inline `getFiles` calls in `exportToFolder` should
  use the ETag path when a cache is available.
- `PipelineView.swift` — Same for any `getFiles` calls.

**Pattern:**

```swift
if let cache = appState.metadataCache {
    response = try await apiClient.getFilesWithETag(
        playlist: key, profile: appState.activeProfile, metadataCache: cache)
} else {
    response = try await apiClient.getFiles(playlist: key)
}
```

### 2. Cache-Aware Audio Playback

`AudioPlayerService` streams tracks from the server. When a track is cached
locally, play from the cache URL instead.

**Files to modify:**

- `AudioPlayerService.swift` — Before building a server URL, check
  `audioCacheManager.isCached(uuid)`. If it returns a local URL, use
  `AVPlayer(url: localURL)` instead of the server URL.
- Need to pass `audioCacheManager` into `AudioPlayerService` (either via
  `configure()` or by reading from `AppState` at the call site).

### 3. Cache-Aware File Downloads

`FileDownloadManager` downloads files to `~/Documents/MusicPorter/<playlist>/`.
After downloading, also store in the audio cache for offline use.

**Files to modify:**

- `FileDownloadManager.swift` — After a successful download, call
  `audioCacheManager.storeFromFile(sourcePath, file:, playlistKey:)` to
  populate the cache from the downloaded file.
- Alternatively, before downloading, check `audioCacheManager.isCached(uuid)`.
  If cached, copy from cache to Documents instead of re-downloading from
  server.

### 4. Cache-Aware USB Export

`USBExportService` copies local files to USB. It could also copy from cache
when files aren't in Documents but are cached.

**Files to modify:**

- `LibraryView.swift` / `PipelineView.swift` — In `exportToFolder`, after
  collecting local files, also check the audio cache for any files not
  available locally. Use `audioCacheManager.copyToDestination(uuid, destPath)`
  to export cached files directly.

### 5. Background Prefetch Trigger

The `PrefetchEngine` exists but nothing invokes it. Decide when prefetch
should run:

**Option A — Manual trigger:**
Add a "Prefetch" button in Settings or Library that calls:

```swift
Task {
    guard let engine = appState.prefetchEngine,
          let cache = appState.metadataCache else { return }
    let playlists = vm.playlists.map(\.key)
    let result = await engine.prefetch(
        options: PrefetchOptions(playlists: playlists, profile: appState.activeProfile),
        metadataCache: cache)
}
```

**Option B — Auto-prefetch on connect:**
After `AppState.connect()` succeeds, fire a background prefetch for all
playlists. Use a low concurrency (2) to avoid saturating the connection.

**Option C — Both:**
Auto-prefetch on connect with a manual refresh button.

**Files to modify:**

- `AppState.swift` — Add a `startPrefetch()` method and optionally call it
  from `connect()`.
- A view (Settings or Library) — Add UI to trigger and show prefetch progress.

### 6. Cache Management UI

Users need visibility into cache usage and the ability to clear it.

**Add to SettingsView.swift:**

- Display total cache size: `await audioCacheManager.getTotalSize()`
- "Clear Cache" button: `await audioCacheManager.clearAll()` +
  `await metadataCache.clearAll()`
- Per-playlist cache status (optional): show cached/total counts per playlist

**Possible layout:**

```
Section("Cache") {
    LabeledContent("Cache Size", value: formattedSize)
    Button("Clear Cache", role: .destructive) { ... }
}
```

### 7. Profile Switching

`AppState.switchProfile(_:)` reinitializes cache services, but no view
calls it yet. The profile picker in SettingsView should call `switchProfile`
instead of directly setting `activeProfile`.

**Files to modify:**

- `SettingsView.swift` — Replace direct `activeProfile = newProfile`
  assignments with `appState.switchProfile(newProfile)`.

### 8. Cache Eviction Configuration (Optional)

Allow users to configure max cache size. Currently hardcoded at 10 GB via
`CacheConstants.defaultMaxCacheBytes`.

**Files to modify:**

- `SettingsView.swift` — Add a cache limit picker (1 GB, 5 GB, 10 GB, 20 GB,
  Unlimited).
- `AppState.swift` — Store the setting in UserDefaults, pass to
  `PrefetchOptions.maxCacheBytes`.

### 9. Playlist Pinning (Optional)

The eviction system supports pinned playlists (evicted last). This needs a
UI to let users pin/unpin playlists.

**Files to modify:**

- `LibraryView.swift` — Add a swipe action or context menu to pin/unpin.
- Store pinned set in UserDefaults.
- Pass pinned set to `PrefetchOptions.pinnedPlaylists`.

---

## Testing Checklist

After integration, verify:

- [ ] File list fetches use ETag — second fetch returns cached data (no network)
- [ ] `getPlaylists()` uses ETag — second call gets 304
- [ ] Audio playback serves from cache when available
- [ ] Downloads populate the audio cache
- [ ] USB export uses cached files when local downloads aren't available
- [ ] Prefetch downloads files into cache
- [ ] Cache size displays correctly in Settings
- [ ] Clear Cache removes all cached files and resets indexes
- [ ] Profile switching creates independent cache directories
- [ ] Eviction removes oldest/unpinned files when limit is exceeded
- [ ] App launches and connects without errors after cache changes
- [ ] Existing download, playback, and export flows still work unchanged

---

## File Summary

Files that need changes for full integration:

| File | Changes |
|------|---------|
| `PlaylistDetailViewModel.swift` | Use `getFilesWithETag` |
| `AudioPlayerService.swift` | Check cache before streaming |
| `FileDownloadManager.swift` | Populate cache after download; serve from cache |
| `LibraryView.swift` | Cache-aware export; prefetch trigger (optional) |
| `PipelineView.swift` | Cache-aware export |
| `SettingsView.swift` | Cache size display, clear button, profile switch, eviction config |
| `AppState.swift` | `startPrefetch()` method, cache limit setting |
