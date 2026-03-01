import { useState, useEffect } from 'react';
import type { AboutResponse, SyncPreferences, ServerConfig, CookieStatus, BackgroundPrefetchStatus, PlaylistCacheStatus } from '@mporter/core';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';

const MIN_CONCURRENCY = 1;
const MAX_CONCURRENCY = 8;
const BYTES_PER_GB = 1024 * 1024 * 1024;
const BYTES_PER_MB = 1024 * 1024;

const CACHE_SIZE_OPTIONS = [
  { label: '5 GB', value: 5 * BYTES_PER_GB },
  { label: '10 GB', value: 10 * BYTES_PER_GB },
  { label: '20 GB', value: 20 * BYTES_PER_GB },
  { label: '50 GB', value: 50 * BYTES_PER_GB },
  { label: 'Unlimited', value: 0 },
];

const VERSION_HEADER_REGEX = /^Version\s+(.+):$/;

interface ParsedVersion {
  header: string;
  bullets: string[];
}

function parseReleaseNotes(text: string): ParsedVersion[] {
  const lines = text.split('\n');
  const versions: ParsedVersion[] = [];
  let current: ParsedVersion | null = null;

  for (const line of lines) {
    const match = line.match(VERSION_HEADER_REGEX);
    if (match) {
      if (current) versions.push(current);
      current = { header: match[1]!, bullets: [] };
    } else if (line.startsWith('\u2022 ')) {
      current?.bullets.push(line.substring(2));
    } else if (line.trim() !== '') {
      current?.bullets.push(line);
    }
  }
  if (current) versions.push(current);
  return versions;
}

function formatCacheSize(bytes: number): string {
  if (bytes >= BYTES_PER_GB) return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
  if (bytes >= BYTES_PER_MB) return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
  return `${bytes} B`;
}

export function SettingsPage() {
  const ipc = useIPC();
  const {
    connection,
    setConnection,
    setActivePage,
    serverProfiles,
    setServerProfiles,
    activeProfile,
    setActiveProfile,
    isOffline,
    setIsOffline,
  } = useAppState();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [prefs, setPrefs] = useState<SyncPreferences | null>(null);
  const [version, setVersion] = useState('');
  const [cookieStatus, setCookieStatus] = useState<CookieStatus | null>(null);
  const [cookieRefreshing, setCookieRefreshing] = useState(false);
  const [cookieAlert, setCookieAlert] = useState<{ type: 'success' | 'danger'; message: string } | null>(null);
  const [cacheTotalSize, setCacheTotalSize] = useState(0);
  const [cacheClearing, setCacheClearing] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [reconnectError, setReconnectError] = useState('');
  const [bgPrefetchStatus, setBgPrefetchStatus] = useState<BackgroundPrefetchStatus | null>(null);
  const [cachePlaylistStatuses, setCachePlaylistStatuses] = useState<PlaylistCacheStatus[]>([]);
  const [autoPinEnabled, setAutoPinEnabled] = useState(false);
  const [availableDiskSpace, setAvailableDiskSpace] = useState<number | null>(null);
  const [releaseNotes, setReleaseNotes] = useState<AboutResponse | null>(null);
  const [notesLoading, setNotesLoading] = useState(false);

  useEffect(() => {
    loadSettings();
    const cleanup = ipc.onBackgroundPrefetchStatus((status: BackgroundPrefetchStatus) => {
      setBgPrefetchStatus(status);
    });
    return () => { cleanup(); };
  }, []);

  async function loadSettings() {
    const [cfg, p, ver] = await Promise.all([
      ipc.getServerConfig(),
      ipc.getPreferences(),
      ipc.getVersion(),
    ]);
    setConfig(cfg);
    setPrefs(p);
    setVersion(ver);

    // Load cache size and playlist breakdown (always available, even offline)
    try {
      const [cacheStatus, bgStatus, autoPin, diskSpace] = await Promise.all([
        ipc.cacheGetStatus(),
        ipc.cacheGetBackgroundPrefetchStatus(),
        ipc.cacheGetAutoPinNewPlaylists(),
        ipc.getDiskSpace(),
      ]);
      setCacheTotalSize(cacheStatus.totalSize);
      setCachePlaylistStatuses(cacheStatus.playlists);
      setBgPrefetchStatus(bgStatus);
      setAutoPinEnabled(autoPin);
      setAvailableDiskSpace(diskSpace);
    } catch {
      // Non-critical
    }

    // Fetch server profiles, saved profile, and cookie status (only when online)
    if (!isOffline) {
      try {
        const [settings, savedProfile, cookies] = await Promise.all([
          ipc.getSettings(),
          ipc.getProfile(),
          ipc.getCookieStatus(),
        ]);
        setServerProfiles(settings.profiles);
        setCookieStatus(cookies);
        if (!activeProfile) {
          const profileNames = Object.keys(settings.profiles);
          const resolved = savedProfile
            ?? (settings.settings['output_type'] as string | undefined)
            ?? profileNames[0]
            ?? '';
          if (resolved) setActiveProfile(resolved);
        }
      } catch {
        // Non-critical
      }

      // Fetch release notes (non-critical)
      setNotesLoading(true);
      try {
        const about = await ipc.getAbout();
        setReleaseNotes(about);
      } catch {
        // Non-critical — release notes are optional
      }
      setNotesLoading(false);
    }
  }

  async function disconnect() {
    await ipc.updateServerConfig({ name: '', localURL: '' });
    setConnection({ connected: false });
    setActivePage('connect');
  }

  async function updateConcurrency(value: number) {
    if (!prefs) return;
    const updated = { ...prefs, concurrency: value };
    setPrefs(updated);
    await ipc.updatePreferences({ concurrency: value });
  }

  async function changeProfile(name: string) {
    setActiveProfile(name);
    await ipc.setProfile(name);
  }

  async function removeAutoSyncDrive(driveName: string) {
    if (!prefs) return;
    const updated = {
      ...prefs,
      autoSyncDrives: prefs.autoSyncDrives.filter((d) => d !== driveName),
    };
    setPrefs(updated);
    await ipc.updatePreferences({ autoSyncDrives: updated.autoSyncDrives });
  }

  async function handleCookieRefresh() {
    setCookieRefreshing(true);
    setCookieAlert(null);
    try {
      const result = await ipc.refreshCookies();
      if (result.success && result.valid) {
        const daysMsg = result.days_remaining != null
          ? ` (${result.days_remaining} days remaining)`
          : '';
        setCookieAlert({ type: 'success', message: `Cookies refreshed successfully${daysMsg}` });
        setCookieStatus({
          valid: true,
          exists: true,
          reason: result.reason ?? 'Valid',
          days_remaining: result.days_remaining ?? null,
        });
      } else {
        setCookieAlert({ type: 'danger', message: result.error ?? 'Cookie refresh failed' });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCookieAlert({ type: 'danger', message });
    } finally {
      setCookieRefreshing(false);
    }
  }

  async function goOffline() {
    setIsOffline(true);
    setConnection({ connected: false });
    await ipc.goOffline();
  }

  async function reconnect() {
    setReconnecting(true);
    setReconnectError('');
    try {
      const state = await ipc.connect();
      if (state.connected) {
        setConnection(state);
        setIsOffline(false);
        loadSettings();
      } else {
        setReconnectError('Connection failed. Server may be unreachable.');
      }
    } catch (err) {
      setReconnectError(err instanceof Error ? err.message : 'Connection failed');
    }
    setReconnecting(false);
  }

  async function handleClearCache() {
    setCacheClearing(true);
    try {
      await ipc.cacheClearAll();
      setCacheTotalSize(0);
    } catch {
      // Non-critical
    }
    setCacheClearing(false);
  }

  async function handleToggleAutoPin() {
    const newValue = !autoPinEnabled;
    setAutoPinEnabled(newValue);
    await ipc.cacheSetAutoPinNewPlaylists(newValue);
  }

  async function handleSetMaxCacheSize(value: number) {
    if (!prefs) return;
    const updated = { ...prefs, maxCacheBytes: value };
    setPrefs(updated);
    await ipc.cacheSetMaxSize(value);
    // Reload cache size (eviction may have reduced it)
    try {
      const status = await ipc.cacheGetStatus();
      setCacheTotalSize(status.totalSize);
    } catch {
      // Non-critical
    }
  }

  const profileNames = Object.keys(serverProfiles).sort();

  return (
    <div style={{ maxWidth: 600 }}>
      <h4 className="mb-4">Settings</h4>

      {/* Server Connection */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header">Server Connection</div>
        <div className="card-body">
          {config && (
            <>
              {config.name && (
                <div className="mb-2">
                  <small className="text-secondary">Name</small>
                  <div>{config.name}</div>
                </div>
              )}
              <div className="mb-2">
                <small className="text-secondary">Connection</small>
                <div className="d-flex align-items-center gap-2">
                  {connection.type === 'external' ? (
                    <i className="bi bi-globe text-primary" />
                  ) : (
                    <i className="bi bi-house text-success" />
                  )}
                  <span>
                    {connection.type === 'external'
                      ? 'Connected via External URL'
                      : 'Connected via Local Network'}
                  </span>
                </div>
              </div>
              <div className="mb-2">
                <small className="text-secondary">Local URL</small>
                <div className="font-monospace small">{config.localURL}</div>
              </div>
              {config.externalURL && (
                <div className="mb-2">
                  <small className="text-secondary">External URL</small>
                  <div className="font-monospace small">{config.externalURL}</div>
                </div>
              )}
              {connection.activeURL && (
                <div className="mb-3">
                  <small className="text-secondary">Active URL</small>
                  <div className="font-monospace small">{connection.activeURL}</div>
                </div>
              )}
            </>
          )}
          <div className="d-flex gap-2">
            {isOffline ? (
              <>
                <button
                  className="btn btn-outline-primary btn-sm"
                  onClick={reconnect}
                  disabled={reconnecting}
                >
                  {reconnecting ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-1" />
                      Reconnecting...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-wifi me-1" />
                      Reconnect
                    </>
                  )}
                </button>
                {reconnectError && (
                  <span className="text-danger small align-self-center">{reconnectError}</span>
                )}
              </>
            ) : (
              <>
                <button className="btn btn-outline-secondary btn-sm" onClick={goOffline}>
                  <i className="bi bi-cloud-slash me-1" />
                  Go Offline
                </button>
                <button className="btn btn-outline-danger btn-sm" onClick={disconnect}>
                  Disconnect
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Apple Music Authentication — hide when offline */}
      {!isOffline && (
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header">Apple Music Authentication</div>
        <div className="card-body">
          {cookieStatus ? (
            <div className="d-flex align-items-center gap-2 mb-3">
              {cookieStatus.valid ? (
                <>
                  <i className="bi bi-check-circle-fill text-success" />
                  <span>Cookies valid</span>
                  {cookieStatus.days_remaining != null && (
                    <span className="text-secondary small">
                      ({cookieStatus.days_remaining} days remaining)
                    </span>
                  )}
                </>
              ) : (
                <>
                  <i className="bi bi-exclamation-triangle-fill text-warning" />
                  <span className="text-warning">
                    {cookieStatus.exists ? 'Cookies expired or invalid' : 'No cookies configured'}
                  </span>
                </>
              )}
            </div>
          ) : (
            <div className="text-secondary small mb-3">Loading cookie status...</div>
          )}

          {cookieAlert && (
            <div className={`alert alert-${cookieAlert.type} py-2 mb-3`} role="alert">
              {cookieAlert.message}
            </div>
          )}

          {cookieRefreshing ? (
            <button
              className="btn btn-outline-danger btn-sm"
              onClick={() => ipc.cancelCookieRefresh()}
            >
              <i className="bi bi-x-circle me-1" />
              Cancel
            </button>
          ) : (
            <button
              className="btn btn-outline-primary btn-sm"
              onClick={handleCookieRefresh}
            >
              {cookieStatus?.valid ? 'Refresh Cookies' : 'Sign In to Apple Music'}
            </button>
          )}
        </div>
      </div>
      )}

      {/* Output Profile */}
      {profileNames.length > 0 && (
        <div className="card bg-dark border-secondary mb-4">
          <div className="card-header">Output Profile</div>
          <div className="card-body">
            <select
              className="form-select bg-dark text-light border-secondary"
              value={activeProfile}
              onChange={(e) => changeProfile(e.target.value)}
            >
              {profileNames.map((name) => (
                <option key={name} value={name}>
                  {name} — {serverProfiles[name]?.description}
                </option>
              ))}
            </select>
            {activeProfile && serverProfiles[activeProfile]?.usb_dir && (
              <small className="text-secondary mt-2 d-block">
                <i className="bi bi-usb-drive me-1" />
                USB directory: {serverProfiles[activeProfile]!.usb_dir}
              </small>
            )}
          </div>
        </div>
      )}

      {/* Sync Preferences */}
      {prefs && (
        <div className="card bg-dark border-secondary mb-4">
          <div className="card-header">Sync Preferences</div>
          <div className="card-body">
            <div className="mb-3">
              <label className="form-label">Parallel Downloads</label>
              <input
                type="range"
                className="form-range"
                min={MIN_CONCURRENCY}
                max={MAX_CONCURRENCY}
                value={prefs.concurrency}
                onChange={(e) => updateConcurrency(parseInt(e.target.value, 10))}
              />
              <small className="text-secondary">{prefs.concurrency} concurrent downloads</small>
            </div>

            {/* Per-drive auto-sync */}
            <div>
              <label className="form-label">Auto-Sync Drives</label>
              {prefs.autoSyncDrives.length === 0 ? (
                <div className="text-secondary small">
                  No drives configured for auto-sync. Select a USB drive during sync to enable.
                </div>
              ) : (
                <div className="d-flex flex-column gap-1">
                  {prefs.autoSyncDrives.map((driveName) => (
                    <div
                      key={driveName}
                      className="d-flex justify-content-between align-items-center border border-secondary rounded px-2 py-1"
                    >
                      <span>
                        <i className="bi bi-usb-drive me-1" />
                        {driveName}
                      </span>
                      <button
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => removeAutoSyncDrive(driveName)}
                        title="Remove auto-sync"
                      >
                        <i className="bi bi-x" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Local Cache */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header">Local Cache</div>
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <small className="text-secondary">Cache Size</small>
              <div>{formatCacheSize(cacheTotalSize)}</div>
            </div>
            <div className="d-flex gap-2">
              <button
                className="btn btn-outline-info btn-sm"
                onClick={() => ipc.cacheTriggerPrefetch()}
                disabled={bgPrefetchStatus?.running || false}
              >
                {bgPrefetchStatus?.running ? (
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
              <button
                className="btn btn-outline-danger btn-sm"
                onClick={handleClearCache}
                disabled={cacheClearing || cacheTotalSize === 0}
              >
                {cacheClearing ? (
                  <span className="spinner-border spinner-border-sm" />
                ) : (
                  <>
                    <i className="bi bi-trash me-1" />
                    Clear Cache
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Background prefetch status */}
          {bgPrefetchStatus && (
            <div className="mb-3 p-2 border border-secondary rounded">
              <div className="d-flex justify-content-between align-items-center mb-1">
                <small className="fw-bold">Background Prefetch</small>
                <span className={`badge ${bgPrefetchStatus.running ? 'bg-info' : 'bg-secondary'}`}>
                  {bgPrefetchStatus.running ? 'Active' : 'Idle'}
                </span>
              </div>
              {bgPrefetchStatus.running && bgPrefetchStatus.progress && (
                <div className="mb-1">
                  <div className="d-flex justify-content-between">
                    <small className="text-info">
                      {bgPrefetchStatus.playlist && `Caching ${bgPrefetchStatus.playlist}: `}
                      {bgPrefetchStatus.progress.current} / {bgPrefetchStatus.progress.total}
                    </small>
                    <small>
                      {bgPrefetchStatus.progress.total > 0
                        ? Math.round((bgPrefetchStatus.progress.current / bgPrefetchStatus.progress.total) * 100)
                        : 0}%
                    </small>
                  </div>
                  <div className="progress mt-1" style={{ height: 3 }}>
                    <div
                      className="progress-bar bg-info"
                      style={{
                        width: `${bgPrefetchStatus.progress.total > 0
                          ? (bgPrefetchStatus.progress.current / bgPrefetchStatus.progress.total) * 100
                          : 0}%`,
                      }}
                    />
                  </div>
                </div>
              )}
              {bgPrefetchStatus.lastRunAt && (
                <small className="text-secondary">
                  Last run: {new Date(bgPrefetchStatus.lastRunAt).toLocaleTimeString()}
                  {bgPrefetchStatus.lastResult && (
                    <span className="ms-2">
                      ({bgPrefetchStatus.lastResult.downloaded} downloaded, {bgPrefetchStatus.lastResult.skipped} cached)
                    </span>
                  )}
                </small>
              )}
            </div>
          )}

          {/* Per-playlist cache breakdown */}
          {cachePlaylistStatuses.length > 0 && (
            <div className="mb-3">
              <small className="text-secondary fw-bold d-block mb-1">Per-Playlist Cache</small>
              {cachePlaylistStatuses.map((ps) => (
                <div key={ps.playlistKey} className="d-flex align-items-center gap-2 mb-1">
                  <i className={`bi ${ps.pinned ? 'bi-pin-fill text-info' : 'bi-pin text-secondary'}`} style={{ fontSize: '0.75em' }} />
                  <span className="small flex-grow-1 text-truncate">{ps.playlistKey}</span>
                  <small className="text-secondary text-nowrap">{ps.cached}{ps.total > 0 ? `/${ps.total}` : ''}</small>
                  {ps.total > 0 && (
                    <div className="progress flex-shrink-0" style={{ width: 60, height: 3 }}>
                      <div
                        className={`progress-bar ${ps.cached >= ps.total ? 'bg-success' : 'bg-info'}`}
                        style={{ width: `${ps.total > 0 ? (ps.cached / ps.total) * 100 : 0}%` }}
                      />
                    </div>
                  )}
                  {ps.cached > 0 && (
                    <button
                      className="btn btn-sm btn-outline-danger p-0 d-flex align-items-center justify-content-center"
                      style={{ width: 20, height: 20, fontSize: '0.65em' }}
                      title={`Clear cache for ${ps.playlistKey}`}
                      onClick={async () => {
                        await ipc.cacheClearPlaylist(ps.playlistKey);
                        const status = await ipc.cacheGetStatus();
                        setCacheTotalSize(status.totalSize);
                        setCachePlaylistStatuses(status.playlists);
                      }}
                    >
                      <i className="bi bi-trash" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Auto-pin toggle */}
          <div className="form-check form-switch mb-3">
            <input
              className="form-check-input"
              type="checkbox"
              checked={autoPinEnabled}
              onChange={handleToggleAutoPin}
            />
            <label className="form-check-label">
              Auto-Pin New Playlists
            </label>
            <div className="text-secondary small">Automatically pin new playlists for caching as they appear on the server</div>
          </div>

          {prefs && (
            <div>
              <label className="form-label">Max Cache Size</label>
              <select
                className="form-select bg-dark text-light border-secondary"
                value={prefs.maxCacheBytes}
                onChange={(e) => handleSetMaxCacheSize(parseInt(e.target.value, 10))}
              >
                {CACHE_SIZE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {availableDiskSpace != null && (
                <small className="text-secondary mt-1 d-block">
                  {formatCacheSize(availableDiskSpace)} available on disk
                </small>
              )}
            </div>
          )}
        </div>
      </div>

      {/* About */}
      <div className="card bg-dark border-secondary">
        <div className="card-header">About</div>
        <div className="card-body">
          <div className="mb-1">
            <small className="text-secondary">Sync Client Version</small>
            <div>{version}</div>
          </div>
          {connection.serverVersion && (
            <div className="mb-3">
              <small className="text-secondary">Server Version</small>
              <div>{connection.serverVersion}</div>
            </div>
          )}

          {/* Release Notes */}
          {notesLoading && (
            <div className="text-secondary small">
              <span className="spinner-border spinner-border-sm me-1" />
              Loading release notes...
            </div>
          )}
          {releaseNotes?.release_notes && (() => {
            const versions = parseReleaseNotes(releaseNotes.release_notes);
            if (versions.length === 0) return null;
            return (
              <div>
                <small className="text-secondary fw-bold d-block mb-2">
                  Server Release Notes
                  <span className="ms-1 fw-normal">({versions.length} versions)</span>
                </small>
                <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                  {versions.map((ver, i) => (
                    <div key={i} className="mb-2">
                      <div className="text-info small fw-bold">
                        <i className="bi bi-tag me-1" />
                        Version {ver.header}
                      </div>
                      {ver.bullets.map((bullet, j) => (
                        <div key={j} className="ms-3 small text-secondary">
                          &bull; {bullet}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
