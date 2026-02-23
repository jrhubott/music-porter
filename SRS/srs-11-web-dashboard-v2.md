# SRS 11: Web Dashboard (v2)

**Version:** 2.0  |  **Date:** 2026-02-23  |  **Status:** In Progress  |  **Builds on:** v1.0 (SRS.md)

---

## Purpose

Extend SRS 11 with detailed API request/response contracts, setup prerequisites, and template linting requirements. These additions ensure the Web Dashboard is fully documented for reimplementation from the SRS alone.

## Requirements

### 11.12 Setup and Prerequisites

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.12.1 | v2.0.0 | [ ] | Flask listed as a dependency in `requirements.txt` and installed in the Python virtual environment |
| 11.12.2 | v2.0.0 | [ ] | `music-porter web` launches the Flask server with optional `--host` (default `127.0.0.1`) and `--port` (default `5555`) flags |
| 11.12.3 | v2.0.0 | [ ] | Default server URL is `http://127.0.0.1:5555`; printed to console on startup |
| 11.12.4 | v2.0.0 | [ ] | `config.yaml` must exist (auto-created with defaults if missing) for playlists and settings at startup |
| 11.12.5 | v2.0.0 | [ ] | Output profiles loaded from `config.yaml` into `mp.OUTPUT_PROFILES` at startup via `load_output_profiles()` |
| 11.12.6 | v2.0.0 | [ ] | `mp._init_third_party()` called at module import time to pre-load dependencies before background threads start |
| 11.12.7 | v2.0.0 | [ ] | `music-porter` imported via `importlib.machinery.SourceFileLoader` because the executable has no `.py` extension |

### 11.13 API Request/Response Contracts

All API endpoints return JSON. Error responses use the shape `{"error": "<message>"}` with the appropriate HTTP status code unless otherwise noted.

**HTTP status code conventions:**

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Validation error (missing/invalid parameters) |
| 404 | Resource not found (task, playlist, directory) |
| 409 | Conflict (another operation already running, duplicate playlist key) |

#### 11.13.1 Status and Info Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.1.1 | v2.0.0 | [ ] | `GET /api/status` returns 200 with JSON: `version` (string), `cookies` (object with `valid` bool, `exists` bool, `reason` string, `days_remaining` int or null), `library` (object with `playlists` int, `files` int, `size_mb` float), `profile` (string), `busy` (bool) |
| 11.13.1.2 | v2.0.0 | [ ] | `GET /api/summary` returns 200 with JSON: `total_playlists` (int), `total_files` (int), `total_size_bytes` (int), `scan_duration` (float), `tag_integrity` (object with `checked`/`protected`/`missing` ints), `cover_art` (object with `with_art`/`without_art`/`original`/`resized` ints), `freshness` (object with `current`/`recent`/`stale`/`outdated` ints), `playlists` (array of objects with `name`, `file_count`, `size_bytes`, `avg_size_mb`, `last_modified` ISO8601 or null, `freshness`, `tags_checked`, `tags_protected`, `cover_with`, `cover_without`), `profile` (string) |
| 11.13.1.3 | v2.0.0 | [ ] | `GET /api/library-stats` returns 200 with JSON: `total_playlists` (int), `total_files` (int), `total_size_bytes` (int), `total_exported` (int), `total_unconverted` (int), `scan_duration` (float) |

#### 11.13.2 Cookie Management Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.2.1 | v2.0.0 | [ ] | `GET /api/cookies/browsers` returns 200 with JSON: `default` (string or null — detected default browser), `installed` (array of strings — available browser names) |
| 11.13.2.2 | v2.0.0 | [ ] | `POST /api/cookies/refresh` accepts JSON body: `browser` (string, required — `"auto"` or browser name), `verbose` (bool, optional). Returns 200 with `{"task_id": "<hex>"}` on submission. Returns 409 with error if another operation is running |
| 11.13.2.3 | v2.0.0 | [ ] | Cookie refresh task result contains: `success` (bool), `reason` (string), `days_remaining` (int or null) |

#### 11.13.3 Playlist CRUD Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.3.1 | v2.0.0 | [ ] | `GET /api/playlists` returns 200 with JSON array of objects: `key` (string), `url` (string), `name` (string) |
| 11.13.3.2 | v2.0.0 | [ ] | `POST /api/playlists` accepts JSON body with required fields: `key` (string, unique identifier), `url` (string, Apple Music URL), `name` (string, display name). Returns 200 with `{"ok": true}`. Returns 400 if any field is missing. Returns 409 if `key` already exists |
| 11.13.3.3 | v2.0.0 | [ ] | `PUT /api/playlists/<key>` accepts JSON body with optional fields: `url` (string), `name` (string). Returns 200 with `{"ok": true}`. Returns 404 if `key` not found |
| 11.13.3.4 | v2.0.0 | [ ] | `DELETE /api/playlists/<key>` returns 200 with `{"ok": true}`. Returns 404 if `key` not found |

#### 11.13.4 Directory Listing Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.4.1 | v2.0.0 | [ ] | `GET /api/directories/music` returns 200 with JSON array of sorted directory name strings (non-hidden subdirectories of `music/`) |
| 11.13.4.2 | v2.0.0 | [ ] | `GET /api/directories/export` returns 200 with JSON array of objects: `name` (string), `files` (int — count via `rglob` for nested directories). Scoped to current output profile: `export/<profile>/` |

#### 11.13.5 Settings Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.5.1 | v2.0.0 | [ ] | `GET /api/settings` returns 200 with JSON: `settings` (object with `output_type` string, `usb_dir` string, `workers` int), `profiles` (object keyed by profile name, each with `description`, `quality_preset`, `artwork_size`, `id3_version`, `directory_structure`, `filename_format`), `quality_presets` (array of strings), `dir_structures` (array of strings), `filename_formats` (array of strings) |
| 11.13.5.2 | v2.0.0 | [ ] | `POST /api/settings` accepts JSON body with any combination of: `output_type` (string), `usb_dir` (string), `workers` (int). Returns 200 with `{"ok": true}` |

#### 11.13.6 Pipeline Endpoint

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.6.1 | v2.0.0 | [ ] | `POST /api/pipeline/run` accepts JSON body: `playlist` (string, optional — playlist key), `url` (string, optional — Apple Music URL), `auto` (bool, optional — process all playlists), `preset` (string, optional — quality preset), `copy_to_usb` (bool, optional), `dir_structure` (string, optional), `filename_format` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Exactly one of `playlist`, `url`, or `auto` must be provided |
| 11.13.6.2 | v2.0.0 | [ ] | Pipeline returns 200 with `{"task_id": "<hex>"}` on submission. Returns 400 if none of `playlist`/`url`/`auto` provided. Returns 409 if another operation is running |
| 11.13.6.3 | v2.0.0 | [ ] | Pipeline task result contains: `success` (bool), `playlists` (int — count, for auto mode) |

#### 11.13.7 Convert Endpoint

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.7.1 | v2.0.0 | [ ] | `POST /api/convert/run` accepts JSON body: `input_dir` (string, required — relative path under `music/`), `output_dir` (string, optional — defaults to `export/<profile>/`), `preset` (string, optional — defaults to `"lossless"`), `force` (bool, optional), `no_cover_art` (bool, optional), `dir_structure` (string, optional), `filename_format` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional) |
| 11.13.7.2 | v2.0.0 | [ ] | Convert returns 200 with `{"task_id": "<hex>"}`. Returns 400 if `input_dir` is missing or fails `_safe_dir()` validation. Returns 409 if another operation is running |
| 11.13.7.3 | v2.0.0 | [ ] | Convert task result contains: `success` (bool) |

#### 11.13.8 Tag Operation Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.8.1 | v2.0.0 | [ ] | `POST /api/tags/update` accepts JSON body: `directory` (string, required — relative path under `export/`), `album` (string, optional), `artist` (string, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` is missing or fails `_safe_dir()`. Returns 409 if busy |
| 11.13.8.2 | v2.0.0 | [ ] | `POST /api/tags/restore` accepts JSON body: `directory` (string, required), `all` (bool, optional — restore all fields), `album` (bool, optional), `title` (bool, optional), `artist` (bool, optional), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` invalid. Returns 409 if busy |
| 11.13.8.3 | v2.0.0 | [ ] | `POST /api/tags/reset` accepts JSON body: `input_dir` (string, required — source M4A directory), `output_dir` (string, required — target MP3 directory), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if either directory is missing or fails `_safe_dir()`. Returns 409 if busy |
| 11.13.8.4 | v2.0.0 | [ ] | All tag operation task results contain: `success` (bool) |

#### 11.13.9 Cover Art Endpoint

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.9.1 | v2.0.0 | [ ] | `POST /api/cover-art/<action>` where `<action>` is one of: `embed`, `extract`, `update`, `strip`, `resize`. Returns 400 if action is not one of the five valid values |
| 11.13.9.2 | v2.0.0 | [ ] | Common parameters for all cover art actions: `directory` (string, required — relative path under `export/`), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `directory` invalid. Returns 409 if busy |
| 11.13.9.3 | v2.0.0 | [ ] | Action-specific parameters: `embed` accepts `source` (string, optional — M4A source directory, auto-derived from export path if omitted) and `force` (bool, optional); `update` accepts `image` (string, optional — path to image file); `resize` accepts `max_size` (int, optional — default 100 pixels) |
| 11.13.9.4 | v2.0.0 | [ ] | Cover art task result contains: `success` (bool). For `update` action, may also include `error` (string) if image validation fails |

#### 11.13.10 USB Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.10.1 | v2.0.0 | [ ] | `GET /api/usb/drives` returns 200 with JSON array of objects: `mount_point` (string), `name` (string), `size_gb` (float) |
| 11.13.10.2 | v2.0.0 | [ ] | `POST /api/usb/sync` accepts JSON body: `source_dir` (string, required — relative path under `export/`), `volume` (string, required — mount point or drive letter), `usb_dir` (string, optional — default `"RZR/Music"`), `dry_run` (bool, optional), `verbose` (bool, optional). Returns 400 if `source_dir` or `volume` missing. Returns 409 if busy |
| 11.13.10.3 | v2.0.0 | [ ] | USB sync task result contains: `success` (bool), `files_found` (int), `files_copied` (int), `files_skipped` (int), `files_failed` (int) |

#### 11.13.11 Task Management Endpoints

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.11.1 | v2.0.0 | [ ] | `GET /api/tasks` returns 200 with JSON array of task objects: `id` (string — 12-char hex), `operation` (string), `description` (string), `status` (string — `pending`/`running`/`completed`/`failed`/`cancelled`), `result` (object or null), `error` (string or null), `elapsed` (float — seconds, rounded to 1 decimal), `started_at` (float — Unix timestamp), `finished_at` (float or null) |
| 11.13.11.2 | v2.0.0 | [ ] | `GET /api/tasks/<task_id>` returns 200 with single task object (same schema as list). Returns 404 if `task_id` not found |
| 11.13.11.3 | v2.0.0 | [ ] | `POST /api/tasks/<task_id>/cancel` returns 200 with `{"ok": true}` if task was running and cancel signal sent. Returns 404 if `task_id` not found or task is not in `running` status |
| 11.13.11.4 | v2.0.0 | [ ] | `GET /api/stream/<task_id>` returns SSE stream (`text/event-stream`) with headers `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Returns 404 if `task_id` not found |

#### 11.13.12 SSE Event Contracts

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.12.1 | v2.0.0 | [ ] | SSE `log` event payload: `{"type": "log", "level": "INFO\|WARN\|ERROR", "message": "<text>"}` — ANSI escape codes stripped before sending |
| 11.13.12.2 | v2.0.0 | [ ] | SSE `progress` event payload: `{"type": "progress", "current": <int>, "total": <int>, "percent": <int>, "stage": "<text>"}` — throttled to fire only on percentage change |
| 11.13.12.3 | v2.0.0 | [ ] | SSE `heartbeat` event payload: `{"type": "heartbeat"}` — sent when queue is empty for 30 seconds |
| 11.13.12.4 | v2.0.0 | [ ] | SSE `done` event payload: `{"type": "done", "status": "completed\|failed\|cancelled", "result": <object or null>, "error": "<string or null>"}` — sent once on task completion, acts as sentinel |

#### 11.13.13 Common API Conventions

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.13.1 | v2.0.0 | [ ] | All directory parameters are validated via `_safe_dir()` which resolves the path and confirms it is within the project root; returns `None` (triggering 400) if the path escapes the project root |
| 11.13.13.2 | v2.0.0 | [ ] | All background operations follow the task submission pattern: POST request → validation → `task_manager.submit()` → return `{"task_id": "<hex>"}` or error. Frontend subscribes to `/api/stream/<task_id>` for live updates |
| 11.13.13.3 | v2.0.0 | [ ] | `task_manager.submit()` returns `None` when another task is already running, resulting in HTTP 409 response |
| 11.13.13.4 | v2.0.0 | [ ] | POST/PUT endpoints parse request body with `request.get_json(force=True)` (strict JSON required) or `request.get_json(silent=True) or {}` (optional JSON with empty-dict fallback) |

#### 11.13.14 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.13.14.1 | v2.0.0 | [ ] | Directory path traversal attempt (e.g., `../etc/passwd`): `_safe_dir()` returns `None`, endpoint returns 400 |
| 11.13.14.2 | v2.0.0 | [ ] | Missing required JSON body on POST: endpoint returns 400 with descriptive error message |
| 11.13.14.3 | v2.0.0 | [ ] | SSE stream for completed task: stream replays final `done` event immediately |
| 11.13.14.4 | v2.0.0 | [ ] | Pipeline called with no mode (`playlist`, `url`, or `auto` all absent): returns 400 with error |
| 11.13.14.5 | v2.0.0 | [ ] | Cover art `update` action with invalid image path: task completes with `success: false` and `error` message in result |

### 11.14 Template Linting (djLint)

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 11.14.1 | vNEXT | [ ] | `djlint` added to `requirements-dev.txt` as a development dependency |
| 11.14.2 | vNEXT | [ ] | djLint configuration in `pyproject.toml` under `[tool.djlint]` with `profile = "jinja"` |
| 11.14.3 | vNEXT | [ ] | Lint check command: `djlint templates/ --lint` — checks all 10 HTML templates for linting issues |
| 11.14.4 | vNEXT | [ ] | Format check command: `djlint templates/ --check` — verifies template formatting without modifying files |
| 11.14.5 | vNEXT | [ ] | CLAUDE.md linting section updated to include djLint commands alongside Ruff and PyMarkdown |
