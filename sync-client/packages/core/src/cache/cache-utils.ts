import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
  readdirSync,
  rmSync,
  copyFileSync,
} from 'node:fs';
import { join, dirname } from 'node:path';

const TEMP_SUFFIX = '.tmp';

/**
 * Read and parse a JSON index file. Returns `fallback` on missing/corrupt/invalid files.
 * When `validator` is provided, it must return true for the parsed data to be accepted.
 */
export function loadJsonIndex<T>(
  path: string,
  fallback: T,
  validator?: (data: T) => boolean,
): T {
  try {
    if (!existsSync(path)) return fallback;
    const raw = readFileSync(path, 'utf-8');
    const parsed = JSON.parse(raw) as T;
    if (validator && !validator(parsed)) return fallback;
    return parsed;
  } catch {
    return fallback;
  }
}

/**
 * Atomically write a JSON file: serialize to `.tmp`, then rename to final path.
 * Creates parent directories if needed. Errors are silently swallowed (non-fatal).
 */
export function saveJsonIndex(path: string, data: unknown): void {
  try {
    const dir = dirname(path);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    const tmpPath = path + TEMP_SUFFIX;
    writeFileSync(tmpPath, JSON.stringify(data, null, 2), 'utf-8');
    renameSync(tmpPath, path);
  } catch {
    // Non-fatal — cache metadata loss is recoverable
  }
}

/** Remove empty subdirectories under `baseDir`. */
export function removeEmptyDirs(baseDir: string): void {
  try {
    const entries = readdirSync(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const dirPath = join(baseDir, entry.name);
      try {
        const contents = readdirSync(dirPath);
        if (contents.length === 0) {
          rmSync(dirPath, { recursive: true });
        }
      } catch {
        // Ignore
      }
    }
  } catch {
    // Ignore
  }
}

/**
 * Copy a file atomically: write to `.tmp` beside the destination, then rename.
 * Creates parent directories if needed. Returns true on success.
 */
export function atomicCopyFile(src: string, dest: string): boolean {
  try {
    const destDir = dirname(dest);
    if (!existsSync(destDir)) {
      mkdirSync(destDir, { recursive: true });
    }
    const tmpPath = dest + TEMP_SUFFIX;
    copyFileSync(src, tmpPath);
    renameSync(tmpPath, dest);
    return true;
  } catch {
    return false;
  }
}
