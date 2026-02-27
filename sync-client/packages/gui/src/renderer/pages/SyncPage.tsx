import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import type { SyncProgress } from '@mporter/core';

const BYTES_PER_MB = 1024 * 1024;
const MS_PER_SECOND = 1000;

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / MS_PER_SECOND);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

export function SyncPage() {
  const ipc = useIPC();
  const {
    selectedPlaylists,
    syncProgress,
    setSyncProgress,
    isSyncing,
    setIsSyncing,
    lastSyncResult,
    setLastSyncResult,
    drives,
  } = useAppState();

  const [destPath, setDestPath] = useState('');
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    const cleanup = ipc.onSyncProgress((progress: SyncProgress) => {
      setSyncProgress(progress);
    });
    return cleanup;
  }, []);

  async function selectFolder() {
    const path = await ipc.selectFolder();
    if (path) setDestPath(path);
  }

  async function startSync() {
    if (!destPath) return;
    setIsSyncing(true);
    setLastSyncResult(null);
    setLogs([]);
    setSyncProgress(null);

    try {
      const result = await ipc.startSync({
        dest: destPath,
        playlists: selectedPlaylists.size > 0 ? [...selectedPlaylists] : undefined,
      });
      setLastSyncResult(result);
    } catch (err) {
      setLogs((prev) => [...prev, `Error: ${err instanceof Error ? err.message : err}`]);
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
      <h4 className="mb-4">Sync</h4>

      {/* Destination selector */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-body">
          <label className="form-label">Destination</label>
          <div className="d-flex gap-2">
            <input
              type="text"
              className="form-control bg-dark text-light border-secondary"
              placeholder="Select a folder..."
              value={destPath}
              onChange={(e) => setDestPath(e.target.value)}
              readOnly
            />
            <button className="btn btn-outline-secondary" onClick={selectFolder}>
              Browse
            </button>
          </div>
          {drives.length > 0 && (
            <div className="mt-2">
              <small className="text-secondary">Quick select:</small>
              <div className="d-flex gap-1 mt-1">
                {drives.map((d) => (
                  <button
                    key={d.path}
                    className="btn btn-sm btn-outline-secondary"
                    onClick={() => setDestPath(d.path)}
                  >
                    <i className="bi bi-usb-drive me-1" />
                    {d.name}
                  </button>
                ))}
              </div>
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
          <button className="btn btn-primary" onClick={startSync} disabled={!destPath}>
            <i className="bi bi-arrow-repeat me-1" />
            Start Sync
          </button>
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
                {progress.playlist}/{progress.file}
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
        </div>
      )}
    </div>
  );
}
