import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import type { DriveInfo, Playlist, SyncProgress } from '@mporter/core';

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;
const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;

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

export function SyncPage() {
  const ipc = useIPC();
  const {
    playlists,
    setPlaylists,
    selectedPlaylists,
    togglePlaylist,
    selectAllPlaylists,
    clearSelection,
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
    autoPinNewPlaylists,
    setAutoPinNewPlaylists,
    backgroundPrefetchStatus,
  } = useAppState();

  const [destPath, setDestPath] = useState('');
  const [selectedDrive, setSelectedDrive] = useState<DriveInfo | null>(null);
  const [autoSyncDrives, setAutoSyncDrives] = useState<string[]>([]);
  const [ejectAfterSync, setEjectAfterSync] = useState(false);
  const [ejected, setEjected] = useState(false);

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
      const [playlistData, settingsData, prefs, savedProfile, pinned, autoPin] = await Promise.all([
        ipc.getPlaylists(),
        ipc.getSettings(),
        ipc.getPreferences(),
        ipc.getProfile(),
        ipc.cacheGetPinnedPlaylists(),
        ipc.cacheGetAutoPinNewPlaylists(),
      ]);
      setPlaylists(playlistData);
      setServerProfiles(settingsData.profiles);
      setAutoSyncDrives(prefs.autoSyncDrives);
      setEjectAfterSync(prefs.ejectAfterSync);
      setAutoPinNewPlaylists(autoPin);

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

  async function handlePrefetchNow() {
    // Trigger the background prefetch service (handles auto-pin sync, stale detection, etc.)
    await ipc.cacheTriggerPrefetch();
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
      const syncKey = await ipc.resolveSyncKey(path, driveName);
      if (syncKey) {
        const status = await ipc.getSyncStatus(syncKey);
        setDestSyncStatus(status);
      } else {
        setDestSyncStatus(null);
      }
    } catch {
      setDestSyncStatus(null);
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
    if (path) {
      setDestPath(path);
      setSelectedDrive(null);
      loadSyncStatus(path);
    }
  }

  async function startSync(force = false) {
    if (!destPath) return;
    setIsSyncing(true);
    setLastSyncResult(null);
    setSyncProgress(null);
    setEjected(false);

    const syncDrive = selectedDrive;
    try {
      const result = await ipc.startSync({
        dest: destPath,
        playlists: selectedPlaylists.size > 0 ? [...selectedPlaylists] : undefined,
        usbDriveName: syncDrive?.name,
        profile: activeProfile || undefined,
        force,
        offlineOnly: isOffline,
      });
      setLastSyncResult(result);

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
          {cacheTotalSize > 0 && !isOffline && (
            <span className="badge bg-info bg-opacity-25 text-info">
              <i className="bi bi-database me-1" />
              {formatBytes(cacheTotalSize)} cached
            </span>
          )}
        </div>
        <div className="d-flex gap-2 align-items-center">
          {!isOffline && pinnedPlaylists.size > 0 && (
            <button
              className="btn btn-sm btn-outline-info"
              onClick={handlePrefetchNow}
              disabled={backgroundPrefetchStatus?.running || isSyncing}
            >
              {backgroundPrefetchStatus?.running ? (
                <>
                  <span className="spinner-border spinner-border-sm me-1" />
                  Prefetching...
                </>
              ) : (
                <>
                  <i className="bi bi-cloud-download me-1" />
                  Prefetch Now
                </>
              )}
            </button>
          )}
          <button className="btn btn-sm btn-outline-secondary" onClick={isOffline ? loadOfflineData : loadData}>
            <i className="bi bi-arrow-clockwise me-1" />
            Refresh
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
                          className="form-check-input"
                          checked={selectedPlaylists.has(p.key)}
                          onChange={() => togglePlaylist(p.key)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="flex-grow-1">
                          <div className="d-flex align-items-center gap-1">
                            <span className="fw-bold">{p.name}</span>
                            {(isPinned || (cacheStatus && cacheStatus.cached > 0)) && (
                              <span className="badge bg-info bg-opacity-25 text-info" style={{ fontSize: '0.65em' }}>
                                {cacheStatus && cacheStatus.cached === (p.file_count ?? 0)
                                  ? 'cached'
                                  : `${cacheStatus?.cached ?? 0}/${p.file_count ?? '?'} cached`}
                              </span>
                            )}
                          </div>
                          <small className="text-secondary">
                            {p.file_count ?? 0} {p.file_count === 1 ? 'file' : 'files'}
                            {!isOffline && (() => {
                              const syncInfo = destSyncStatus?.playlists.find(
                                (sp) => sp.name === p.key || sp.name === p.name,
                              );
                              if (!syncInfo) return null;
                              if (syncInfo.new_files === 0)
                                return <span className="text-success ms-2">synced</span>;
                              if (syncInfo.is_new_playlist)
                                return <span className="text-warning ms-2">all new</span>;
                              return <span className="text-info ms-2">{syncInfo.new_files} new</span>;
                            })()}
                          </small>
                        </div>
                        <button
                          className={`btn btn-sm ${isPinned ? 'btn-info' : 'btn-outline-secondary'}`}
                          onClick={(e) => { e.stopPropagation(); handleTogglePin(p.key); }}
                          title={isPinned ? 'Unpin playlist' : 'Pin for offline caching'}
                        >
                          <i className={`bi ${isPinned ? 'bi-pin-fill' : 'bi-pin'}`} />
                        </button>
                      </div>
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
            <input
              type="text"
              className="form-control bg-dark text-light border-secondary"
              placeholder="Select a folder or USB drive..."
              value={destPath}
              onChange={(e) => {
                setDestPath(e.target.value);
                setSelectedDrive(null);
                setDestSyncStatus(null);
              }}
              readOnly
            />
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
          className={`alert ${lastSyncResult.aborted ? 'alert-warning' : lastSyncResult.failed > 0 ? 'alert-danger' : 'alert-success'}`}
        >
          <h6>{lastSyncResult.aborted ? 'Sync Aborted' : 'Sync Complete'}</h6>
          <div>Copied: {lastSyncResult.copied}</div>
          <div>Skipped: {lastSyncResult.skipped}</div>
          {lastSyncResult.failed > 0 && <div>Failed: {lastSyncResult.failed}</div>}
          <div>Duration: {formatDuration(lastSyncResult.durationMs)}</div>
          <div>Sync Key: {lastSyncResult.syncKey}</div>
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
    </div>
  );
}
