import { useState, useEffect, useRef } from 'react';
import { useAppState } from './store/app-state.js';
import { useIPC } from './hooks/useIPC.js';
import { ConnectPage } from './pages/ConnectPage.js';
import { SyncPage } from './pages/SyncPage.js';
import { DestinationsPage } from './pages/DestinationsPage.js';
import { SettingsPage } from './pages/SettingsPage.js';
import type { SyncProgress } from '@mporter/core';

const NAV_ITEMS = [
  { id: 'sync', label: 'Sync', icon: 'bi-arrow-repeat' },
  { id: 'destinations', label: 'Destinations', icon: 'bi-hdd' },
  { id: 'settings', label: 'Settings', icon: 'bi-gear' },
];

const CACHE_UPDATED_DISMISS_MS = 5000;

export function App() {
  const {
    connection, setConnection, activePage, setActivePage, setDrives, activeProfile, isOffline,
    setPrefetchProgress, setBackgroundPrefetchStatus, backgroundPrefetchStatus,
    pinnedPlaylists, playlists, cacheStatuses, setCacheStatuses, setCacheTotalSize,
  } = useAppState();
  const ipc = useIPC();
  const [sidebarPrefetch, setSidebarPrefetch] = useState<SyncProgress | null>(null);
  const [cacheUpdated, setCacheUpdated] = useState(false);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function loadCacheStatuses() {
    try {
      const status = await ipc.cacheGetStatus();
      setCacheTotalSize(status.totalSize);
      const statuses: Record<string, (typeof cacheStatuses)[string]> = {};
      for (const s of status.playlists) {
        statuses[s.playlistKey] = s;
      }
      setCacheStatuses(statuses);
    } catch {
      // Non-critical
    }
  }

  useEffect(() => {
    // Try auto-connect on startup
    autoConnect();
    // Load drives
    ipc.listDrives().then(setDrives);
    // Load initial cache statuses
    loadCacheStatuses();
    // Watch drive changes
    const cleanupDrives = ipc.onDriveChange(() => {
      ipc.listDrives().then(setDrives);
    });
    // Prefetch progress listener (moved from SyncPage)
    const cleanupPrefetch = ipc.onPrefetchProgress((progress: SyncProgress) => {
      setPrefetchProgress(progress);
      setSidebarPrefetch(progress);
      if (progress.phase === 'complete' || progress.phase === 'aborted') {
        // Show "Cache updated" only if actual downloads happened
        if (progress.copied > 0) {
          setCacheUpdated(true);
          if (dismissTimer.current) clearTimeout(dismissTimer.current);
          dismissTimer.current = setTimeout(() => {
            setCacheUpdated(false);
            setSidebarPrefetch(null);
          }, CACHE_UPDATED_DISMISS_MS);
        } else {
          setSidebarPrefetch(null);
        }
        // Refresh cache statuses after prefetch completes
        loadCacheStatuses();
      }
    });
    // Background prefetch status listener (moved from SyncPage)
    const cleanupBgStatus = ipc.onBackgroundPrefetchStatus((status) => {
      setBackgroundPrefetchStatus(status);
      // Refresh cache statuses when background prefetch finishes
      if (!status.running && status.lastResult) {
        loadCacheStatuses();
      }
    });
    return () => { cleanupDrives(); cleanupPrefetch(); cleanupBgStatus(); };
  }, []);

  async function autoConnect() {
    try {
      const state = await ipc.connect();
      if (state.connected) {
        setConnection(state);
        setActivePage('sync');
      }
    } catch {
      // Not configured yet
    }
  }

  // Show connect page if not connected and not in offline mode
  if (!connection.connected && !isOffline) {
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
            <small className="text-secondary d-block">{connection.serverName}</small>
          )}
          {activeProfile && (
            <small className="text-info">
              <i className="bi bi-layers me-1" />
              {activeProfile}
            </small>
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

        {/* Bottom status area */}
        <div className="sidebar-status">
          {/* Sidebar prefetch indicator */}
          {sidebarPrefetch && sidebarPrefetch.phase === 'syncing' && (sidebarPrefetch.copied > 0 || sidebarPrefetch.total > sidebarPrefetch.skipped) && (
            <div className="sidebar-prefetch">
              <div className="d-flex justify-content-between align-items-center mb-1">
                <small className="text-info">
                  <i className="bi bi-cloud-download me-1" />
                  Caching
                </small>
                <small className="text-secondary">
                  {sidebarPrefetch.total > 0
                    ? Math.round((sidebarPrefetch.processed / sidebarPrefetch.total) * 100)
                    : 0}%
                </small>
              </div>
              <div className="progress" style={{ height: 3 }}>
                <div
                  className="progress-bar bg-info"
                  style={{
                    width: `${sidebarPrefetch.total > 0
                      ? (sidebarPrefetch.processed / sidebarPrefetch.total) * 100
                      : 0}%`,
                  }}
                />
              </div>
            </div>
          )}
          {cacheUpdated && (
            <div className="sidebar-prefetch">
              <small className="text-success">
                <i className="bi bi-check-circle me-1" />
                Cache updated
              </small>
            </div>
          )}
          {!sidebarPrefetch && !cacheUpdated && pinnedPlaylists.size > 0
            && backgroundPrefetchStatus?.lastResult
            && backgroundPrefetchStatus.lastResult.failed === 0
            && backgroundPrefetchStatus.lastResult.capacityCapped === 0
            && (backgroundPrefetchStatus.lastResult.skipped > 0
              || backgroundPrefetchStatus.lastResult.downloaded > 0)
            && [...pinnedPlaylists].every((key) => {
              const s = cacheStatuses[key];
              const serverTotal = playlists.find((p) => p.key === key)?.file_count ?? 0;
              return s && s.cached >= serverTotal;
            }) && (
            <div className="connection-badge">
              <span className="dot" />
              <span>
                <i className="bi bi-database-check me-1" />
                Cache good
              </span>
            </div>
          )}
          {!sidebarPrefetch && !cacheUpdated && pinnedPlaylists.size > 0
            && backgroundPrefetchStatus?.lastResult
            && (backgroundPrefetchStatus.lastResult.failed > 0
              || backgroundPrefetchStatus.lastResult.capacityCapped > 0
              || [...pinnedPlaylists].some((key) => {
                const s = cacheStatuses[key];
                const serverTotal = playlists.find((p) => p.key === key)?.file_count ?? 0;
                return !s || s.cached < serverTotal;
              })) && (
            <div className="connection-badge">
              <span className="dot disconnected" />
              <span>
                <i className="bi bi-database-exclamation me-1" />
                Cache incomplete
              </span>
            </div>
          )}

          {/* Connection status */}
          <div className="connection-badge">
            <span className={`dot${isOffline ? ' dot-warning' : ''}`} />
            <span>
              {isOffline ? (
                <>
                  <i className="bi bi-cloud-slash me-1" />
                  Offline
                </>
              ) : connection.type === 'external' ? (
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
        </div>
      </nav>

      {/* Content */}
      <main className="app-content">
        {activePage === 'sync' && <SyncPage />}
        {activePage === 'destinations' && <DestinationsPage />}
        {activePage === 'settings' && <SettingsPage />}
      </main>
    </div>
  );
}
