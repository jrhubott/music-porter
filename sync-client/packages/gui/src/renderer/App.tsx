import { useEffect } from 'react';
import { useAppState } from './store/app-state.js';
import { useIPC } from './hooks/useIPC.js';
import { ConnectPage } from './pages/ConnectPage.js';
import { PlaylistsPage } from './pages/PlaylistsPage.js';
import { SyncPage } from './pages/SyncPage.js';
import { DestinationsPage } from './pages/DestinationsPage.js';
import { SettingsPage } from './pages/SettingsPage.js';

const NAV_ITEMS = [
  { id: 'playlists', label: 'Playlists', icon: 'bi-music-note-list' },
  { id: 'sync', label: 'Sync', icon: 'bi-arrow-repeat' },
  { id: 'destinations', label: 'Destinations', icon: 'bi-hdd' },
  { id: 'settings', label: 'Settings', icon: 'bi-gear' },
];

export function App() {
  const { connection, setConnection, activePage, setActivePage, setDrives } = useAppState();
  const ipc = useIPC();

  useEffect(() => {
    // Try auto-connect on startup
    autoConnect();
    // Load drives
    ipc.listDrives().then(setDrives);
    // Watch drive changes
    const cleanup = ipc.onDriveChange(({ added, removed }) => {
      ipc.listDrives().then(setDrives);
    });
    return cleanup;
  }, []);

  async function autoConnect() {
    try {
      const state = await ipc.connect();
      if (state.connected) {
        setConnection(state);
        setActivePage('playlists');
      }
    } catch {
      // Not configured yet
    }
  }

  // Show connect page if not connected
  if (!connection.connected) {
    return (
      <div className="d-flex align-items-center justify-content-center" style={{ height: '100vh' }}>
        <ConnectPage />
      </div>
    );
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <nav className="app-sidebar">
        <div className="px-3 mb-3">
          <h6 className="text-light mb-0">Music Porter Sync</h6>
          {connection.serverName && (
            <small className="text-secondary">{connection.serverName}</small>
          )}
        </div>

        <ul className="nav flex-column">
          {NAV_ITEMS.map((item) => (
            <li key={item.id} className="nav-item">
              <button
                className={`nav-link ${activePage === item.id ? 'active' : ''}`}
                onClick={() => setActivePage(item.id)}
              >
                <i className={`bi ${item.icon}`} />
                {item.label}
              </button>
            </li>
          ))}
        </ul>

        {/* Connection status */}
        <div className="connection-badge">
          <span className="dot" />
          <span>
            {connection.type === 'external' ? (
              <>
                <i className="bi bi-globe me-1" />
                External
              </>
            ) : (
              <>
                <i className="bi bi-house me-1" />
                Local
              </>
            )}
          </span>
        </div>
      </nav>

      {/* Content */}
      <main className="app-content">
        {activePage === 'playlists' && <PlaylistsPage />}
        {activePage === 'sync' && <SyncPage />}
        {activePage === 'destinations' && <DestinationsPage />}
        {activePage === 'settings' && <SettingsPage />}
      </main>
    </div>
  );
}
