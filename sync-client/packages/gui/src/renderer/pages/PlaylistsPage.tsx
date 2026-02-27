import { useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';

export function PlaylistsPage() {
  const ipc = useIPC();
  const {
    playlists,
    setPlaylists,
    selectedPlaylists,
    togglePlaylist,
    selectAllPlaylists,
    clearSelection,
    setActivePage,
  } = useAppState();

  useEffect(() => {
    loadPlaylists();
  }, []);

  async function loadPlaylists() {
    try {
      const data = await ipc.getPlaylists();
      setPlaylists(data);
    } catch {
      // Handle error
    }
  }

  function syncSelected() {
    if (selectedPlaylists.size === 0) {
      selectAllPlaylists();
    }
    setActivePage('sync');
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0">Playlists</h4>
        <div className="d-flex gap-2">
          <button className="btn btn-sm btn-outline-secondary" onClick={loadPlaylists}>
            <i className="bi bi-arrow-clockwise me-1" />
            Refresh
          </button>
          {selectedPlaylists.size > 0 ? (
            <button className="btn btn-sm btn-outline-secondary" onClick={clearSelection}>
              Clear ({selectedPlaylists.size})
            </button>
          ) : (
            <button className="btn btn-sm btn-outline-secondary" onClick={selectAllPlaylists}>
              Select All
            </button>
          )}
          <button className="btn btn-sm btn-primary" onClick={syncSelected}>
            <i className="bi bi-arrow-repeat me-1" />
            Sync {selectedPlaylists.size > 0 ? `(${selectedPlaylists.size})` : 'All'}
          </button>
        </div>
      </div>

      {playlists.length === 0 ? (
        <div className="text-secondary text-center py-5">
          No playlists found on the server.
        </div>
      ) : (
        <div className="row g-3">
          {playlists.map((p) => (
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
                  <div>
                    <div className="fw-bold">{p.name}</div>
                    <small className="text-secondary">{p.key}</small>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
