# Project Todos

## Active

- [ ] Add web file-level browsing page — template + route showing per-file sync indicators using the /api/files/<key>/sync-status endpoint
- [ ] Document web UI (web_ui.py and templates/) — API endpoints, setup instructions, and usage guide
- [ ] Add iOS app version management — version should only be updated when something changes in the iOS app, not on every main project version bump
- [ ] Build companion desktop agent — lightweight Python CLI/binary with Bonjour discovery, API key auth, and USB detection (reusing SyncManager platform logic) for incremental sync from music-porter server to local drives without a browser
- [ ] iOS sync should honor USB directory structure — create playlist subdirectories under the user's selected directory (matching server sync behavior) and inform the user that subdirectories will be created within their chosen location
- [ ] Add schema versioning to config.yaml and music-porter.db — add a schema_version field to both, consolidate all existing migration logic into two functions (one for DB, one for config), update CLAUDE.md to document the schema and instruct Claude to increment the version when schemas change
- [ ] For the Operations and Audit Log WebUI please add helper dropdowns for common date range selections.  Today, Yesterday, This Month, Last Month, etc.
- [ ] Refactor iOS app for simplicity — current app is too complex for users. Core flow should be: Browse Apple Music, Add Playlist from Apple Music, Sync to USB Key. Discuss which additional features should remain. Goal is an app that is easy to use and easy to maintain.

## Completed

- [x] Refactor web_ui.py — extract API route definitions into a separate module (e.g., `web_api.py`) | Done: 02-24-2026
- [x] Add --output-type feature, defaulting to ride-command (only type for now, but extensible) | Done: 02-18-2026
