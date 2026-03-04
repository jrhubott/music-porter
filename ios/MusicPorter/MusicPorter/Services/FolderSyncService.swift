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
    ///   - playlistPrefs: Playlists to persist as preferences on the server. Pass `nil` to
    ///     indicate "sync all" (server stores `null`); pass an array for a specific selection.
    ///   - api: Connected API client.
    ///   - audioCacheManager: Optional local audio cache for cache-first strategy.
    ///   - profile: Output profile name forwarded to the server download endpoint.
    ///   - forceResync: When true, ignore the manifest and re-copy every file.
    func sync(
        destURL: URL,
        playlistKeys: [String],
        playlistPrefs: [String]?,
        api: APIClient,
        audioCacheManager: AudioCacheManager?,
        profile: String,
        forceResync: Bool = false,
        cleanDestination: Bool = false
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
            do {
                try await self.performSync(
                    destURL: destURL,
                    playlistKeys: playlistKeys,
                    playlistPrefs: playlistPrefs,
                    api: api,
                    audioCacheManager: audioCacheManager,
                    profile: profile,
                    forceResync: forceResync,
                    cleanDestination: cleanDestination
                )
            } catch {
                self.lastResult = FolderSyncResult(
                    success: false,
                    filesCopied: 0,
                    filesSkipped: 0,
                    filesFailed: 0,
                    totalFiles: 0,
                    destinationName: destURL.lastPathComponent,
                    message: "Sync failed: \(error.localizedDescription)"
                )
            }
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
        playlistPrefs: [String]?,
        api: APIClient,
        audioCacheManager: AudioCacheManager?,
        profile: String,
        forceResync: Bool,
        cleanDestination: Bool
    ) async throws {
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
            // Save playlist preferences to server (non-fatal if fails).
            try? await api.savePlaylistPrefs(destination: destName, playlistKeys: playlistPrefs)
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

        // Register sync run with server — required, throws if unreachable.
        let startTime = Date()
        let taskId = try await api.startSyncRun(
            destination: destName,
            playlistKeys: playlistKeys.isEmpty ? nil : playlistKeys,
            startedAt: startTime.timeIntervalSince1970
        )

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

        // Phase 1: Fetch all file lists (with profile for correct display_filename
        // and output_subdir) and count total files.
        var allFiles: [(playlistKey: String, response: FileListResponse)] = []
        for playlistKey in playlistKeys {
            guard !Task.isCancelled && !isCancelled else { break }
            guard let response = try? await api.getFiles(playlist: playlistKey, profile: profile) else { continue }
            allFiles.append((playlistKey, response))
            totalFiles += response.files.count
        }

        // Phase 2: Process each playlist.
        var syncedFileURLs = Set<URL>()
        for (playlistKey, response) in allFiles {
            guard !Task.isCancelled && !isCancelled else { break }

            let manifestFiles = manifest.playlists[playlistKey]?.files ?? [:]
            var playlistSynced: [String] = []

            for track in response.files {
                guard !Task.isCancelled && !isCancelled else { break }

                let displayName = track.displayFilename ?? track.filename
                currentFileName = displayName

                // Resolve destination directory from the profile's output_subdir.
                // Empty subdir means flat placement directly in destURL.
                let subdir = track.outputSubdir ?? ""
                let trackDestDir = subdir.isEmpty
                    ? destURL
                    : destURL.appendingPathComponent(subdir)
                let destFile = trackDestDir.appendingPathComponent(displayName)
                let existsOnDisk = FileManager.default.fileExists(atPath: destFile.path)

                // Incremental skip: already in manifest and file is present on disk.
                if manifestFiles[displayName] != nil && existsOnDisk {
                    filesSkipped += 1
                    syncedFileURLs.insert(destFile)
                    playlistSynced.append(displayName)
                    updateProgress()
                    continue
                }

                // Ensure destination directory exists (idempotent).
                do {
                    try FileManager.default.createDirectory(
                        at: trackDestDir, withIntermediateDirectories: true)
                } catch {
                    filesFailed += 1
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
                    syncedFileURLs.insert(destFile)
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
                    destPath: destURL.path,
                    taskId: taskId
                )
            }
        }

        // Scan-based destination cleanup (mirror mode).
        if cleanDestination && !(isCancelled || Task.isCancelled) {
            let fm = FileManager.default
            if let enumerator = fm.enumerator(
                at: destURL,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            ) {
                for case let fileURL as URL in enumerator
                    where fileURL.pathExtension.lowercased() == "mp3"
                {
                    if !syncedFileURLs.contains(fileURL) {
                        try? fm.removeItem(at: fileURL)
                    }
                }
            }
            removeEmptyDirectories(at: destURL, using: fm)
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

        // Notify server of sync completion (best-effort — non-fatal).
        let finalStatus = cancelled ? "cancelled" : (filesFailed > 0 && filesCopied == 0 ? "failed" : "completed")
        await api.completeSyncRun(
            taskId: taskId,
            status: finalStatus,
            filesCopied: filesCopied,
            filesSkipped: filesSkipped,
            filesFailed: filesFailed
        )

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

    /// Recursively removes empty subdirectories under `url`.
    private func removeEmptyDirectories(at url: URL, using fm: FileManager) {
        guard let contents = try? fm.contentsOfDirectory(
            at: url, includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return }
        for item in contents {
            var isDir: ObjCBool = false
            if fm.fileExists(atPath: item.path, isDirectory: &isDir), isDir.boolValue {
                removeEmptyDirectories(at: item, using: fm)
                if (try? fm.contentsOfDirectory(atPath: item.path))?.isEmpty == true {
                    try? fm.removeItem(at: item)
                }
            }
        }
    }
}
