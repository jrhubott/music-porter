// Cache module — barrel export

// Types
export type {
  CacheEntry,
  CacheIndex,
  CachedPlaylistData,
  MetadataCacheData,
  PrefetchResult,
  PlaylistCacheStatus,
  BackgroundPrefetchStatus,
} from './types.js';

// Constants
export {
  CACHE_DIRNAME,
  CACHE_INDEX_FILENAME,
  DEFAULT_MAX_CACHE_BYTES,
  BACKGROUND_PREFETCH_INTERVAL_MS,
  METADATA_CACHE_FILENAME,
} from './constants.js';

// Utilities
export { loadJsonIndex, saveJsonIndex, removeEmptyDirs, atomicCopyFile } from './cache-utils.js';

// Classes
export { CacheManager } from './cache-manager.js';
export { MetadataCache } from './metadata-cache.js';
export { PrefetchEngine } from './prefetch-engine.js';
export type { PrefetchOptions } from './prefetch-engine.js';
