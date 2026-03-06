import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import { LinkDestinationModal } from '../components/LinkDestinationModal.js';
import type { SyncDestination } from '@mporter/core';

const BYTES_PER_GB = 1024 * 1024 * 1024;
const SECS_PER_HOUR = 3600;
const SECS_PER_DAY = 86400;
const SECS_PER_WEEK = 604800;
const SECS_PER_MONTH = 2592000;
const STALENESS_WARN_DAYS = 7;
const STALENESS_DANGER_DAYS = 30;

function formatGB(bytes: number): string {
  return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
}

function formatRelativeTime(ts: number): string {
  if (!ts) return 'Never';
  const age = Math.floor(Date.now() / 1000) - ts;
  if (age < 60) return 'just now';
  if (age < SECS_PER_HOUR) return `${Math.floor(age / 60)} min ago`;
  if (age < SECS_PER_DAY) return `${Math.floor(age / SECS_PER_HOUR)} hr ago`;
  if (age < SECS_PER_WEEK) return `${Math.floor(age / SECS_PER_DAY)} days ago`;
  if (age < SECS_PER_MONTH) return `${Math.floor(age / SECS_PER_WEEK)} wk ago`;
  return `${Math.floor(age / SECS_PER_MONTH)} mo ago`;
}

function getStalenessClass(ts: number): string {
  if (!ts) return 'text-secondary';
  const ageDays = (Date.now() / 1000 - ts) / SECS_PER_DAY;
  if (ageDays > STALENESS_DANGER_DAYS) return 'text-danger';
  if (ageDays > STALENESS_WARN_DAYS) return 'text-warning';
  return 'text-secondary';
}

export function DestinationsPage() {
  const ipc = useIPC();
  const {
    drives,
    setDrives,
    destinations,
    setDestinations,
    syncStatusSummary,
    setSyncStatusSummary,
    selectedDestGroup,
    setSelectedDestGroup,
    selectedDestGroupDetail,
    setSelectedDestGroupDetail,
  } = useAppState();

  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkTargetName, setLinkTargetName] = useState('');
  const [linkAvailableDestinations, setLinkAvailableDestinations] = useState<SyncDestination[]>([]);

  useEffect(() => {
    loadData();
    const cleanup = ipc.onDriveChange(() => {
      refreshDrives();
    });
    return () => { cleanup(); };
  }, []);

  async function loadData() {
    await Promise.all([loadDestinations(), refreshDrives(), loadSyncStatusSummary()]);
  }

  async function loadDestinations() {
    try {
      const response = await ipc.getSyncDestinations();
      setDestinations(response.destinations);
    } catch {
      // Handle error
    }
  }

  async function loadSyncStatusSummary() {
    try {
      const summary = await ipc.getSyncStatusSummary();
      setSyncStatusSummary(summary);
    } catch {
      // Handle error
    }
  }

  async function refreshDrives() {
    const d = await ipc.listDrives();
    setDrives(d);
  }

  async function ejectDrive(path: string) {
    const success = await ipc.ejectDrive(path);
    if (success) {
      refreshDrives();
    }
  }

  async function openLinkModal(name: string) {
    setLinkTargetName(name);
    try {
      const response = await ipc.getSyncDestinations();
      setLinkAvailableDestinations(response.destinations.filter((d) => d.name !== name));
    } catch {
      setLinkAvailableDestinations([]);
    }
    setLinkModalOpen(true);
  }

  async function handleLinkChoice(targetDest: string) {
    const result = await ipc.linkDestination(linkTargetName, targetDest);
    if (!result.ok) throw new Error('Failed to link destination');
    setLinkModalOpen(false);
    loadDestinations();
    loadSyncStatusSummary();
  }

  function handleCloseLink() {
    setLinkModalOpen(false);
  }

  async function handleUnlink(name: string) {
    try {
      await ipc.linkDestination(name, null);
      loadDestinations();
    } catch {
      // Handle error
    }
  }

  async function handleSelectDestGroup(destName: string) {
    if (selectedDestGroup === destName) {
      setSelectedDestGroup(null);
      setSelectedDestGroupDetail(null);
      return;
    }
    setSelectedDestGroup(destName);
    try {
      const detail = await ipc.getSyncStatus(destName);
      setSelectedDestGroupDetail(detail);
    } catch {
      setSelectedDestGroupDetail(null);
    }
  }

  return (
    <div>
      <h4 className="mb-4">Destinations</h4>

      {/* Detected Drives */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>
            <i className="bi bi-usb-drive me-2" />
            Detected Drives
          </span>
          <button className="btn btn-sm btn-outline-secondary" onClick={refreshDrives}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
        <div className="list-group list-group-flush">
          {drives.length === 0 && (
            <div className="list-group-item bg-dark text-secondary">No drives detected</div>
          )}
          {drives.map((d) => (
            <div key={d.path} className="list-group-item bg-dark d-flex justify-content-between align-items-center">
              <div>
                <div className="fw-bold text-light">{d.name}</div>
                <small className="text-secondary">
                  {d.path}
                  {d.freeSpace !== undefined && ` — ${formatGB(d.freeSpace)} free`}
                </small>
              </div>
              <button className="btn btn-sm btn-outline-warning" onClick={() => ejectDrive(d.path)}>
                <i className="bi bi-eject me-1" />
                Eject
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Saved Destinations */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>
            <i className="bi bi-folder me-2" />
            Saved Destinations (Server)
          </span>
          <button className="btn btn-sm btn-outline-secondary" onClick={loadDestinations}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
        <div className="list-group list-group-flush">
          {destinations.length === 0 && (
            <div className="list-group-item bg-dark text-secondary">
              No saved destinations on server
            </div>
          )}
          {destinations.map((d) => {
            const hasLinked = d.linked_destinations && d.linked_destinations.length > 0;
            return (
              <div key={d.name} className="list-group-item bg-dark d-flex justify-content-between align-items-center">
                <div>
                  <div className="fw-bold text-light">{d.name}</div>
                  <small className="text-secondary">
                    {d.path}
                    {hasLinked && (
                      <span className="badge bg-info bg-opacity-25 text-info ms-2">
                        linked with {d.linked_destinations.join(', ')}
                      </span>
                    )}
                  </small>
                </div>
                <div className="d-flex gap-1">
                  <button
                    className="btn btn-sm btn-outline-info"
                    onClick={() => openLinkModal(d.name)}
                    title="Link with another destination"
                  >
                    <i className="bi bi-link-45deg" />
                  </button>
                  {hasLinked && (
                    <button
                      className="btn btn-sm btn-outline-secondary"
                      onClick={() => handleUnlink(d.name)}
                      title="Unlink from group"
                    >
                      <i className="bi bi-x-lg" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sync Status Overview */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>
            <i className="bi bi-bar-chart me-2" />
            Sync Status Overview
          </span>
          <button className="btn btn-sm btn-outline-secondary" onClick={loadSyncStatusSummary}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
        <div className="card-body p-0">
          {syncStatusSummary.length === 0 ? (
            <div className="p-3 text-secondary">No destination groups found</div>
          ) : (
            <div className="table-responsive">
              <table className="table table-dark table-hover mb-0">
                <thead>
                  <tr>
                    <th>Destinations</th>
                    <th className="text-end">Total</th>
                    <th className="text-end">Synced</th>
                    <th className="text-end">New</th>
                    <th className="text-end">New PL</th>
                    <th>Last Sync</th>
                  </tr>
                </thead>
                <tbody>
                  {syncStatusSummary.map((s) => {
                    const groupLabel = s.destinations.join(', ');
                    const groupKey = groupLabel;
                    const pct = s.total_files > 0 ? Math.round(s.synced_files / s.total_files * 100) : 0;
                    const lastSyncAbs = s.last_sync_at
                      ? new Date(s.last_sync_at * 1000).toLocaleString()
                      : 'Never';
                    let statusBadge;
                    if (!s.last_sync_at) {
                      statusBadge = <span className="badge bg-danger">Never synced</span>;
                    } else if (s.new_playlists > 0) {
                      statusBadge = <span className="badge bg-warning text-dark">{s.new_playlists} new playlist(s)</span>;
                    } else if (s.new_files > 0) {
                      statusBadge = <span className="badge bg-info">{s.new_files} files behind</span>;
                    } else {
                      statusBadge = <span className="badge bg-success">Up to date</span>;
                    }
                    return (
                      <tr
                        key={groupKey}
                        className={`cursor-pointer ${selectedDestGroup === groupKey ? 'table-active' : ''}`}
                        onClick={() => handleSelectDestGroup(s.destinations[0]!)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <div>
                            <i className={`bi bi-chevron-${selectedDestGroup === groupKey ? 'down' : 'right'} me-1`} />
                            {groupLabel}
                          </div>
                          <div className="ms-3 mt-1">{statusBadge}</div>
                        </td>
                        <td className="text-end">{s.total_files}</td>
                        <td className="text-end">
                          {s.synced_files}{' '}
                          <small className="text-muted">({pct}%)</small>
                        </td>
                        <td className="text-end">
                          {s.new_files > 0 ? (
                            <span className="text-info">{s.new_files}</span>
                          ) : (
                            <span className="text-success">0</span>
                          )}
                        </td>
                        <td className="text-end">
                          {s.new_playlists > 0 ? (
                            <span className="badge bg-info">{s.new_playlists}</span>
                          ) : (
                            <span className="text-muted">0</span>
                          )}
                        </td>
                        <td>
                          <small className={getStalenessClass(s.last_sync_at)} title={lastSyncAbs}>
                            {formatRelativeTime(s.last_sync_at)}
                          </small>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Per-destination detail panel */}
          {selectedDestGroup && selectedDestGroupDetail && (
            <div className="border-top border-secondary p-3">
              <h6 className="text-light mb-3">
                <i className="bi bi-list-task me-2" />
                {selectedDestGroupDetail.destinations?.join(', ') ?? selectedDestGroup} — Per-Playlist Breakdown
              </h6>
              {selectedDestGroupDetail.playlists.length === 0 ? (
                <small className="text-secondary">No playlist data available.</small>
              ) : (
                <div className="table-responsive">
                  <table className="table table-dark table-sm mb-0">
                    <thead>
                      <tr>
                        <th>Playlist</th>
                        <th className="text-end">Synced</th>
                        <th className="text-end">Total</th>
                        <th className="text-end">New</th>
                        <th className="text-center">
                          {selectedDestGroupDetail.playlist_prefs ? 'Pref' : 'Pref (All)'}
                        </th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedDestGroupDetail.playlists.map((p) => {
                        const s = p.sync_status;
                        const badgeClass =
                          s === 'skipped' ? 'bg-secondary' :
                          (s === 'new' || p.is_new_playlist) ? 'bg-warning text-dark' :
                          (s === 'behind' || p.new_files > 0) ? 'bg-info' : 'bg-success';
                        const badgeText =
                          s === 'skipped' ? 'Skipped' :
                          (s === 'new' || p.is_new_playlist) ? 'Never synced' :
                          (s === 'behind' || p.new_files > 0) ? `${p.new_files} new` : 'Current';
                        const prefs = selectedDestGroupDetail.playlist_prefs;
                        const inPref = prefs ? prefs.includes(p.name) : null;
                        return (
                          <tr key={p.name}>
                            <td>{p.name}</td>
                            <td className="text-end">{p.synced_files}</td>
                            <td className="text-end">{p.total_files}</td>
                            <td className="text-end">{p.new_files}</td>
                            <td className="text-center">
                              {inPref === null ? (
                                <span className="text-muted">–</span>
                              ) : inPref ? (
                                <i className="bi bi-check-circle-fill text-success" title="In saved prefs" />
                              ) : (
                                <span className="text-muted">–</span>
                              )}
                            </td>
                            <td><span className={`badge ${badgeClass}`}>{badgeText}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <LinkDestinationModal
        show={linkModalOpen}
        folderName={linkTargetName}
        destinations={linkAvailableDestinations}
        onLink={handleLinkChoice}
        onNo={handleCloseLink}
        onCancelled={handleCloseLink}
      />
    </div>
  );
}
