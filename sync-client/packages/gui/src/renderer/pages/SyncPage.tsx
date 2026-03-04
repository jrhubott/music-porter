import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import { LinkDestinationModal } from '../components/LinkDestinationModal.js';
import type { DriveInfo, Playlist, SyncDestination, SyncProgress } from '@mporter/core';

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;
const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const CACHE_NEAR_FULL_THRESHOLD = 0.9;

function formatBytes(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
  if (bytes >= BYTES_PER_KB) return `${Math.round(bytes / BYTES_PER_KB)} KB`;
  return `${bytes} B`;
}

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / MS_PER_SECOND);
  if (seconds < SECONDS_PER_MINUTE) return `${seconds}s`;
  const minutes = Math.floor(seconds / SECONDS_PER_MINUTE);
  const secs = seconds % SECONDS_PER_MINUTE;
  return `${minutes}m ${secs}s`;
}

function stripScheme(path: string): string {
  return path.replace(/^(usb|folder):\/\//, '');
}

export function SyncPage() {
  const ipc = useIPC();
  const {
    playlists,
    setPlaylists,
    selectedPlaylists,
    togglePlaylist,
    selectAllPlaylists,
    clearSelection,
    setSelectedPlaylists,
    serverProfiles,
    setServerProfiles,
    activeProfile,
    setActiveProfile,
    syncProgress,
    setSyncProgress,
    isSyncing,
    setIsSyncing,
    lastSyncResult,
    setLastSyncResult,
    drives,
    setDrives,
    selectedDrive,
    setSelectedDrive,
    destPath,
    setDestPath,
    destSyncStatus,
    setDestSyncStatus,
    isOffline,
    pinnedPlaylists,
    togglePin,
    setPinnedPlaylists,
    cacheStatuses,
    setCacheStatuses,
    cacheTotalSize,
    setCacheTotalSize,
    cacheMaxBytes,
    setCacheMaxBytes,
    autoPinNewPlaylists,
    setAutoPinNewPlaylists,
    backgroundPrefetchStatus,
  } = useAppState();

  const [autoSyncDrives, setAutoSyncDrives] = useState<string[]>([]);
  const [ejectAfterSync, setEjectAfterSync] = useState(false);
  const [ejected, setEjected] = useState(false);
  const [localDestinations, setLocalDestinations] = useState<SyncDestination[]>([]);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkTargetName, setLinkTargetName] = useState('');
  const [linkDestinations, setLinkDestinations] = useState<SyncDestination[]>([]);
  const [pendingLinkPath, setPendingLinkPath] = useState('');

  useEffect(() => {
    if (isOffline) {
      loadOfflineData();
    } else {
      loadData();
    }
    const cleanupSync = ipc.onSyncProgress((progress: SyncProgress) => {
      setSyncProgress(progress);
    });
    return () => { cleanupSync(); };
  }, []);

  // Refresh cache status when background prefetch completes
  useEffect(() => {
    if (backgroundPrefetchStatus && !backgroundPrefetchStatus.running && backgroundPrefetchStatus.lastResult) {
      loadCacheStatus();
    }
  }, [backgroundPrefetchStatus?.running]);

  async function loadOfflineData() {
    try {
      const [cached, pinned] = await Promise.all([
        ipc.cacheGetCachedPlaylists(),
        ipc.cacheGetPinnedPlaylists(),
      ]);
      setPinnedPlaylists(new Set(pinned));
      // Build pseudo-playlist list from cache
      const offlinePlaylists: Playlist[] = cached.map((c) => ({
        key: c.key,
        url: '',
        name: c.key,
        file_count: c.fileCount,
      }));
      setPlaylists(offlinePlaylists);
    } catch {
      // Handle error
    }
  }

  async function loadData() {
    try {
      const [playlistData, settingsData, prefs, savedProfile, pinned, autoPin, localDests] = await Promise.all([
        ipc.getPlaylists(),
        ipc.getSettings(),
        ipc.getPreferences(),
        ipc.getProfile(),
        ipc.cacheGetPinnedPlaylists(),
        ipc.cacheGetAutoPinNewPlaylists(),
        ipc.getLocalDestinations(),
      ]);
      setPlaylists(playlistData);
      setServerProfiles(settingsData.profiles);
      setAutoSyncDrives(prefs.autoSyncDrives);
      setEjectAfterSync(prefs.ejectAfterSync);
      setAutoPinNewPlaylists(autoPin);
      setLocalDestinations(localDests);

      // Sync pins with server when auto-pin is enabled
      const playlistKeys = playlistData.map((p) => p.key);
      const newlyPinned = await ipc.cacheSyncPins(playlistKeys);
      const allPinned = newlyPinned.length > 0
        ? [...new Set([...pinned, ...newlyPinned])]
        : pinned;
      setPinnedPlaylists(new Set(allPinned));

      // Restore active profile: saved > server default > first available
      if (!activeProfile) {
        const profileNames = Object.keys(settingsData.profiles);
        const resolved = savedProfile
          ?? (settingsData.settings['output_type'] as string | undefined)
          ?? profileNames[0]
          ?? '';
        if (resolved) {
          setActiveProfile(resolved);
          // Persist so background prefetch and other main-process consumers can see it
          if (!savedProfile) {
            await ipc.setProfile(resolved);
          }
        }
      }

      // Load cache status
      loadCacheStatus();
    } catch {
      // Handle error
    }
  }

  async function loadCacheStatus() {
    try {
      const status = await ipc.cacheGetStatus();
      setCacheTotalSize(status.totalSize);
      setCacheMaxBytes(status.maxCacheBytes);
      const statuses: Record<string, typeof cacheStatuses[string]> = {};
      for (const s of status.playlists) {
        statuses[s.playlistKey] = s;
      }
      setCacheStatuses(statuses);
    } catch {
      // Non-critical
    }
  }

  async function handleTogglePin(key: string) {
    togglePin(key);
    if (pinnedPlaylists.has(key)) {
      await ipc.cacheUnpin(key);
    } else {
      await ipc.cachePin(key);
    }
  }

  async function handleToggleAutoPin() {
    const newValue = !autoPinNewPlaylists;
    setAutoPinNewPlaylists(newValue);
    const newlyPinned = await ipc.cacheSetAutoPinNewPlaylists(newValue);
    if (newlyPinned.length > 0) {
      // Update pinned playlists state
      setPinnedPlaylists(new Set([...pinnedPlaylists, ...newlyPinned]));
      loadCacheStatus();
    }
  }

  async function toggleAutoSync(driveName: string) {
    const isEnabled = autoSyncDrives.includes(driveName);
    const updated = isEnabled
      ? autoSyncDrives.filter((d) => d !== driveName)
      : [...autoSyncDrives, driveName];
    setAutoSyncDrives(updated);
    await ipc.updatePreferences({ autoSyncDrives: updated });
  }

  async function toggleEjectAfterSync() {
    const updated = !ejectAfterSync;
    setEjectAfterSync(updated);
    await ipc.updatePreferences({ ejectAfterSync: updated });
  }

  async function ejectSelectedDrive() {
    if (!selectedDrive) return;
    const success = await ipc.ejectDrive(selectedDrive.path);
    if (success) {
      setEjected(true);
      setSelectedDrive(null);
      setDestPath('');
      setDestSyncStatus(null);
      const updated = await ipc.listDrives();
      setDrives(updated);
    }
  }

  // Resolve USB directory from active profile
  const profile = serverProfiles[activeProfile];
  const usbDir = profile?.usb_dir ?? '';

  async function loadSyncStatus(path: string, driveName?: string) {
    try {
      const destName = await ipc.resolveDestination(path, driveName);
      if (destName) {
        const status = await ipc.getSyncStatus(destName);
        setDestSyncStatus(status);
        // Auto-apply saved playlist prefs for this destination
        const destMeta = localDestinations.find((d) => d.name === destName);
        const prefs = destMeta?.playlist_prefs ?? status.playlist_prefs ?? null;
        if (prefs && prefs.length > 0) {
          setSelectedPlaylists(new Set(prefs));
        } else {
          clearSelection();
        }
      } else {
        setDestSyncStatus(null);
      }
    } catch {
      setDestSyncStatus(null);
      // Offline fallback: read local manifest for playlist pre-selection
      const keys = await ipc.readManifestPlaylistKeys(path).catch(() => []);
      if (keys.length > 0) {
        setSelectedPlaylists(new Set(keys));
      }
    }
  }

  function selectDrive(drive: DriveInfo) {
    setSelectedDrive(drive);
    const targetPath = usbDir ? `${drive.path}/${usbDir}` : drive.path;
    setDestPath(targetPath);
    loadSyncStatus(targetPath, drive.name);
  }

  async function selectFolder() {
    const path = await ipc.selectFolder();
    if (!path) return;

    setSelectedDrive(null);

    try {
      const destsResp = await ipc.getSyncDestinations();
      const folderPath = `folder://${path}`;
      const alreadyExists = destsResp.destinations.some((d) => d.path === folderPath);

      if (alreadyExists || destsResp.destinations.length === 0) {
        // Existing destination OR no other dests to link to — set path and create/find directly
        setDestPath(path);
        loadSyncStatus(path);
        setLocalDestinations(await ipc.getLocalDestinations());
        return;
      }

      // New destination AND other dests exist — defer creation and destPath, show link modal
      setPendingLinkPath(path);
      setLinkDestinations(destsResp.destinations);
      setLinkTargetName(path.split('/').pop() ?? path.split('\\').pop() ?? 'folder');
      setLinkModalOpen(true);
    } catch {
      setDestSyncStatus(null);
    }
  }

  async function handleLinkChoice(targetDest: string) {
    const destName = await ipc.resolveDestination(pendingLinkPath);
    if (!destName) throw new Error('Failed to create destination');
    await ipc.linkDestination(destName, targetDest);
    setLinkModalOpen(false);
    await loadSyncStatus(pendingLinkPath, selectedDrive?.name);
    const updatedDests = await ipc.getLocalDestinations();
    setLocalDestinations(updatedDests);
    setDestPath(pendingLinkPath);
    setPendingLinkPath('');
  }

  async function handleNoLink() {
    setLinkModalOpen(false);
    await loadSyncStatus(pendingLinkPath);
    const updatedDests = await ipc.getLocalDestinations();
    setLocalDestinations(updatedDests);
    setDestPath(pendingLinkPath);
    setPendingLinkPath('');
  }

  function handleCancelLink() {
    setLinkModalOpen(false);
    setPendingLinkPath('');
  }

  async function startSync(force = false) {
    if (!destPath) return;
    setIsSyncing(true);
    setLastSyncResult(null);
    setSyncProgress(null);
    setEjected(false);

    const syncDrive = selectedDrive;
    const selectedKeys = selectedPlaylists.size > 0 ? [...selectedPlaylists] : null;

    // Save playlist prefs before sync so they persist even if sync is aborted
    try {
      const destName = await ipc.resolveDestination(destPath, syncDrive?.name);
      if (destName) {
        await ipc.savePlaylistPrefs(destName, selectedKeys);
      }
    } catch {
      // Non-critical — proceed with sync even if pref save fails
    }

    try {
      const result = await ipc.startSync({
        dest: destPath,
        playlists: selectedKeys ?? undefined,
        usbDriveName: syncDrive?.name,
        profile: activeProfile || undefined,
        force,
        offlineOnly: isOffline,
      });
      setLastSyncResult(result);

      // Refresh local destinations after sync (server may have created/updated destinations)
      if (!result.aborted) {
        try {
          setLocalDestinations(await ipc.getLocalDestinations());
        } catch {
          // Non-critical
        }
      }

      // Auto-eject on successful USB sync when auto-sync or eject-after-sync is enabled
      const syncSucceeded = !result.aborted && result.failed === 0;
      const shouldAutoEject = syncDrive && syncSucceeded
        && (autoSyncDrives.includes(syncDrive.name) || ejectAfterSync);
      if (shouldAutoEject) {
        const success = await ipc.ejectDrive(syncDrive.path);
        if (success) {
          setEjected(true);
          setSelectedDrive(null);
          setDestPath('');
          setDestSyncStatus(null);
          const updated = await ipc.listDrives();
          setDrives(updated);
        }
      } else {
        // Refresh sync status so badges reflect the completed sync
        loadSyncStatus(destPath, syncDrive?.name);
      }
    } catch {
      // Error handled via progress
    }
    setIsSyncing(false);
    setSyncProgress(null);
  }

  async function cancelSync() {
    await ipc.cancelSync();
  }

  const progress = syncProgress;
  const progressPercent =
    progress && progress.total > 0 ? Math.round((progress.processed / progress.total) * 100) : 0;

  return (
    <div>
      {/* Offline banner */}
      {isOffline && (
        <div className="alert alert-warning py-2 mb-3">
          <i className="bi bi-cloud-slash me-2" />
          <strong>Offline Mode</strong> — Syncing from local cache only. Connect to server for full functionality.
        </div>
      )}

      {/* Header with profile badge and refresh */}
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div className="d-flex align-items-center gap-3">
          <h4 className="mb-0">Sync</h4>
          {activeProfile && (
            <span className="badge bg-secondary">
              <i className="bi bi-layers me-1" />
              {activeProfile}
              {usbDir && <span className="ms-1 opacity-75">({usbDir})</span>}
            </span>
          )}
          {cacheTotalSize > 0 && !isOffline && (() => {
            const cacheIncomplete = pinnedPlaylists.size > 0 && [...pinnedPlaylists].some((key) => {
              const status = cacheStatuses[key];
              const serverCount = playlists.find((p) => p.key === key)?.file_count ?? 0;
              return !status || status.cached < serverCount;
            });
            const cacheNearFull = cacheMaxBytes > 0
              && cacheTotalSize / cacheMaxBytes >= CACHE_NEAR_FULL_THRESHOLD;
            const badgeColor = cacheIncomplete
              ? 'text-danger'
              : cacheNearFull
                ? 'text-warning'
                : 'text-info';
            const bgColor = cacheIncomplete
              ? 'bg-danger'
              : cacheNearFull
                ? 'bg-warning'
                : 'bg-info';
            return (
              <span className={`badge ${bgColor} bg-opacity-25 ${badgeColor}`}>
                <i className="bi bi-database me-1" />
                {formatBytes(cacheTotalSize)} cached
              </span>
            );
          })()}
        </div>
        <div className="d-flex gap-2 align-items-center">
          <button className="btn btn-sm btn-outline-secondary" onClick={isOffline ? loadOfflineData : loadData}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
      </div>

      {/* Playlist selection */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>Playlists</span>
          <div className="d-flex gap-2 align-items-center">
            {!isOffline && (
              <div className="form-check form-switch mb-0">
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={autoPinNewPlaylists}
                  onChange={handleToggleAutoPin}
                />
                <label className="form-check-label small">
                  Auto-Pin New
                </label>
              </div>
            )}
            {selectedPlaylists.size > 0 ? (
              <button className="btn btn-sm btn-outline-secondary" onClick={clearSelection}>
                Clear ({selectedPlaylists.size})
              </button>
            ) : (
              <button className="btn btn-sm btn-outline-secondary" onClick={selectAllPlaylists}>
                Select All
              </button>
            )}
          </div>
        </div>
        <div className="card-body">
          {playlists.length === 0 ? (
            <div className="text-secondary text-center py-3">
              No playlists found on the server.
            </div>
          ) : (
            <div className="row g-2">
              {playlists.map((p) => {
                const cacheStatus = cacheStatuses[p.key];
                const isPinned = pinnedPlaylists.has(p.key);
                return (
                  <div key={p.key} className="col-md-6 col-lg-4">
                    <div
                      className={`playlist-card ${selectedPlaylists.has(p.key) ? 'selected' : ''}`}
                      onClick={() => togglePlaylist(p.key)}
                    >
                      <div className="d-flex align-items-center gap-2">
                        <input
                          type="checkbox"
                          className="form-check-input flex-shrink-0"
                          checked={selectedPlaylists.has(p.key)}
                          onChange={() => togglePlaylist(p.key)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="flex-grow-1" style={{ minWidth: 0 }}>
                          <div className="text-truncate fw-bold">{p.name}</div>
                          <div className="d-flex align-items-center gap-2 mt-1">
                            <small className="text-secondary flex-shrink-0">
                              {p.file_count ?? 0} {p.file_count === 1 ? 'file' : 'files'}
                            </small>
                            {(isPinned || (cacheStatus && cacheStatus.cached > 0)) && (() => {
                              const allCached = cacheStatus && cacheStatus.cached === (p.file_count ?? 0);
                              return (
                                <span
                                  className={`badge bg-info bg-opacity-25 flex-shrink-0 ${allCached ? 'text-info' : 'text-warning'}`}
                                  style={{ fontSize: '0.65em' }}
                                >
                                  {allCached
                                    ? 'cached'
                                    : `${cacheStatus?.cached ?? 0}`}
                                </span>
                              );
                            })()}
                          </div>
                        </div>
                        <button
                          className={`btn btn-sm flex-shrink-0 ${isPinned ? 'btn-info' : 'btn-outline-secondary'}`}
                          onClick={(e) => { e.stopPropagation(); handleTogglePin(p.key); }}
                          title={isPinned ? 'Unpin playlist' : 'Pin for offline caching'}
                        >
                          <i className={`bi ${isPinned ? 'bi-pin-fill' : 'bi-pin'}`} />
                        </button>
                      </div>
                      {!isOffline && (() => {
                        const syncInfo = destSyncStatus?.playlists.find(
                          (sp) => sp.name === p.key || sp.name === p.name,
                        );
                        if (!syncInfo) return null;
                        const s = syncInfo.sync_status;
                        if (s === 'skipped')
                          return <small className="text-muted d-block mt-1">skipped</small>;
                        if (s === 'new' || syncInfo.is_new_playlist)
                          return <small className="text-warning d-block mt-1">all new</small>;
                        if (syncInfo.new_files === 0)
                          return <small className="text-success d-block mt-1">synced</small>;
                        return <small className="text-info d-block mt-1">{syncInfo.new_files} new</small>;
                      })()}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Destination selector */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header">Destination</div>
        <div className="card-body">
          <div className="d-flex gap-2">
            {localDestinations.length > 0 ? (
              <select
                className="form-select bg-dark text-light border-secondary"
                value={destPath}
                onChange={(e) => {
                  const path = e.target.value;
                  if (path) {
                    setDestPath(path);
                    setSelectedDrive(null);
                    loadSyncStatus(path);
                  }
                }}
              >
                <option value="">Select a destination...</option>
                {localDestinations.map((d) => (
                  <option key={d.name} value={stripScheme(d.path)}>
                    {d.name} — {stripScheme(d.path)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                className="form-control bg-dark text-light border-secondary"
                placeholder="Select a folder or USB drive..."
                value={destPath}
                readOnly
              />
            )}
            <button className="btn btn-outline-secondary" onClick={selectFolder}>
              Browse
            </button>
          </div>
          {drives.length > 0 && (
            <div className="mt-2">
              <small className="text-secondary">USB Drives:</small>
              <div className="d-flex gap-1 mt-1 flex-wrap">
                {drives.map((d) => {
                  const targetPath = usbDir ? `${d.path}/${usbDir}` : d.path;
                  const isSelected = selectedDrive?.path === d.path;
                  const hasAutoSync = autoSyncDrives.includes(d.name);
                  return (
                    <button
                      key={d.path}
                      className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-outline-secondary'}`}
                      onClick={() => selectDrive(d)}
                      title={targetPath}
                    >
                      <i className="bi bi-usb-drive me-1" />
                      {d.name}
                      {hasAutoSync && <i className="bi bi-lightning-fill ms-1 text-warning" title="Auto-sync enabled" />}
                      {d.freeSpace !== undefined && (
                        <span className="ms-1 opacity-75">({formatBytes(d.freeSpace)})</span>
                      )}
                    </button>
                  );
                })}
              </div>
              {selectedDrive && (
                <div className="mt-2 d-flex align-items-center gap-3">
                  {usbDir && (
                    <small className="text-info">
                      <i className="bi bi-folder me-1" />
                      Files will sync to: {destPath}
                    </small>
                  )}
                  <div className="form-check form-switch mb-0">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      checked={autoSyncDrives.includes(selectedDrive.name)}
                      onChange={() => toggleAutoSync(selectedDrive.name)}
                    />
                    <label className="form-check-label small">
                      Auto-sync
                    </label>
                  </div>
                  <div className="form-check form-switch mb-0">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      checked={ejectAfterSync}
                      onChange={toggleEjectAfterSync}
                    />
                    <label className="form-check-label small">
                      Eject when done
                    </label>
                  </div>
                  <button
                    className="btn btn-sm btn-outline-warning"
                    onClick={ejectSelectedDrive}
                    disabled={isSyncing}
                  >
                    <i className="bi bi-eject-fill me-1" />
                    Eject
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Sync status */}
      {selectedPlaylists.size > 0 && (
        <div className="mb-3">
          <small className="text-secondary">
            Syncing {selectedPlaylists.size} playlist(s):{' '}
            {[...selectedPlaylists].join(', ')}
          </small>
        </div>
      )}

      {/* Sync options */}
      {/* Action buttons */}
      <div className="d-flex gap-2 mb-4">
        {isSyncing ? (
          <button className="btn btn-danger" onClick={cancelSync}>
            <i className="bi bi-stop-fill me-1" />
            Cancel
          </button>
        ) : (
          <>
            <button className="btn btn-primary" onClick={() => startSync()} disabled={!destPath}>
              <i className="bi bi-arrow-repeat me-1" />
              Start Sync{selectedPlaylists.size > 0 ? ` (${selectedPlaylists.size})` : ' All'}
            </button>
            <button
              className="btn btn-outline-warning"
              onClick={() => startSync(true)}
              disabled={!destPath}
              title="Re-download all files regardless of sync status"
            >
              <i className="bi bi-arrow-clockwise me-1" />
              Force Re-sync{selectedPlaylists.size > 0 ? ` (${selectedPlaylists.size})` : ' All'}
            </button>
          </>
        )}
      </div>

      {/* Progress */}
      {progress && (
        <div className="card bg-dark border-secondary mb-4">
          <div className="card-body">
            <div className="d-flex justify-content-between mb-2">
              <span>
                {progress.phase === 'discovering'
                  ? 'Discovering files...'
                  : `${progress.processed} / ${progress.total} files`}
              </span>
              <span>{progressPercent}%</span>
            </div>
            <div className="progress sync-progress-bar">
              <div
                className="progress-bar"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            {progress.file && (
              <small className="text-secondary mt-2 d-block text-truncate">
                {progress.subdir !== undefined
                  ? (progress.subdir ? `${progress.subdir}/${progress.file}` : progress.file)
                  : `${progress.playlist}/${progress.file}`}
              </small>
            )}
            <div className="d-flex gap-3 mt-2">
              <small className="text-success">Copied: {progress.copied}</small>
              <small className="text-info">Skipped: {progress.skipped}</small>
              {progress.failed > 0 && (
                <small className="text-danger">Failed: {progress.failed}</small>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Result */}
      {lastSyncResult && (
        <div
          className={`alert ${lastSyncResult.aborted ? 'alert-warning' : (lastSyncResult.failed > 0 || lastSyncResult.destError) ? 'alert-danger' : 'alert-success'}`}
        >
          <h6>{lastSyncResult.aborted ? 'Sync Aborted' : 'Sync Complete'}</h6>
          <div>Copied: {lastSyncResult.copied}</div>
          <div>Skipped: {lastSyncResult.skipped}</div>
          {lastSyncResult.failed > 0 && <div>Failed: {lastSyncResult.failed}</div>}
          <div>Duration: {formatDuration(lastSyncResult.durationMs)}</div>
          <div>Destination: {lastSyncResult.destinationName}</div>
          {lastSyncResult.destError && (
            <div className="mt-2 text-danger">
              <i className="bi bi-exclamation-triangle-fill me-1" />
              {lastSyncResult.destError}
            </div>
          )}
          {ejected && (
            <div className="mt-2 text-success">
              <i className="bi bi-eject-fill me-1" />
              Drive ejected
            </div>
          )}
          {selectedDrive && !ejected && (
            <button className="btn btn-sm btn-outline-warning mt-2" onClick={ejectSelectedDrive}>
              <i className="bi bi-eject me-1" />
              Eject {selectedDrive.name}
            </button>
          )}
        </div>
      )}

      <LinkDestinationModal
        show={linkModalOpen}
        folderName={linkTargetName}
        destinations={linkDestinations}
        onLink={handleLinkChoice}
        onNo={handleNoLink}
        onCancelled={handleCancelLink}
      />
    </div>
  );
}
