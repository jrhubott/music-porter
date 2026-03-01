import { useState, useEffect, useRef } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import type { FreshnessLevel, Playlist, PipelineProgress } from '@mporter/core';

// ── Constants ──

const BYTES_PER_MB = 1024 * 1024;
const BYTES_PER_GB = 1024 * 1024 * 1024;
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const PERCENT_MULTIPLIER = 100;
const APPLE_MUSIC_URL_PATTERN =
  /^https?:\/\/music\.apple\.com\/[a-z]{2}\/playlist\/([^/]+)\/[a-zA-Z0-9.]+/;

// ── Helpers ──

function formatSize(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(0)} MB`;
  return `${bytes} B`;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return '0m';
  const hours = Math.floor(seconds / SECONDS_PER_HOUR);
  const minutes = Math.floor((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function parseAppleMusicURL(url: string): { key: string; name: string } | null {
  const match = url.match(APPLE_MUSIC_URL_PATTERN);
  if (!match?.[1]) return null;
  const slug = match[1];
  const name = slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
  const key = slug.replace(/-/g, '_').toLowerCase();
  return { key, name };
}

function freshnessBadge(level?: FreshnessLevel): { className: string; label: string } {
  switch (level) {
    case 'current':
      return { className: 'bg-success', label: 'Current' };
    case 'recent':
      return { className: 'bg-info', label: 'Recent' };
    case 'stale':
      return { className: 'bg-warning text-dark', label: 'Stale' };
    case 'outdated':
      return { className: 'bg-danger', label: 'Outdated' };
    default:
      return { className: 'bg-secondary', label: 'Unknown' };
  }
}

function logLevelClass(level?: string): string {
  switch (level?.toUpperCase()) {
    case 'OK':
      return 'text-success';
    case 'WARN':
      return 'text-warning';
    case 'ERROR':
      return 'text-danger';
    case 'SKIP':
      return 'text-secondary';
    default:
      return 'text-info';
  }
}

// ── Component ──

export function SourcesPage() {
  const ipc = useIPC();
  const {
    playlists, setPlaylists, isOffline,
    isPipelining, setIsPipelining,
    pipelineTaskId, setPipelineTaskId,
    pipelineProgress, setPipelineProgress,
    pipelineLogs, appendPipelineLog, clearPipelineLogs,
  } = useAppState();

  // Add form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [addURL, setAddURL] = useState('');
  const [addName, setAddName] = useState('');
  const [addKey, setAddKey] = useState('');
  const [addError, setAddError] = useState('');
  const [addLoading, setAddLoading] = useState(false);

  // Edit state
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editURL, setEditURL] = useState('');
  const [editError, setEditError] = useState('');
  const [editLoading, setEditLoading] = useState(false);

  // Pipeline done result
  const [pipelineDone, setPipelineDone] = useState<PipelineProgress | null>(null);

  const logEndRef = useRef<HTMLDivElement>(null);

  // Load playlists on mount
  useEffect(() => {
    loadPlaylists();
  }, []);

  // Subscribe to pipeline progress
  useEffect(() => {
    const cleanup = ipc.onPipelineProgress((progress: PipelineProgress) => {
      if (progress.type === 'log') {
        appendPipelineLog(progress);
      } else if (progress.type === 'progress' || progress.type === 'overall_progress') {
        setPipelineProgress(progress);
      } else if (progress.type === 'done') {
        setIsPipelining(false);
        setPipelineTaskId(null);
        setPipelineProgress(null);
        setPipelineDone(progress);
        // Reload playlists to get updated stats
        loadPlaylists();
      }
    });
    return () => { cleanup(); };
  }, []);

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [pipelineLogs]);

  async function loadPlaylists() {
    try {
      const list = await ipc.getPlaylists();
      setPlaylists(list);
    } catch {
      // Non-critical
    }
  }

  // ── Add Playlist ──

  function handleURLChange(url: string) {
    setAddURL(url);
    setAddError('');
    const parsed = parseAppleMusicURL(url);
    if (parsed) {
      setAddName(parsed.name);
      setAddKey(parsed.key);
    }
  }

  async function handleAdd() {
    if (!addURL.trim()) {
      setAddError('URL is required');
      return;
    }
    const key = addKey.trim() || addName.trim().toLowerCase().replace(/\s+/g, '_');
    const name = addName.trim() || key;
    if (!key) {
      setAddError('Could not derive a key from the URL. Please enter a name.');
      return;
    }
    setAddLoading(true);
    setAddError('');
    try {
      await ipc.addPlaylist(key, addURL.trim(), name);
      setAddURL('');
      setAddName('');
      setAddKey('');
      setShowAddForm(false);
      await loadPlaylists();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : String(err));
    } finally {
      setAddLoading(false);
    }
  }

  // ── Edit Playlist ──

  function startEdit(p: Playlist) {
    setEditingKey(p.key);
    setEditName(p.name);
    setEditURL(p.url);
    setEditError('');
  }

  function cancelEdit() {
    setEditingKey(null);
    setEditError('');
  }

  async function handleSaveEdit() {
    if (!editingKey) return;
    setEditLoading(true);
    setEditError('');
    try {
      await ipc.updatePlaylist(editingKey, editURL.trim() || undefined, editName.trim() || undefined);
      setEditingKey(null);
      await loadPlaylists();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
    } finally {
      setEditLoading(false);
    }
  }

  // ── Pipeline ──

  async function handleProcess(playlistKey?: string) {
    clearPipelineLogs();
    setPipelineDone(null);
    setPipelineProgress(null);
    setIsPipelining(true);
    try {
      const result = await ipc.startPipeline(
        playlistKey ? { playlist: playlistKey } : { auto: true },
      );
      setPipelineTaskId(result.task_id);
    } catch (err) {
      setIsPipelining(false);
      appendPipelineLog({
        type: 'log',
        level: 'ERROR',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  async function handleCancel() {
    try {
      await ipc.cancelPipeline(pipelineTaskId ?? undefined);
    } catch {
      // Best-effort
    }
    // Aborting the SSE stream prevents the 'done' event from arriving,
    // so reset UI state directly after cancel.
    setIsPipelining(false);
    setPipelineTaskId(null);
    setPipelineProgress(null);
    setPipelineDone({ type: 'done', status: 'cancelled' });
  }

  // ── Render ──

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0">Sources</h4>
        {!isOffline && (
          <button className="btn btn-sm btn-outline-secondary" onClick={loadPlaylists}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        )}
      </div>

      {/* Apple Music Card */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>
            <i className="bi bi-music-note-beamed me-2" />
            Apple Music
          </span>
          {!isOffline && (
            <button
              className="btn btn-sm btn-outline-primary"
              onClick={() => setShowAddForm(!showAddForm)}
            >
              <i className={`bi ${showAddForm ? 'bi-x-lg' : 'bi-plus-lg'}`} />
            </button>
          )}
        </div>

        {/* Add form */}
        {showAddForm && (
          <div className="card-body border-bottom border-secondary">
            <div className="mb-2">
              <input
                type="text"
                className="form-control form-control-sm bg-dark text-light border-secondary"
                placeholder="Apple Music playlist URL"
                value={addURL}
                onChange={(e) => handleURLChange(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              />
            </div>
            {addName && (
              <div className="mb-2 d-flex gap-2">
                <input
                  type="text"
                  className="form-control form-control-sm bg-dark text-light border-secondary"
                  placeholder="Name"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                />
                <input
                  type="text"
                  className="form-control form-control-sm bg-dark text-light border-secondary"
                  placeholder="Key"
                  value={addKey}
                  onChange={(e) => setAddKey(e.target.value)}
                  style={{ maxWidth: '40%' }}
                />
              </div>
            )}
            {addError && <div className="text-danger small mb-2">{addError}</div>}
            <button
              className="btn btn-sm btn-primary"
              onClick={handleAdd}
              disabled={addLoading || !addURL.trim()}
            >
              {addLoading ? (
                <span className="spinner-border spinner-border-sm me-1" />
              ) : (
                <i className="bi bi-plus-lg me-1" />
              )}
              Add Playlist
            </button>
          </div>
        )}

        {/* Playlist list */}
        <div className="list-group list-group-flush">
          {playlists.length === 0 && (
            <div className="list-group-item bg-dark text-secondary">No playlists configured</div>
          )}
          {playlists.map((p) => (
            <div key={p.key} className="list-group-item bg-dark">
              {editingKey === p.key ? (
                /* Edit mode */
                <div>
                  <div className="mb-2 d-flex gap-2">
                    <input
                      type="text"
                      className="form-control form-control-sm bg-dark text-light border-secondary"
                      placeholder="Name"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                    />
                  </div>
                  <div className="mb-2">
                    <input
                      type="text"
                      className="form-control form-control-sm bg-dark text-light border-secondary"
                      placeholder="URL"
                      value={editURL}
                      onChange={(e) => setEditURL(e.target.value)}
                    />
                  </div>
                  {editError && <div className="text-danger small mb-2">{editError}</div>}
                  <div className="d-flex gap-2">
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={handleSaveEdit}
                      disabled={editLoading}
                    >
                      {editLoading ? (
                        <span className="spinner-border spinner-border-sm" />
                      ) : (
                        'Save'
                      )}
                    </button>
                    <button className="btn btn-sm btn-outline-secondary" onClick={cancelEdit}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                /* Display mode */
                <div className="d-flex justify-content-between align-items-center">
                  <div>
                    <div className="fw-bold text-light">{p.name}</div>
                    <small className="text-secondary">
                      <code>{p.key}</code>
                      {(p.file_count ?? 0) > 0 && (
                        <>
                          {' · '}
                          {p.file_count} files
                          {(p.size_bytes ?? 0) > 0 && ` · ${formatSize(p.size_bytes!)}`}
                          {(p.duration_s ?? 0) > 0 && ` · ${formatDuration(p.duration_s!)}`}
                        </>
                      )}
                      {p.freshness && (
                        <>
                          {' '}
                          <span className={`badge ${freshnessBadge(p.freshness).className}`} style={{ fontSize: '0.65em' }}>
                            {freshnessBadge(p.freshness).label}
                          </span>
                        </>
                      )}
                    </small>
                  </div>
                  {!isOffline && (
                    <div className="d-flex gap-1">
                      <button
                        className="btn btn-sm btn-outline-secondary"
                        onClick={() => startEdit(p)}
                        title="Edit"
                      >
                        <i className="bi bi-pencil" />
                      </button>
                      <button
                        className="btn btn-sm btn-outline-success"
                        onClick={() => handleProcess(p.key)}
                        disabled={isPipelining}
                        title="Run pipeline"
                      >
                        <i className="bi bi-play-fill" />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Process All button */}
        {playlists.length > 0 && !isOffline && (
          <div className="card-footer text-end">
            <button
              className="btn btn-sm btn-success"
              onClick={() => handleProcess()}
              disabled={isPipelining}
            >
              <i className="bi bi-play-fill me-1" />
              Process All
            </button>
          </div>
        )}
      </div>

      {/* Process Card — shown when pipeline active or has results */}
      {(isPipelining || pipelineLogs.length > 0 || pipelineDone) && (
        <div className="card bg-dark border-secondary">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>
              <i className="bi bi-gear me-2" />
              Process
            </span>
            {isPipelining && (
              <button className="btn btn-sm btn-outline-danger" onClick={handleCancel}>
                <i className="bi bi-x-lg me-1" />
                Cancel
              </button>
            )}
          </div>
          <div className="card-body">
            {/* Progress bars */}
            {isPipelining && pipelineProgress && (
              <div className="mb-3">
                <div className="d-flex justify-content-between align-items-center mb-1">
                  <small className="text-light">
                    {pipelineProgress.stage ?? 'Processing...'}
                  </small>
                  <small className="text-secondary">
                    {pipelineProgress.percent != null
                      ? `${Math.round(pipelineProgress.percent)}%`
                      : pipelineProgress.total
                        ? `${pipelineProgress.current ?? 0} / ${pipelineProgress.total}`
                        : ''}
                  </small>
                </div>
                <div className="progress" style={{ height: 6 }}>
                  <div
                    className="progress-bar bg-primary"
                    style={{
                      width: `${pipelineProgress.percent
                        ?? (pipelineProgress.total
                          ? ((pipelineProgress.current ?? 0) / pipelineProgress.total) * PERCENT_MULTIPLIER
                          : 0)}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {/* Done summary */}
            {pipelineDone && !isPipelining && (
              <div className="mb-3">
                <span
                  className={`badge ${pipelineDone.status === 'completed' ? 'bg-success' : pipelineDone.status === 'cancelled' ? 'bg-warning' : 'bg-danger'}`}
                >
                  {pipelineDone.status === 'completed'
                    ? 'Completed'
                    : pipelineDone.status === 'cancelled'
                      ? 'Cancelled'
                      : 'Failed'}
                </span>
                {pipelineDone.error && (
                  <span className="text-danger ms-2 small">{pipelineDone.error}</span>
                )}
              </div>
            )}

            {/* Log area */}
            {pipelineLogs.length > 0 && (
              <div
                className="bg-black rounded p-2"
                style={{ maxHeight: 300, overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.8rem' }}
              >
                {pipelineLogs.map((log, i) => (
                  <div key={i} className={logLevelClass(log.level)}>
                    <span className="text-secondary me-1">{log.level?.padEnd(5) ?? '     '}</span>
                    {log.message}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
