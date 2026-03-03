import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import { LinkDestinationModal } from '../components/LinkDestinationModal.js';

const BYTES_PER_GB = 1024 * 1024 * 1024;

function formatGB(bytes: number): string {
  return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
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
  const [linkTargetPath, setLinkTargetPath] = useState<string | undefined>();

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

  function openLinkModal(name: string, path?: string) {
    setLinkTargetName(name);
    setLinkTargetPath(path);
    setLinkModalOpen(true);
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
                    onClick={() => openLinkModal(d.name, d.path)}
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
                    <th>Last Sync</th>
                  </tr>
                </thead>
                <tbody>
                  {syncStatusSummary.map((s) => {
                    const groupLabel = s.destinations.join(', ');
                    const groupKey = groupLabel;
                    return (
                      <tr
                        key={groupKey}
                        className={`cursor-pointer ${selectedDestGroup === groupKey ? 'table-active' : ''}`}
                        onClick={() => handleSelectDestGroup(s.destinations[0]!)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <i className={`bi bi-chevron-${selectedDestGroup === groupKey ? 'down' : 'right'} me-1`} />
                          {groupLabel}
                        </td>
                        <td className="text-end">{s.total_files}</td>
                        <td className="text-end">{s.synced_files}</td>
                        <td className="text-end">
                          {s.new_files > 0 ? (
                            <span className="text-info">{s.new_files}</span>
                          ) : (
                            <span className="text-success">0</span>
                          )}
                        </td>
                        <td>
                          <small className="text-secondary">
                            {s.last_sync_at
                              ? new Date(s.last_sync_at * 1000).toLocaleString()
                              : 'Never'}
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
                        const badgeClass = p.is_new_playlist
                          ? 'bg-warning text-dark'
                          : p.new_files > 0
                            ? 'bg-info'
                            : 'bg-success';
                        const badgeText = p.is_new_playlist
                          ? 'Never synced'
                          : p.new_files > 0
                            ? `${p.new_files} new`
                            : 'Current';
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
        destinationName={linkTargetName}
        destinationPath={linkTargetPath}
        onClose={() => setLinkModalOpen(false)}
        onLinked={() => {
          loadDestinations();
          loadSyncStatusSummary();
        }}
      />
    </div>
  );
}
