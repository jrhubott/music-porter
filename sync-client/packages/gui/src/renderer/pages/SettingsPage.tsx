import { useState, useEffect } from 'react';
import type { SyncPreferences, ServerConfig } from '@mporter/core';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';

const MIN_CONCURRENCY = 1;
const MAX_CONCURRENCY = 8;

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
  } = useAppState();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [prefs, setPrefs] = useState<SyncPreferences | null>(null);
  const [version, setVersion] = useState('');

  useEffect(() => {
    loadSettings();
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

    // Fetch server profiles and restore saved profile
    try {
      const [settings, savedProfile] = await Promise.all([
        ipc.getSettings(),
        ipc.getProfile(),
      ]);
      setServerProfiles(settings.profiles);
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
          <button className="btn btn-outline-danger btn-sm" onClick={disconnect}>
            Disconnect
          </button>
        </div>
      </div>

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

      {/* About */}
      <div className="card bg-dark border-secondary">
        <div className="card-header">About</div>
        <div className="card-body">
          <div className="mb-1">
            <small className="text-secondary">Sync Client Version</small>
            <div>{version}</div>
          </div>
          {connection.serverVersion && (
            <div>
              <small className="text-secondary">Server Version</small>
              <div>{connection.serverVersion}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
