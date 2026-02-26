# SRS 18: Destination Linking — Shared Sync Keys

## Overview

Adds an optional `sync_key` field to `SyncDestination` so multiple destinations can share
a single tracking key. This unifies sync tracking across server-side sync, client-side
browser sync, and iOS — preventing duplicate tracking entries and unnecessary re-syncs.

## Requirements

### 18.1 Data Model

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.1.1 | 1.0 | [ ] | `SyncDestination` dataclass has an optional `sync_key: str` field (default `None`) |
| 18.1.2 | 1.0 | [ ] | `SyncDestination.effective_key` property returns `sync_key` if set, otherwise `name` |
| 18.1.3 | 1.0 | [ ] | `to_api_dict()` includes `effective_key` field and conditionally includes `sync_key` when set |
| 18.1.4 | 1.0 | [ ] | `config.yaml` destinations persist `sync_key` when set; omit when `None` |
| 18.1.5 | 1.0 | [ ] | ConfigManager loads `sync_key` from YAML destination entries |

### 18.2 Tracking Merge

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.2.1 | 1.0 | [ ] | `SyncTracker.merge_key(source_key, target_key)` moves all `sync_files` records from source to target |
| 18.2.2 | 1.0 | [ ] | Duplicate records (same file\_path + playlist) resolve by keeping the latest `synced_at` timestamp |
| 18.2.3 | 1.0 | [ ] | After merge, source sync key is deleted (cascade deletes remaining records) |
| 18.2.4 | 1.0 | [ ] | `merge_key()` returns `{records_moved, records_merged, source_deleted}` stats |
| 18.2.5 | 1.0 | [ ] | Merging when source key has no records is a no-op returning zero counts |
| 18.2.6 | 1.0 | [ ] | Target key is created (upserted) if it does not already exist |

### 18.3 API

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.3.1 | 1.0 | [ ] | `PUT /api/sync/destinations/<name>/link` accepts `{sync_key}` to link or `{sync_key: ""}` to unlink |
| 18.3.2 | 1.0 | [ ] | Link endpoint calls `merge_key()` when old tracking data exists under the destination name |
| 18.3.3 | 1.0 | [ ] | Link endpoint returns `{ok, sync_key, merge_stats}` |
| 18.3.4 | 1.0 | [ ] | `POST /api/sync/destinations` accepts optional `sync_key` field |
| 18.3.5 | 1.0 | [ ] | `GET /api/sync/destinations` returns `effective_key` and `sync_key` for each destination |
| 18.3.6 | 1.0 | [ ] | `POST /api/sync/run` uses `dest.effective_key` for tracking instead of `dest.name` |

### 18.4 Web UI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.4.1 | 1.0 | [ ] | Destinations table shows "Linked Key" column with badge when linked |
| 18.4.2 | 1.0 | [ ] | Each destination row has a link/unlink button in the actions column |
| 18.4.3 | 1.0 | [ ] | Link modal allows selecting from existing sync keys |
| 18.4.4 | 1.0 | [ ] | Add destination form has optional "Link to Key" dropdown |
| 18.4.5 | 1.0 | [ ] | `findDestMeta()` matches by both `name` and `effective_key` |
| 18.4.6 | 1.0 | [ ] | Sync Keys table shows linked-destination count badge when destinations link to a key |

### 18.5 CLI

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.5.1 | 1.0 | [ ] | `--link-to KEY` flag on `--add-dest` pre-links the new destination |
| 18.5.2 | 1.0 | [ ] | `--link-dest NAME KEY` links an existing destination and merges tracking data |
| 18.5.3 | 1.0 | [ ] | `--unlink-dest NAME` removes the sync\_key from a destination |
| 18.5.4 | 1.0 | [ ] | `render_destinations_list` shows `-> KEY` suffix for linked destinations |
| 18.5.5 | 1.0 | [ ] | All sync operations use `dest.effective_key` for tracking |
| 18.5.6 | 1.0 | [ ] | Pipeline sync stage uses `sync_destination.effective_key` |

### 18.6 iOS

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.6.1 | 1.0 | [ ] | `SyncDestination` model has optional `syncKey` and required `effectiveKey` fields |
| 18.6.2 | 1.0 | [ ] | CodingKeys map `sync_key` and `effective_key` from JSON |

### 18.7 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 18.7.1 | 1.0 | [ ] | Linking to a nonexistent key is allowed — key is created on first sync |
| 18.7.2 | 1.0 | [ ] | Deleting a destination that others link to does not affect other destinations |
| 18.7.3 | 1.0 | [ ] | Deleting a sync key that destinations link to removes tracking data; `sync_key` field persists in config |
| 18.7.4 | 1.0 | [ ] | Unlinking a destination does not delete or move tracking data |
| 18.7.5 | 1.0 | [ ] | Auto-detected USB drives (unsaved) have no `sync_key` — `effective_key` equals `name` |
