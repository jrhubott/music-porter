import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import type { SyncDestination } from '@mporter/core';

interface LinkDestinationModalProps {
  show: boolean;
  destinationName: string;
  destinationPath?: string;
  onClose: () => void;
  onLinked: () => void;
}

export function LinkDestinationModal({ show, destinationName, destinationPath, onClose, onLinked }: LinkDestinationModalProps) {
  const ipc = useIPC();
  const [otherDestinations, setOtherDestinations] = useState<SyncDestination[]>([]);
  const [selectedDest, setSelectedDest] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (show) {
      setSelectedDest('');
      setError('');
      loadDestinations();
    }
  }, [show, destinationName]);

  async function loadDestinations() {
    try {
      const response = await ipc.getSyncDestinations();
      const others = response.destinations.filter((d) => d.name !== destinationName);
      setOtherDestinations(others);
      if (others.length > 0) {
        setSelectedDest(others[0]!.name);
      }
    } catch {
      setOtherDestinations([]);
    }
  }

  async function handleLink() {
    if (!selectedDest) {
      setError('Please select a destination to share tracking with.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await ipc.linkDestination(destinationName, selectedDest);
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
              Link <strong>{destinationName}</strong> to share sync tracking with another destination.
              {destinationPath && (
                <>
                  <br />
                  <small className="text-secondary">{destinationPath}</small>
                </>
              )}
            </p>

            {otherDestinations.length === 0 ? (
              <div className="text-secondary">
                No other destinations available to link with.
              </div>
            ) : (
              <div className="list-group list-group-flush">
                {otherDestinations.map((d) => (
                  <button
                    key={d.name}
                    className={`list-group-item list-group-item-action border-secondary ${selectedDest === d.name ? 'active' : ''}`}
                    onClick={() => setSelectedDest(d.name)}
                  >
                    <div className="d-flex justify-content-between">
                      <span>{d.name}</span>
                      <small className="text-secondary">{d.path}</small>
                    </div>
                    {d.linked_destinations && d.linked_destinations.length > 0 && (
                      <small className="text-info">
                        Already linked with: {d.linked_destinations.join(', ')}
                      </small>
                    )}
                  </button>
                ))}
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
            <button
              className="btn btn-primary"
              onClick={handleLink}
              disabled={loading || otherDestinations.length === 0}
            >
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
