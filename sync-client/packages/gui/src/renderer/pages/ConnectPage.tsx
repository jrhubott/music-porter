import { useState, useEffect } from 'react';
import type { DiscoveredServer } from '@mporter/core';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';

export function ConnectPage() {
  const ipc = useIPC();
  const { setConnection, setActivePage, setIsOffline } = useAppState();
  const [servers, setServers] = useState<DiscoveredServer[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [localURL, setLocalURL] = useState('');
  const [externalURL, setExternalURL] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasCacheData, setHasCacheData] = useState(false);

  useEffect(() => {
    discover();
    loadSavedConfig();
    checkCacheData();
  }, []);

  async function checkCacheData() {
    try {
      const hasData = await ipc.cacheHasData();
      setHasCacheData(hasData);
    } catch {
      // Cache check non-critical
    }
  }

  async function continueOffline() {
    setIsOffline(true);
    setActivePage('sync');
  }

  async function loadSavedConfig() {
    const config = await ipc.getServerConfig();
    if (config) {
      setLocalURL(config.localURL);
      setExternalURL(config.externalURL ?? '');
    }
  }

  async function discover() {
    setIsSearching(true);
    try {
      const found = await ipc.discoverServers();
      setServers(found);
    } catch {
      // Discovery failed silently
    }
    setIsSearching(false);
  }

  async function connect() {
    if (!localURL && !externalURL) {
      setError('Enter at least a local URL.');
      return;
    }

    setIsConnecting(true);
    setError('');

    try {
      if (apiKey) {
        await ipc.setApiKey(apiKey);
      }
      await ipc.updateServerConfig({
        name: '',
        localURL: localURL || `http://localhost:5555`,
        externalURL: externalURL || undefined,
      });

      const state = await ipc.connect();
      if (state.connected) {
        setConnection(state);
        setActivePage('playlists');
      } else {
        setError('Connection failed. Check the URL and API key.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed');
    }
    setIsConnecting(false);
  }

  function selectServer(server: DiscoveredServer) {
    setLocalURL(`http://${server.host}:${server.port}`);
  }

  return (
    <div className="container" style={{ maxWidth: 600 }}>
      <h4 className="mb-4">Connect to Server</h4>

      {/* Discovered Servers */}
      <div className="card bg-dark border-secondary mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <span>Discovered Servers</span>
          <button className="btn btn-sm btn-outline-secondary" onClick={discover} disabled={isSearching}>
            {isSearching ? (
              <span className="spinner-border spinner-border-sm" />
            ) : (
              <i className="bi bi-arrow-clockwise" />
            )}
          </button>
        </div>
        <div className="list-group list-group-flush">
          {servers.length === 0 && (
            <div className="list-group-item bg-dark text-secondary">
              {isSearching ? 'Searching...' : 'No servers found'}
            </div>
          )}
          {servers.map((s) => (
            <button
              key={`${s.host}:${s.port}`}
              className="list-group-item list-group-item-action bg-dark text-light"
              onClick={() => selectServer(s)}
            >
              <div className="fw-bold">{s.name}</div>
              <small className="text-secondary">
                {s.host}:{s.port}
                {s.version && ` — v${s.version}`}
              </small>
            </button>
          ))}
        </div>
      </div>

      {/* Manual Connection */}
      <div className="mb-3">
        <label className="form-label">Local URL</label>
        <input
          type="text"
          className="form-control bg-dark text-light border-secondary"
          placeholder="http://192.168.1.100:5555"
          value={localURL}
          onChange={(e) => setLocalURL(e.target.value)}
        />
      </div>

      <div className="mb-3">
        <label className="form-label">External URL (optional)</label>
        <input
          type="text"
          className="form-control bg-dark text-light border-secondary"
          placeholder="https://music.example.com"
          value={externalURL}
          onChange={(e) => setExternalURL(e.target.value)}
        />
      </div>

      <div className="mb-3">
        <label className="form-label">API Key</label>
        <input
          type="password"
          className="form-control bg-dark text-light border-secondary"
          placeholder="Enter API key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        <div className="form-text">From the server startup output or web dashboard.</div>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
        </div>
      )}

      <button
        className="btn btn-primary w-100"
        onClick={connect}
        disabled={isConnecting || (!localURL && !externalURL)}
      >
        {isConnecting ? (
          <>
            <span className="spinner-border spinner-border-sm me-2" />
            Connecting...
          </>
        ) : (
          'Connect'
        )}
      </button>

      {hasCacheData && (
        <button
          className="btn btn-outline-secondary w-100 mt-3"
          onClick={continueOffline}
        >
          <i className="bi bi-cloud-slash me-2" />
          Continue Offline
          <div className="small opacity-75 mt-1">Sync from local cache without server connection</div>
        </button>
      )}
    </div>
  );
}
