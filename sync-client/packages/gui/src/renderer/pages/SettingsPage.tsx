import { useState, useEffect } from 'react';
import type { SyncPreferences, ServerConfig } from '@mporter/core';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';

export function SettingsPage() {
  const ipc = useIPC();
  const { connection, setConnection, setActivePage } = useAppState();
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

  async function toggleAutoSync() {
    if (!prefs) return;
    const updated = { ...prefs, autoSyncOnUSB: !prefs.autoSyncOnUSB };
    setPrefs(updated);
    await ipc.updatePreferences({ autoSyncOnUSB: updated.autoSyncOnUSB });
  }

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
                min={1}
                max={8}
                value={prefs.concurrency}
                onChange={(e) => updateConcurrency(parseInt(e.target.value, 10))}
              />
              <small className="text-secondary">{prefs.concurrency} concurrent downloads</small>
            </div>
            <div className="form-check form-switch">
              <input
                className="form-check-input"
                type="checkbox"
                checked={prefs.autoSyncOnUSB}
                onChange={toggleAutoSync}
              />
              <label className="form-check-label">Auto-sync when USB drive inserted</label>
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
