/** Base error class for all mporter-sync errors. */
export class MPorterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MPorterError';
  }
}

/** Server connection failed (unreachable or timed out). */
export class ConnectionError extends MPorterError {
  constructor(
    message: string,
    public readonly url?: string,
  ) {
    super(message);
    this.name = 'ConnectionError';
  }
}

/** API key validation failed (401 Unauthorized). */
export class AuthError extends MPorterError {
  constructor(message = 'Invalid API key') {
    super(message);
    this.name = 'AuthError';
  }
}

/** Server returned an error response. */
export class ServerError extends MPorterError {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(`Server error (${status}): ${message}`);
    this.name = 'ServerError';
  }
}

/** Server is busy with another operation (409 Conflict). */
export class ServerBusyError extends MPorterError {
  constructor() {
    super('Server is busy with another operation');
    this.name = 'ServerBusyError';
  }
}

/** Sync engine error (download failure, disk error, etc.). */
export class SyncError extends MPorterError {
  constructor(message: string) {
    super(message);
    this.name = 'SyncError';
  }
}

/** Configuration error (missing or invalid config). */
export class ConfigError extends MPorterError {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

/** No server configured — need to set up connection first. */
export class NotConfiguredError extends MPorterError {
  constructor() {
    super('No server configured. Run "mporter-sync server set-local <url>" first.');
    this.name = 'NotConfiguredError';
  }
}
