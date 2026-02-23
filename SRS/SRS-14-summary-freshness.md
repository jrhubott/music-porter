# SRS 14: Summary Freshness Levels

**Version:** 1.0  |  **Date:** 2026-02-23  |  **Status:** Draft

---

## Purpose

Replace the binary today/not-today update check in the library summary playlist table with four graduated freshness levels, giving users clear visual indicators of which playlists need re-syncing.

## Freshness Levels

| Level | Icon | Age Range | Meaning |
|-------|------|-----------|---------|
| Current | ✅ | Today (0 days) | Just updated |
| Recent | (none) | 1–7 days | Still fresh |
| Stale | ⚠️ | 8–30 days | Needs attention |
| Outdated | ❌ | 31+ days | Needs re-sync |

## Requirements

### 14.1 Freshness Classification

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.1.1 | v2.6.0 | [ ] | A helper function classifies a `last_modified` datetime into one of four levels: Current (0 days), Recent (1–7 days), Stale (8–30 days), Outdated (31+ days) |
| 14.1.2 | v2.6.0 | [ ] | The function returns both the icon string and the level name |
| 14.1.3 | v2.6.0 | [ ] | Age is calculated as calendar days between `last_modified.date()` and `today` |

### 14.2 Playlist Table Display

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.2.1 | v2.6.0 | [ ] | The "Updated" column in `_render_playlist_table()` uses the freshness icon instead of the old binary ⚠️ check |
| 14.2.2 | v2.6.0 | [ ] | Format: `{icon} {MMM DD}` (e.g., `✅ Feb 23`, `⚠️ Feb 10`, `❌ Jan 05`) |
| 14.2.3 | v2.6.0 | [ ] | Recent level shows no icon — just the date (e.g., `  Feb 20`) |
| 14.2.4 | v2.6.0 | [ ] | Missing `last_modified` displays `❌ N/A` |

### 14.3 Aggregate Freshness Statistics

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.3.1 | v2.6.0 | [ ] | Default and detailed summary modes display a freshness breakdown line showing counts per level |
| 14.3.2 | v2.6.0 | [ ] | Format: `Freshness: X current, X recent, X stale, X outdated` |
| 14.3.3 | v2.6.0 | [ ] | Quick mode does not display freshness breakdown |

### 14.4 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 14.4.1 | v2.6.0 | [ ] | Playlists with no files (empty directory) show `❌ N/A` |
| 14.4.2 | v2.6.0 | [ ] | The freshness thresholds are defined as named constants, not magic numbers |
