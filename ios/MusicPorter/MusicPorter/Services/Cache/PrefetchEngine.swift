import Foundation
import os

/// Downloads playlist files to the local cache (not to a destination).
///
/// Port of sync client's prefetch-engine.ts. Uses Swift structured concurrency
/// (TaskGroup) for concurrent downloads and Task cancellation for abort.
actor PrefetchEngine {
    private let apiClient: APIClient
    private let cacheManager: AudioCacheManager
    private let logger = Logger(subsystem: "com.musicporter", category: "PrefetchEngine")

    init(apiClient: APIClient, cacheManager: AudioCacheManager) {
        self.apiClient = apiClient
        self.cacheManager = cacheManager
    }

    /// Prefetch files for the given playlists into the local cache.
    func prefetch(
        options: PrefetchOptions,
        metadataCache: MetadataCache,
        onProgress: (@Sendable (PrefetchProgress) -> Void)? = nil
    ) async -> PrefetchResult {
        let startTime = ContinuousClock.now

        // Prune stale entries before starting
        let pruned = await cacheManager.pruneStaleEntries()
        if pruned > 0 {
            logger.info("Pruned \(pruned) stale cache entries")
        }

        // Discover files for all playlists
        var playlistFileList: [(key: String, files: [Track])] = []
        var grandTotal = 0

        for key in options.playlists {
            if Task.isCancelled { break }
            do {
                let response = try await apiClient.getFilesWithETag(
                    playlist: key,
                    profile: options.profile,
                    metadataCache: metadataCache
                )
                playlistFileList.append((key: key, files: response.files))
                grandTotal += response.files.count
            } catch {
                logger.warning("Skipping playlist \"\(key)\": \(error)")
            }
        }

        let hasLimit = options.maxCacheBytes > 0

        // Pre-filter: determine which files would be evicted anyway due to capacity
        var capacityExcluded = Set<String>()

        if hasLimit {
            // Deduplicate server files by UUID
            var seenUuids = Set<String>()
            var allFiles: [(uuid: String, size: Int, createdAt: Double)] = []
            for (_, files) in playlistFileList {
                for file in files {
                    guard let uuid = file.uuid, !seenUuids.contains(uuid) else { continue }
                    seenUuids.insert(uuid)
                    allFiles.append((uuid: uuid, size: file.size, createdAt: file.createdAt ?? 0))
                }
            }

            // Sort newest first (inverse of eviction order)
            allFiles.sort { $0.createdAt > $1.createdAt }

            // Files whose cumulative size exceeds the limit would be evicted anyway
            var cumulative: Int64 = 0
            for f in allFiles {
                cumulative += Int64(f.size)
                if cumulative > options.maxCacheBytes {
                    capacityExcluded.insert(f.uuid)
                }
            }
        }

        // Filter out already-cached files and capacity-excluded files
        var toDownload: [(key: String, file: Track)] = []
        var totalSkipped = 0
        var capacityCapped = 0

        for (key, files) in playlistFileList {
            for file in files {
                guard let uuid = file.uuid else { continue }
                if capacityExcluded.contains(uuid) {
                    capacityCapped += 1
                    continue
                }
                let cached = await cacheManager.isCached(uuid)
                var stale = false
                if cached != nil {
                    stale = await cacheManager.isStale(uuid: uuid, serverUpdatedAt: file.updatedAt)
                }
                if cached != nil && !stale {
                    totalSkipped += 1
                } else {
                    toDownload.append((key: key, file: file))
                }
            }
        }

        if hasLimit {
            let currentSize = await cacheManager.getTotalSize()
            let available = max(0, options.maxCacheBytes - currentSize)
            logger.info("Cache: \(CacheUtils.formatBytes(currentSize)) used / \(CacheUtils.formatBytes(options.maxCacheBytes)) limit (\(CacheUtils.formatBytes(available)) available)")
        }

        logger.info("Prefetch: \(toDownload.count) to download, \(totalSkipped) already cached\(capacityCapped > 0 ? ", \(capacityCapped) exceeded cache capacity" : "")")

        onProgress?(PrefetchProgress(
            phase: "syncing",
            playlist: nil,
            file: nil,
            processed: totalSkipped + capacityCapped,
            total: grandTotal,
            downloaded: 0,
            skipped: totalSkipped,
            failed: 0
        ))

        // Download with concurrency limit
        let downloaded = LockedCounter()
        let failed = LockedCounter()
        let processedCounter = LockedCounter(initial: totalSkipped + capacityCapped)
        var aborted = false
        var capacityReached = false
        let downloadedUuids = LockedSet()
        let pinnedPlaylists = options.pinnedPlaylists

        // Use a simple index-based approach with TaskGroup
        let downloadIndex = LockedCounter()
        let concurrency = min(options.concurrency, toDownload.count)

        if concurrency > 0 {
            await withTaskGroup(of: Void.self) { group in
                for _ in 0..<concurrency {
                    group.addTask { [self] in
                        while true {
                            if Task.isCancelled { return }
                            if capacityReached { return }

                            let idx = downloadIndex.increment() - 1
                            guard idx < toDownload.count else { return }
                            let item = toDownload[idx]

                            let success = await self.downloadToCache(
                                playlistKey: item.key,
                                file: item.file,
                                profile: options.profile
                            )

                            let currentProcessed = processedCounter.increment()
                            if success {
                                let currentDownloaded = downloaded.increment()
                                if let uuid = item.file.uuid {
                                    downloadedUuids.insert(uuid)
                                }

                                // Check if cache is now full
                                if hasLimit {
                                    let totalSize = await self.cacheManager.getTotalSize()
                                    if totalSize >= options.maxCacheBytes {
                                        // Step 1: evict unpinned files first
                                        if !pinnedPlaylists.isEmpty {
                                            let overage = totalSize - options.maxCacheBytes
                                            let freed = await self.cacheManager.evictUnpinnedBytes(
                                                targetBytes: overage,
                                                pinnedPlaylists: pinnedPlaylists
                                            )
                                            if freed > 0 {
                                                self.logger.info("Evicted \(CacheUtils.formatBytes(freed)) of unpinned cache to make room")
                                            }
                                        }
                                        // Step 2: if still over, evict oldest (skip this session's downloads)
                                        let sizeAfterUnpinned = await self.cacheManager.getTotalSize()
                                        if sizeAfterUnpinned >= options.maxCacheBytes {
                                            let overage = sizeAfterUnpinned - options.maxCacheBytes
                                            let freed = await self.cacheManager.evictOldestBytes(
                                                targetBytes: overage,
                                                protectedUuids: downloadedUuids.values()
                                            )
                                            if freed > 0 {
                                                self.logger.info("Evicted \(CacheUtils.formatBytes(freed)) of oldest cache to make room")
                                            }
                                        }
                                        // Check if still over limit after all eviction
                                        let finalSize = await self.cacheManager.getTotalSize()
                                        if finalSize >= options.maxCacheBytes {
                                            capacityReached = true
                                            let remaining = toDownload.count - (idx + 1)
                                            if remaining > 0 {
                                                capacityCapped += remaining
                                                _ = processedCounter.add(remaining)
                                                self.logger.info("Cache limit reached — skipping \(remaining) remaining files")
                                            }
                                        }
                                    }
                                }

                                onProgress?(PrefetchProgress(
                                    phase: "syncing",
                                    playlist: item.key,
                                    file: item.file.displayFilename ?? item.file.filename,
                                    processed: currentProcessed,
                                    total: grandTotal,
                                    downloaded: currentDownloaded,
                                    skipped: totalSkipped,
                                    failed: failed.value
                                ))
                            } else {
                                let currentFailed = failed.increment()
                                onProgress?(PrefetchProgress(
                                    phase: "syncing",
                                    playlist: item.key,
                                    file: item.file.displayFilename ?? item.file.filename,
                                    processed: currentProcessed,
                                    total: grandTotal,
                                    downloaded: downloaded.value,
                                    skipped: totalSkipped,
                                    failed: currentFailed
                                ))
                            }
                        }
                    }
                }
            }
        }

        aborted = Task.isCancelled

        // Post-download eviction
        if hasLimit && !capacityReached {
            let evicted = await cacheManager.evictToLimit(
                maxBytes: options.maxCacheBytes,
                pinnedPlaylists: pinnedPlaylists.isEmpty ? nil : pinnedPlaylists
            )
            if evicted > 0 {
                logger.info("Evicted \(CacheUtils.formatBytes(evicted)) to stay within cache limit")
            }
        }

        let finalPhase = aborted ? "aborted" : "complete"
        onProgress?(PrefetchProgress(
            phase: finalPhase,
            playlist: nil,
            file: nil,
            processed: processedCounter.value,
            total: grandTotal,
            downloaded: downloaded.value,
            skipped: totalSkipped,
            failed: failed.value
        ))

        let elapsed = ContinuousClock.now - startTime
        let durationMs = Int(elapsed.components.seconds * 1000
            + elapsed.components.attoseconds / 1_000_000_000_000_000)

        return PrefetchResult(
            downloaded: downloaded.value,
            skipped: totalSkipped,
            failed: failed.value,
            capacityCapped: capacityCapped,
            aborted: aborted,
            durationMs: durationMs
        )
    }

    // MARK: - Internal

    private func downloadToCache(
        playlistKey: String,
        file: Track,
        profile: String?
    ) async -> Bool {
        do {
            let data = try await apiClient.downloadFileData(
                playlist: playlistKey,
                filename: file.filename,
                profile: profile
            )
            await cacheManager.storeData(
                data,
                file: file,
                playlistKey: playlistKey,
                serverCreatedAt: file.createdAt,
                serverUpdatedAt: file.updatedAt
            )
            return true
        } catch {
            if Task.isCancelled { return false }
            logger.error("Prefetch failed for \(playlistKey)/\(file.filename): \(error)")
            return false
        }
    }
}

// MARK: - Thread-safe Counters

/// Simple thread-safe counter using os_unfair_lock for use in TaskGroup.
private final class LockedCounter: @unchecked Sendable {
    private var _value: Int
    private let lock = NSLock()

    init(initial: Int = 0) { _value = initial }

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return _value
    }

    /// Increment and return the new value.
    @discardableResult
    func increment() -> Int {
        lock.lock()
        defer { lock.unlock() }
        _value += 1
        return _value
    }

    /// Add amount and return the new value.
    @discardableResult
    func add(_ amount: Int) -> Int {
        lock.lock()
        defer { lock.unlock() }
        _value += amount
        return _value
    }
}

/// Thread-safe set of strings for tracking downloaded UUIDs.
private final class LockedSet: @unchecked Sendable {
    private var _values = Set<String>()
    private let lock = NSLock()

    func insert(_ value: String) {
        lock.lock()
        defer { lock.unlock() }
        _values.insert(value)
    }

    func values() -> Set<String> {
        lock.lock()
        defer { lock.unlock() }
        return _values
    }
}
