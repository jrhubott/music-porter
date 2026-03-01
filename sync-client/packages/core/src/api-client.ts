import {
  AUTH_HEADER_PREFIX,
  HEALTH_CHECK_LOCAL_TIMEOUT_MS,
  HEALTH_CHECK_TIMEOUT_MS,
  LOCAL_TIMEOUT_MS,
  STANDARD_TIMEOUT_MS,
} from './constants.js';
import {
  AuthError,
  ConnectionError,
  NotConfiguredError,
  ServerBusyError,
  ServerError,
} from './errors.js';
import type {
  AboutResponse,
  AuthValidateResponse,
  ClientRecordResponse,
  ConnectionState,
  ConnectionType,
  CookieStatus,
  CookieUploadResponse,
  FileListResponse,
  HealthCheckResult,
  Playlist,
  ServerInfoResponse,
  SettingsResponse,
  SyncDestinationsResponse,
  SyncKeySummary,
  SyncStatusDetail,
} from './types.js';
import type { MetadataCache } from './cache/metadata-cache.js';

const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_MODIFIED = 304;
const HTTP_CONFLICT = 409;
const SUCCESS_RANGE_START = 200;
const SUCCESS_RANGE_END = 299;

/** Result from an ETag-aware GET request. */
interface ETagResult<T> {
  body: T | null;
  etag: string | null;
  notModified: boolean;
}

interface APIClientOptions {
  /** Default request timeout in milliseconds. */
  timeout?: number;
}

/** HTTP client wrapping all music-porter server endpoints. */
export class APIClient {
  private localURL?: string;
  private externalURL?: string;
  private apiKey?: string;
  private activeURL?: string;
  private connType?: ConnectionType;
  /** In-memory ETag for /api/playlists (tiny response, no persistent cache needed). */
  private playlistsETag: string | null = null;
  private playlistsCache: Playlist[] | null = null;

  constructor(_options?: APIClientOptions) {
    // Options reserved for future use
  }

  // ── Configuration ──

  configure(localURL: string, externalURL?: string, apiKey?: string): void {
    this.localURL = localURL;
    this.externalURL = externalURL;
    this.apiKey = apiKey;
  }

  setApiKey(key: string): void {
    this.apiKey = key;
  }

  get connectionState(): ConnectionState {
    return {
      connected: this.activeURL !== undefined,
      type: this.connType,
      activeURL: this.activeURL,
    };
  }

  get isConfigured(): boolean {
    return this.localURL !== undefined || this.externalURL !== undefined;
  }

  // ── Connection Resolution (dual-URL) ──

  /**
   * Try local URL first, then external URL.
   * Sets activeURL and connectionType on success.
   */
  async resolveConnection(): Promise<AuthValidateResponse> {
    if (!this.localURL && !this.externalURL) {
      throw new NotConfiguredError();
    }

    let lastError: Error = new NotConfiguredError();
    const hasExternal = this.externalURL !== undefined;
    const localTimeout = hasExternal ? LOCAL_TIMEOUT_MS : STANDARD_TIMEOUT_MS;

    // Try local URL first
    if (this.localURL) {
      try {
        const response = await this.validateAt(this.localURL, localTimeout);
        this.activeURL = this.localURL;
        this.connType = 'local';
        return response;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
      }
    }

    // Try external URL
    if (this.externalURL) {
      try {
        const response = await this.validateAt(this.externalURL, STANDARD_TIMEOUT_MS);
        this.activeURL = this.externalURL;
        this.connType = 'external';
        return response;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
      }
    }

    throw lastError;
  }

  /** Validate the API key against a specific base URL with timeout. */
  private async validateAt(baseURL: string, timeout: number): Promise<AuthValidateResponse> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      return await this.postTo<AuthValidateResponse>(
        baseURL,
        '/api/auth/validate',
        {},
        controller.signal,
      );
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        throw new ConnectionError(`Connection timed out after ${timeout}ms`, baseURL);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Disconnect and clear active URL and ETag cache. */
  disconnect(): void {
    this.activeURL = undefined;
    this.connType = undefined;
    this.clearETagCache();
  }

  /** Clear in-memory ETag caches (call on reconnect or session reset). */
  clearETagCache(): void {
    this.playlistsETag = null;
    this.playlistsCache = null;
  }

  // ── Playlists ──

  async getPlaylists(): Promise<Playlist[]> {
    const result = await this.getWithETag<Playlist[]>(
      '/api/playlists',
      this.playlistsETag,
    );
    if (result.notModified && this.playlistsCache) {
      return this.playlistsCache;
    }
    this.playlistsETag = result.etag;
    this.playlistsCache = result.body;
    return result.body!;
  }

  // ── Files ──

  async getFiles(
    playlistKey: string,
    includeSyncStatus = false,
    profile?: string,
    metadataCache?: MetadataCache,
  ): Promise<FileListResponse> {
    const queryParts: string[] = [];
    if (includeSyncStatus) queryParts.push('include_sync=true');
    if (profile) queryParts.push(`profile=${encodeURIComponent(profile)}`);
    const params = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
    const path = `/api/files/${playlistKey}${params}`;

    // ETag-aware request when metadataCache is provided
    if (metadataCache) {
      const cachedETag = metadataCache.getETag(playlistKey);
      const result = await this.getWithETag<FileListResponse>(path, cachedETag);
      if (result.notModified) {
        const cached = metadataCache.getPlaylistFiles(playlistKey);
        if (cached) {
          return {
            playlist: playlistKey,
            file_count: cached.fileCount,
            files: cached.files,
            name: cached.playlistName,
          };
        }
      }
      if (result.body) {
        metadataCache.storePlaylistFiles(
          playlistKey,
          result.body.files,
          result.etag,
          result.body.name,
        );
      }
      return result.body!;
    }

    return this.get<FileListResponse>(path);
  }

  /** Get a readable stream for downloading a file. Pass profile for tagged output. */
  async downloadFile(
    playlistKey: string,
    filename: string,
    profile?: string,
    signal?: AbortSignal,
  ): Promise<{ body: ReadableStream<Uint8Array>; size: number }> {
    const profileParam = profile ? `?profile=${encodeURIComponent(profile)}` : '';
    const url = this.buildURL(`/api/files/${playlistKey}/${encodeURIComponent(filename)}${profileParam}`);
    const response = await fetch(url, {
      headers: this.authHeaders(),
      signal,
    });
    this.checkResponse(response);
    if (!response.body) {
      throw new ServerError(response.status, 'No response body');
    }
    const size = parseInt(response.headers.get('content-length') ?? '0', 10);
    return { body: response.body, size };
  }

  /** Build a direct URL for downloading a file (for external use). Pass profile for tagged output. */
  fileDownloadURL(playlistKey: string, filename: string, profile?: string): string {
    const profileParam = profile ? `?profile=${encodeURIComponent(profile)}` : '';
    return this.buildURL(`/api/files/${playlistKey}/${encodeURIComponent(filename)}${profileParam}`);
  }

  // ── Sync ──

  async recordSync(
    syncKey: string,
    playlist: string,
    files: string[],
    folderName?: string,
  ): Promise<ClientRecordResponse> {
    const body: Record<string, unknown> = { sync_key: syncKey, playlist, files };
    if (folderName) {
      body['folder_name'] = folderName;
    }
    return this.post<ClientRecordResponse>('/api/sync/client-record', body);
  }

  async getSyncStatus(key: string): Promise<SyncStatusDetail> {
    return this.get<SyncStatusDetail>(`/api/sync/status/${key}`);
  }

  async getSyncKeys(): Promise<SyncKeySummary[]> {
    return this.get<SyncKeySummary[]>('/api/sync/keys');
  }

  async getSyncDestinations(): Promise<SyncDestinationsResponse> {
    return this.get<SyncDestinationsResponse>('/api/sync/destinations');
  }

  // ── Cookies ──

  /** Fetch cookie validity from the server status endpoint. */
  async getCookieStatus(): Promise<CookieStatus> {
    const status = await this.get<{ cookies: CookieStatus }>('/api/status');
    return status.cookies;
  }

  /** Upload Netscape-format cookie text to the server. */
  async uploadCookies(cookieText: string): Promise<CookieUploadResponse> {
    return this.post<CookieUploadResponse>('/api/cookies/upload', { cookies: cookieText });
  }

  // ── Settings ──

  async getSettings(): Promise<SettingsResponse> {
    return this.get<SettingsResponse>('/api/settings');
  }

  // ── Server Info ──

  async getServerInfo(): Promise<ServerInfoResponse> {
    return this.get<ServerInfoResponse>('/api/server-info');
  }

  // ── About ──

  async getAbout(): Promise<AboutResponse> {
    return this.get<AboutResponse>('/api/about');
  }

  // ── Health Check ──

  /**
   * Lightweight health check — returns true if the server responds, false on any error.
   * Uses a short timeout to avoid blocking.
   */
  async ping(timeoutMs: number = HEALTH_CHECK_TIMEOUT_MS): Promise<boolean> {
    if (!this.activeURL) return false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      await this.get<unknown>('/api/status', controller.signal);
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Dual-URL health check — tries local first (short timeout), then external.
   * Updates activeURL/connType when a different URL succeeds.
   * Does NOT clear activeURL on failure (let the monitor's threshold logic handle that).
   */
  async resolveHealthCheck(): Promise<HealthCheckResult> {
    const hasLocal = this.localURL !== undefined;
    const hasExternal = this.externalURL !== undefined;

    if (!hasLocal && !hasExternal) {
      return { reachable: false, typeChanged: false };
    }

    // Try local first (preferred)
    if (hasLocal) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HEALTH_CHECK_LOCAL_TIMEOUT_MS);
      try {
        await this.getFrom(this.localURL!, '/api/status', controller.signal);
        const changed = this.connType !== 'local';
        this.activeURL = this.localURL;
        this.connType = 'local';
        return { reachable: true, type: 'local', typeChanged: changed };
      } catch {
        // Local unreachable — try external
      } finally {
        clearTimeout(timer);
      }
    }

    // Fall back to external
    if (hasExternal) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT_MS);
      try {
        await this.getFrom(this.externalURL!, '/api/status', controller.signal);
        const changed = this.connType !== 'external';
        this.activeURL = this.externalURL;
        this.connType = 'external';
        return { reachable: true, type: 'external', typeChanged: changed };
      } catch {
        // External also unreachable
      } finally {
        clearTimeout(timer);
      }
    }

    return { reachable: false, type: this.connType, typeChanged: false };
  }

  // ── HTTP Helpers ──

  private buildURL(path: string): string {
    if (!this.activeURL) throw new NotConfiguredError();
    const base = this.activeURL.replace(/\/$/, '');
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
  }

  private authHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.apiKey) {
      headers['Authorization'] = `${AUTH_HEADER_PREFIX} ${this.apiKey}`;
    }
    return headers;
  }

  private async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    const url = this.buildURL(path);
    const response = await fetch(url, {
      method: 'GET',
      headers: this.authHeaders(),
      signal,
    });
    this.checkResponse(response);
    return (await response.json()) as T;
  }

  /**
   * GET with ETag support. Sends If-None-Match when etag is provided.
   * Returns { body: null, notModified: true } on 304 responses.
   */
  private async getWithETag<T>(
    path: string,
    etag: string | null,
    signal?: AbortSignal,
  ): Promise<ETagResult<T>> {
    const url = this.buildURL(path);
    const headers = this.authHeaders();
    if (etag) {
      headers['If-None-Match'] = etag;
    }
    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal,
    });
    if (response.status === HTTP_NOT_MODIFIED) {
      return { body: null, etag, notModified: true };
    }
    this.checkResponse(response);
    const body = (await response.json()) as T;
    const responseETag = response.headers.get('ETag');
    return { body, etag: responseETag, notModified: false };
  }

  private async post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    const url = this.buildURL(path);
    const response = await fetch(url, {
      method: 'POST',
      headers: this.authHeaders(),
      body: JSON.stringify(body),
      signal,
    });
    this.checkResponse(response);
    return (await response.json()) as T;
  }

  /** GET from a specific base URL (for health checks against explicit URLs). */
  private async getFrom<T>(baseURL: string, path: string, signal?: AbortSignal): Promise<T> {
    const base = baseURL.replace(/\/$/, '');
    const p = path.startsWith('/') ? path : `/${path}`;
    const url = `${base}${p}`;
    const response = await fetch(url, {
      method: 'GET',
      headers: this.authHeaders(),
      signal,
    });
    this.checkResponse(response);
    return (await response.json()) as T;
  }

  /** POST to a specific base URL (for connection resolution). */
  private async postTo<T>(
    baseURL: string,
    path: string,
    body: unknown,
    signal?: AbortSignal,
  ): Promise<T> {
    const base = baseURL.replace(/\/$/, '');
    const p = path.startsWith('/') ? path : `/${path}`;
    const url = `${base}${p}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: this.authHeaders(),
      body: JSON.stringify(body),
      signal,
    });
    this.checkResponse(response);
    return (await response.json()) as T;
  }

  private checkResponse(response: Response): void {
    if (response.status === HTTP_UNAUTHORIZED) {
      throw new AuthError();
    }
    if (response.status === HTTP_CONFLICT) {
      throw new ServerBusyError();
    }
    if (response.status < SUCCESS_RANGE_START || response.status > SUCCESS_RANGE_END) {
      throw new ServerError(response.status, response.statusText);
    }
  }
}
