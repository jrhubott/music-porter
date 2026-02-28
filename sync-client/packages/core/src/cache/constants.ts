/** Subdirectory under config dir for cached audio files. */
export const CACHE_DIRNAME = 'cache';

/** Per-profile cache index filename. */
export const CACHE_INDEX_FILENAME = 'cache-index.json';

/** Default maximum cache size in bytes (10 GB). */
export const DEFAULT_MAX_CACHE_BYTES = 10 * 1024 * 1024 * 1024;

/** Background prefetch interval (ms) — 5 minutes between cycles. */
export const BACKGROUND_PREFETCH_INTERVAL_MS = 5 * 60 * 1000;

/** Per-profile metadata cache filename. */
export const METADATA_CACHE_FILENAME = 'metadata-cache.json';
