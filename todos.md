# Project Todos

## Active

- [ ] Add web file-level browsing page — template + route showing per-file sync indicators using the /api/files/<key>/sync-status endpoint
- [ ] Document web UI (web_ui.py and templates/) — API endpoints, setup instructions, and usage guide
- [ ] Add iOS app version management — version should only be updated when something changes in the iOS app, not on every main project version bump

## Completed

- [x] Refactor web_ui.py — extract API route definitions into a separate module (e.g., `web_api.py`) | Done: 02-24-2026
- [x] Add --output-type feature, defaulting to ride-command (only type for now, but extensible) | Done: 02-18-2026
