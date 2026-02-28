import { useState, useEffect } from 'react';
import { useIPC } from '../hooks/useIPC.js';
import { useAppState } from '../store/app-state.js';
import type { SyncDestination } from '@mporter/core';

const BYTES_PER_GB = 1024 * 1024 * 1024;

function formatGB(bytes: number): string {
  return `${(bytes / BYTES_PER_GB).toFixed(1)} GB`;
}

export function DestinationsPage() {
  const ipc = useIPC();
  const { drives, setDrives } = useAppState();
  const [destinations, setDestinations] = useState<SyncDestination[]>([]);

  useEffect(() => {
    loadData();
    const cleanup = ipc.onDriveChange(() => {
      refreshDrives();
    });
    return () => { cleanup(); };
  }, []);

  async function loadData() {
    await Promise.all([loadDestinations(), refreshDrives()]);
  }

  async function loadDestinations() {
    try {
      const response = await ipc.getSyncDestinations();
      setDestinations(response.destinations);
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
      <div className="card bg-dark border-secondary">
        <div className="card-header">
          <i className="bi bi-folder me-2" />
          Saved Destinations (Server)
        </div>
        <div className="list-group list-group-flush">
          {destinations.length === 0 && (
            <div className="list-group-item bg-dark text-secondary">
              No saved destinations on server
            </div>
          )}
          {destinations.map((d) => (
            <div key={d.name} className="list-group-item bg-dark">
              <div className="fw-bold text-light">{d.name}</div>
              <small className="text-secondary">
                {d.path}
                {d.sync_key && (
                  <span className="badge bg-secondary ms-2">{d.sync_key}</span>
                )}
              </small>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
