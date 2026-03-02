import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import type { SyncKeySummary } from '@mporter/core';

interface LinkDestinationModalProps {
  show: boolean;
  destinationName: string;
  destinationPath?: string;
  onClose: () => void;
  onLinked: () => void;
}

export function LinkDestinationModal({ show, destinationName, destinationPath, onClose, onLinked }: LinkDestinationModalProps) {
  const ipc = useIPC();
  const [mode, setMode] = useState<'new' | 'existing'>('new');
  const [newKeyName, setNewKeyName] = useState('');
  const [existingKeys, setExistingKeys] = useState<SyncKeySummary[]>([]);
  const [selectedKey, setSelectedKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (show) {
      setNewKeyName(`client-${destinationName}`);
      setMode('new');
      setSelectedKey('');
      setError('');
      loadKeys();
    }
  }, [show, destinationName]);

  async function loadKeys() {
    try {
      const keys = await ipc.getSyncKeys();
      setExistingKeys(keys);
      if (keys.length > 0) {
        setSelectedKey(keys[0]!.key_name);
      }
    } catch {
      setExistingKeys([]);
    }
  }

  async function handleLink() {
    const syncKey = mode === 'new' ? newKeyName.trim() : selectedKey;
    if (!syncKey) {
      setError('Please enter or select a sync key.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await ipc.linkDestination(destinationName, syncKey, destinationPath);
      if (result.ok) {
        onLinked();
        onClose();
      } else {
        setError('Failed to link destination.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Link failed');
    } finally {
      setLoading(false);
    }
  }

  if (!show) return null;

  return (
    <div className="modal d-block" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content bg-dark text-light border-secondary">
          <div className="modal-header border-secondary">
            <h5 className="modal-title">
              <i className="bi bi-link-45deg me-2" />
              Link Destination
            </h5>
            <button className="btn-close btn-close-white" onClick={onClose} />
          </div>
          <div className="modal-body">
            <p className="text-secondary mb-3">
              Link <strong>{destinationName}</strong> to a sync key so tracking data is shared.
            </p>

            <div className="form-check mb-2">
              <input
                className="form-check-input"
                type="radio"
                id="mode-new"
                checked={mode === 'new'}
                onChange={() => setMode('new')}
              />
              <label className="form-check-label" htmlFor="mode-new">
                Create new sync key
              </label>
            </div>
            {mode === 'new' && (
              <div className="ms-4 mb-3">
                <input
                  type="text"
                  className="form-control form-control-sm bg-dark text-light border-secondary"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Sync key name..."
                />
              </div>
            )}

            <div className="form-check mb-2">
              <input
                className="form-check-input"
                type="radio"
                id="mode-existing"
                checked={mode === 'existing'}
                onChange={() => setMode('existing')}
              />
              <label className="form-check-label" htmlFor="mode-existing">
                Use existing sync key
              </label>
            </div>
            {mode === 'existing' && (
              <div className="ms-4 mb-3">
                {existingKeys.length === 0 ? (
                  <small className="text-secondary">No existing sync keys found.</small>
                ) : (
                  <div className="list-group list-group-flush">
                    {existingKeys.map((k) => (
                      <button
                        key={k.key_name}
                        className={`list-group-item list-group-item-action border-secondary ${selectedKey === k.key_name ? 'active' : ''}`}
                        onClick={() => setSelectedKey(k.key_name)}
                      >
                        <div className="d-flex justify-content-between">
                          <span>{k.key_name}</span>
                          <small className="text-secondary">
                            {k.file_count} files, {k.playlist_count} playlists
                          </small>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="alert alert-danger py-2 mt-2">{error}</div>
            )}
          </div>
          <div className="modal-footer border-secondary">
            <button className="btn btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleLink} disabled={loading}>
              {loading ? (
                <>
                  <span className="spinner-border spinner-border-sm me-1" />
                  Linking...
                </>
              ) : (
                'Link'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
