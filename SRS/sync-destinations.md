# SRS 16: Sync Destinations

Generalize USB sync to support any file location: saved named destinations,
auto-detected USB drives, and ad-hoc custom paths with unified sync tracking.

## Requirements

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 16.1.1 | v2.26.0 | [ ] | `SyncDestination` dataclass stores `name` (str) and `path` (str) for saved destinations |
| 16.1.2 | v2.26.0 | [ ] | `ConfigManager` loads `destinations` list from `config.yaml` via `data.get('destinations', [])` |
| 16.1.3 | v2.26.0 | [ ] | `ConfigManager._save()` serializes `destinations` list to YAML |
| 16.1.4 | v2.26.0 | [ ] | `ConfigManager.add_destination(name, path)` adds a saved destination, validates name uniqueness and path existence, persists to config |
| 16.1.5 | v2.26.0 | [ ] | `ConfigManager.remove_destination(name)` removes a saved destination by name (case-insensitive), persists to config |
| 16.1.6 | v2.26.0 | [ ] | `ConfigManager.get_destination(name)` returns `SyncDestination` by name (case-insensitive) or `None` |
| 16.1.7 | v2.26.0 | [ ] | `validate_config()` validates destination entries (name non-empty, path non-empty) |
| 16.2.1 | v2.26.0 | [ ] | `USBManager` class is renamed to `SyncManager`; `USBManager = SyncManager` alias preserves backwards compatibility |
| 16.2.2 | v2.26.0 | [ ] | `SyncManager.select_destination(config)` shows interactive picker with auto-detected USB drives, saved destinations, and custom path option; returns `(dest_path, dest_key, is_usb)` tuple |
| 16.2.3 | v2.26.0 | [ ] | `SyncManager.sync_to_destination(source_dir, dest_path, dest_key, is_usb, dry_run)` performs sync to any directory using incremental logic from `_should_copy_file()` |
| 16.2.4 | v2.26.0 | [ ] | `SyncManager.sync_to_destination()` only prompts for USB eject when `is_usb=True` |
| 16.2.5 | v2.26.0 | [ ] | `SyncManager.sync_to_destination()` records batches in `sync_tracker` using `dest_key` as the key name |
| 16.2.6 | v2.26.0 | [ ] | `SyncManager.sync_to_usb()` remains as a wrapper calling `sync_to_destination()` for backwards compatibility |
| 16.2.7 | v2.26.0 | [ ] | `USBSyncResult` is renamed to `SyncResult` with `is_usb` field; `USBSyncResult = SyncResult` alias preserved |
| 16.2.8 | v2.26.0 | [ ] | `SyncResult` has `.volume_name` property alias for backwards compatibility |
| 16.2.9 | v2.26.0 | [ ] | `SyncTracker = USBSyncTracker` alias added for forward-looking code |
| 16.2.10 | v2.26.0 | [ ] | No database schema changes required; existing `usb_keys`/`usb_sync_files` tables work for all destination types |
| 16.3.1 | v2.26.0 | [ ] | CLI `sync` subcommand replaces `sync-usb` and `sync-status` with unified interface |
| 16.3.2 | v2.26.0 | [ ] | `sync --dest NAME_OR_PATH` syncs to a saved destination by name or falls back to path |
| 16.3.3 | v2.26.0 | [ ] | `sync` with no arguments triggers interactive destination picker |
| 16.3.4 | v2.26.0 | [ ] | `sync --list-destinations` lists saved destinations |
| 16.3.5 | v2.26.0 | [ ] | `sync --add-dest NAME PATH` saves a new destination |
| 16.3.6 | v2.26.0 | [ ] | `sync --remove-dest NAME` removes a saved destination |
| 16.3.7 | v2.26.0 | [ ] | `sync --status` shows sync tracking summary (was `sync-status`) |
| 16.3.8 | v2.26.0 | [ ] | `sync --list-keys`, `--delete-key`, `--prune` provide tracking management (was `sync-status` subargs) |
| 16.3.9 | v2.26.0 | [ ] | `sync-usb` and `sync-status` remain as hidden aliases for backwards compatibility |
| 16.3.10 | v2.26.0 | [ ] | Pipeline `--sync-dest DEST` flag syncs to named destination or path after processing |
| 16.3.11 | v2.26.0 | [ ] | Pipeline `--copy-to-usb` flag preserved for backwards compatibility, triggers USB-only flow |
| 16.3.12 | v2.26.0 | [ ] | Interactive menu option updated from "Copy to USB only" to "Sync to destination" |
| 16.4.1 | v2.26.0 | [ ] | `GET /api/sync/destinations` returns combined list of saved destinations and USB drives |
| 16.4.2 | v2.26.0 | [ ] | `POST /api/sync/destinations` adds a saved destination |
| 16.4.3 | v2.26.0 | [ ] | `DELETE /api/sync/destinations/<name>` removes a saved destination |
| 16.4.4 | v2.26.0 | [ ] | `POST /api/sync/run` runs sync for any destination type (usb, saved, custom) |
| 16.4.5 | v2.26.0 | [ ] | `GET /api/sync/status` returns all tracked keys summary |
| 16.4.6 | v2.26.0 | [ ] | `GET /api/sync/status/<key>` returns per-playlist detail for a key |
| 16.4.7 | v2.26.0 | [ ] | `GET /api/sync/keys` lists tracked keys |
| 16.4.8 | v2.26.0 | [ ] | `DELETE /api/sync/keys/<key>` deletes a key |
| 16.4.9 | v2.26.0 | [ ] | `DELETE /api/sync/keys/<key>/playlists/<playlist>` deletes playlist tracking |
| 16.4.10 | v2.26.0 | [ ] | `POST /api/sync/keys/<key>/prune` prunes stale records |
| 16.4.11 | v2.26.0 | [ ] | All existing `/api/usb/*` routes remain unchanged for backwards compatibility |
| 16.5.1 | v2.26.0 | [ ] | Web UI `/sync` page combines USB sync and sync status into single page |
| 16.5.2 | v2.26.0 | [ ] | `/usb` and `/sync-status` routes redirect to `/sync` |
| 16.5.3 | v2.26.0 | [ ] | Sidebar shows single "Sync" entry replacing "USB Sync" and "Sync Status" |
| 16.5.4 | v2.26.0 | [ ] | Sync page Section 1: destination picker (saved + USB + custom), source dropdown, dry run/verbose, run button |
| 16.5.5 | v2.26.0 | [ ] | Sync page Section 2: tracked keys table with detail expansion, per-playlist breakdown, prune buttons |
| 16.5.6 | v2.26.0 | [ ] | Sync page Section 3: manage saved destinations (add/remove) |
| 16.5.7 | v2.26.0 | [ ] | Pipeline template: "Copy to USB" checkbox replaced with "Sync to destination" with destination picker |
| 16.6.1 | v2.26.0 | [ ] | iOS `SyncDestination` model struct with `name`, `path`, `type`, `available` fields |
| 16.6.2 | v2.26.0 | [ ] | iOS `SyncKeySummary` replaces `USBKeySummary` (typealias for compat) |
| 16.6.3 | v2.26.0 | [ ] | iOS `APIClient` adds `getSyncDestinations()`, `syncToDestination()`, `getSyncStatus()` methods |
| 16.6.4 | v2.26.0 | [ ] | iOS views updated: labels changed from "USB Sync" to "Sync", property names updated |

## Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 16.7.1 | v2.26.0 | [ ] | `sync --dest` resolves name first; if no saved destination matches, treats argument as a filesystem path |
| 16.7.2 | v2.26.0 | [ ] | `add_destination()` rejects duplicate names (case-insensitive) |
| 16.7.3 | v2.26.0 | [ ] | `add_destination()` validates that the path exists and is a directory |
| 16.7.4 | v2.26.0 | [ ] | Destination names must be alphanumeric with hyphens/underscores only |
| 16.7.5 | v2.26.0 | [ ] | `select_destination()` gracefully handles no USB drives and no saved destinations (shows only custom path option) |
| 16.7.6 | v2.26.0 | [ ] | USB eject is never offered for non-USB destinations |
| 16.7.7 | v2.26.0 | [ ] | Config migration: existing configs without `destinations` key load with empty list (no error) |
