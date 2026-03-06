import type { SyncProgress } from './types.js';

/** Callback for receiving sync progress updates. */
export type ProgressCallback = (progress: SyncProgress) => void;

/** Callback for receiving log messages. */
export type LogCallback = (level: 'info' | 'warn' | 'error', message: string) => void;
