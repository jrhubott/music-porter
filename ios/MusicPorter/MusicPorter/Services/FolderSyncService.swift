import Foundation

/// Result of a completed or cancelled folder sync operation.
struct FolderSyncResult {
    let success: Bool
    let filesCopied: Int
    let filesSkipped: Int
    let filesFailed: Int
    let totalFiles: Int
    let destinationName: String
    let message: String
}

/// Syncs server playlists to a user-selected folder (USB drive, external storage, etc.).
///
/// Uses cache-first strategy: copies locally cached files when available,
/// downloads from server as fallback. Writes a `.music-porter-sync.json`
/// manifest at the destination for incremental sync on subsequent runs.
@Observable @MainActor
final class FolderSyncService {
    var isSyncing = false
    var progress: Double = 0
    var currentFileName: String?
    var filesCopied = 0
    var filesSkipped = 0
    var filesFailed = 0
    var totalFiles = 0
    var lastResult: FolderSyncResult?
    var isCancelled = false

    private var syncTask: Task<Void, Never>?

    /// Cancel an in-progress sync.
    func cancel() {
        syncTask?.cancel()
        isCancelled = true
    }

    /// Reset transient state (progress, counters, last result).
    func reset() {
        lastResult = nil
        currentFileName = nil
        isCancelled = false
        filesCopied = 0
        filesSkipped = 0
        filesFailed = 0
        totalFiles = 0
        progress = 0
    }

    /// Sync `playlistKeys` to `destURL`. Awaits completion.
    ///
    /// - Parameters:
    ///   - destURL: Security-scoped folder URL chosen by the user.
    ///   - playlistKeys: Playlists to sync; pass empty array to sync all server playlists.
    ///   - api: Connected API client.
    ///   - audioCacheManager: Optional local audio cache for cache-first strategy.
    ///   - profile: Output profile name forwarded to the server download endpoint.
    ///   - forceResync: When true, ignore the manifest and re-copy every file.
    func sync(
        destURL: URL,
        playlistKeys: [String],
        api: APIClient,
        audioCacheManager: AudioCacheManager?,
        profile: String,
        forceResync: Bool = false
    ) async {
        isSyncing = true
        isCancelled = false
        filesCopied = 0
        filesSkipped = 0
        filesFailed = 0
        totalFiles = 0
        progress = 0

        let task = Task { [weak self] in
            guard let self else { return }
            await self.performSync(
                destURL: destURL,
                playlistKeys: playlistKeys,
                api: api,
                audioCacheManager: audioCacheManager,
                profile: profile,
                forceResync: forceResync
            )
        }
        syncTask = task
        await task.value
        syncTask = nil
        isSyncing = false
    }

    // MARK: - Private

    private func performSync(
        destURL: URL,
        playlistKeys: [String],
        api: APIClient,
        audioCacheManager: AudioCacheManager?,
        profile: String,
        forceResync: Bool
    ) async {
        let accessing = destURL.startAccessingSecurityScopedResource()
        defer { if accessing { destURL.stopAccessingSecurityScopedResource() } }

        // Resolve (or create) destination on server.
        let destName: String
        do {
            let response = try await api.resolveDestination(
                path: destURL.path,
                name: destURL.lastPathComponent
            )
            destName = response.destination.name
        } catch {
            lastResult = FolderSyncResult(
                success: false,
                filesCopied: 0,
                filesSkipped: 0,
                filesFailed: 0,
                totalFiles: 0,
                destinationName: destURL.lastPathComponent,
                message: "Failed to register destination: \(error.localizedDescription)"
            )
            return
        }

        // Read manifest (nil when force-resyncing or no manifest exists yet).
        let manifestFolderURL = destURL
        var manifest: SyncManifest = forceResync
            ? SyncManifest(
                destinationName: destName,
                serverOrigin: api.activeBaseURL?.absoluteString ?? "",
                lastSyncAt: CacheUtils.isoNow(),
                playlists: [:]
            )
            : (SyncManifest.read(from: manifestFolderURL) ?? SyncManifest(
                destinationName: destName,
                serverOrigin: api.activeBaseURL?.absoluteString ?? "",
                lastSyncAt: CacheUtils.isoNow(),
                playlists: [:]
            ))

        // Phase 1: Fetch all file lists and count total files.
        var allFiles: [(playlistKey: String, response: FileListResponse)] = []
        for playlistKey in playlistKeys {
            guard !Task.isCancelled && !isCancelled else { break }
            guard let response = try? await api.getFiles(playlist: playlistKey) else { continue }
            allFiles.append((playlistKey, response))
            totalFiles += response.files.count
        }

        // Phase 2: Process each playlist.
        for (playlistKey, response) in allFiles {
            guard !Task.isCancelled && !isCancelled else { break }

            let playlistDir = destURL.appendingPathComponent(playlistKey)
            do {
                try FileManager.default.createDirectory(at: playlistDir, withIntermediateDirectories: true)
            } catch {
                filesFailed += response.files.count
                updateProgress()
                continue
            }

            let manifestFiles = manifest.playlists[playlistKey]?.files ?? [:]
            var playlistSynced: [String] = []

            for track in response.files {
                guard !Task.isCancelled && !isCancelled else { break }

                let displayName = track.displayFilename ?? track.filename
                currentFileName = displayName
                let destFile = playlistDir.appendingPathComponent(displayName)
                let existsOnDisk = FileManager.default.fileExists(atPath: destFile.path)

                // Incremental skip: already in manifest and file is present on disk.
                if manifestFiles[displayName] != nil && existsOnDisk {
                    filesSkipped += 1
                    playlistSynced.append(displayName)
                    updateProgress()
                    continue
                }

                var written = false

                // Cache-first: try local audio cache.
                if let uuid = track.uuid, let cachedURL = await audioCacheManager?.isCached(uuid) {
                    do {
                        if existsOnDisk {
                            try FileManager.default.removeItem(at: destFile)
                        }
                        try FileManager.default.copyItem(at: cachedURL, to: destFile)
                        written = true
                    } catch {
                        // Fall through to server download.
                    }
                }

                // Server fallback: download from server.
                if !written {
                    do {
                        let data = try await api.downloadFileData(
                            playlist: playlistKey,
                            filename: track.filename,
                            profile: profile
                        )
                        if existsOnDisk {
                            try? FileManager.default.removeItem(at: destFile)
                        }
                        try data.write(to: destFile, options: .atomicWrite)
                        written = true
                    } catch {
                        filesFailed += 1
                        updateProgress()
                        continue
                    }
                }

                if written {
                    filesCopied += 1
                    playlistSynced.append(displayName)
                    // Update manifest entry for this file.
                    var entry = manifest.playlists[playlistKey] ?? SyncManifestPlaylist(files: [:])
                    entry.files[displayName] = Date().timeIntervalSince1970
                    manifest.playlists[playlistKey] = entry
                }

                updateProgress()
            }

            // Record sync to server for this playlist.
            if !playlistSynced.isEmpty {
                try? await api.recordClientSync(
                    destination: destName,
                    playlist: playlistKey,
                    files: playlistSynced,
                    destPath: destURL.path
                )
            }
        }

        // Write updated manifest.
        manifest.lastSyncAt = CacheUtils.isoNow()
        manifest.destinationName = destName
        manifest.write(to: manifestFolderURL)

        currentFileName = nil
        progress = 1.0

        let cancelled = isCancelled || Task.isCancelled
        let msg: String
        if cancelled {
            msg = "Sync cancelled — \(filesCopied) copied, \(filesSkipped) skipped"
        } else if filesFailed == 0 {
            msg = "Sync complete — \(filesCopied) copied, \(filesSkipped) skipped"
        } else {
            msg = "Sync complete — \(filesCopied) copied, \(filesSkipped) skipped, \(filesFailed) failed"
        }

        lastResult = FolderSyncResult(
            success: !cancelled && filesFailed == 0,
            filesCopied: filesCopied,
            filesSkipped: filesSkipped,
            filesFailed: filesFailed,
            totalFiles: filesCopied + filesSkipped + filesFailed,
            destinationName: destName,
            message: msg
        )
    }

    private func updateProgress() {
        guard totalFiles > 0 else { return }
        let processed = filesCopied + filesSkipped + filesFailed
        progress = Double(processed) / Double(totalFiles)
    }
}
