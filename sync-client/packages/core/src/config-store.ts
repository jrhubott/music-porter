import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { getConfigDir } from './platform.js';
import { ConfigError } from './errors.js';
import type { AppConfig, ServerConfig, SyncPreferences } from './types.js';
import { DEFAULT_CONCURRENCY } from './constants.js';

const CONFIG_FILENAME = 'config.json';
const API_KEY_FILENAME = 'api-key';
const FILE_PERMISSIONS = 0o600;

const DEFAULT_PREFERENCES: SyncPreferences = {
  concurrency: DEFAULT_CONCURRENCY,
  autoSyncOnUSB: false,
  notifications: true,
};

/** Persistent JSON config store for server connection and preferences. */
export class ConfigStore {
  private readonly configPath: string;
  private readonly apiKeyPath: string;
  private config: AppConfig;

  constructor(configDir?: string) {
    const dir = configDir ?? getConfigDir();
    this.configPath = join(dir, CONFIG_FILENAME);
    this.apiKeyPath = join(dir, API_KEY_FILENAME);
    this.config = this.load();
  }

  // ── Server ──

  get serverConfig(): ServerConfig | null {
    return this.config.server;
  }

  set serverConfig(config: ServerConfig | null) {
    this.config.server = config;
    this.save();
  }

  get isConfigured(): boolean {
    return this.config.server !== null;
  }

  // ── Preferences ──

  get preferences(): SyncPreferences {
    return this.config.preferences;
  }

  updatePreferences(updates: Partial<SyncPreferences>): void {
    this.config.preferences = { ...this.config.preferences, ...updates };
    this.save();
  }

  // ── API Key (separate file with restricted permissions) ──

  getApiKey(): string | null {
    try {
      if (!existsSync(this.apiKeyPath)) return null;
      return readFileSync(this.apiKeyPath, 'utf-8').trim();
    } catch {
      return null;
    }
  }

  setApiKey(key: string): void {
    this.ensureDir(dirname(this.apiKeyPath));
    writeFileSync(this.apiKeyPath, key, 'utf-8');
    try {
      chmodSync(this.apiKeyPath, FILE_PERMISSIONS);
    } catch {
      // chmod may not work on Windows
    }
  }

  deleteApiKey(): void {
    try {
      const { unlinkSync } = require('node:fs') as typeof import('node:fs');
      unlinkSync(this.apiKeyPath);
    } catch {
      // File may not exist
    }
  }

  // ── Persistence ──

  private load(): AppConfig {
    try {
      if (!existsSync(this.configPath)) {
        return { server: null, preferences: { ...DEFAULT_PREFERENCES } };
      }
      const raw = readFileSync(this.configPath, 'utf-8');
      const parsed = JSON.parse(raw) as Partial<AppConfig>;
      return {
        server: parsed.server ?? null,
        preferences: { ...DEFAULT_PREFERENCES, ...parsed.preferences },
      };
    } catch (err) {
      throw new ConfigError(`Failed to load config: ${err}`);
    }
  }

  private save(): void {
    try {
      this.ensureDir(dirname(this.configPath));
      writeFileSync(this.configPath, JSON.stringify(this.config, null, 2), 'utf-8');
    } catch (err) {
      throw new ConfigError(`Failed to save config: ${err}`);
    }
  }

  private ensureDir(dir: string): void {
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
  }
}
