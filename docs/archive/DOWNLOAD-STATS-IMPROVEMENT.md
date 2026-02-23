# Download Statistics & Comprehensive Summary Improvements

## Overview

Enhanced the `apple-to-ride-command` tool with detailed download statistics and a comprehensive files summary that tracks the complete pipeline from playlist → M4A → MP3 → USB.

## Changes Made

### 1. Added DownloadStatistics Class

**Location**: After `ConversionStatistics` class (line ~922)

New class to track download-specific metrics:

- `playlist_total`: Total tracks in the playlist
- `downloaded`: Newly downloaded tracks
- `skipped`: Tracks already existing (skipped by gamdl)
- `failed`: Failed downloads

### 2. Enhanced Download Parsing

**Location**: `Downloader.download()` method (lines ~1208-1310)

Implemented real-time parsing of gamdl 2.8.4 output:
- Extracts total track count from `[Track X/Y]` pattern
- Detects new downloads: `[INFO ... Downloading "Track Name"`
- Detects skipped files: `[WARNING ... Skipping "...": Media file already exists`
- Captures error count: `Finished with X error(s)`
- Returns 4-tuple: `(success, key, album_name, download_stats)`

**Parsing Algorithm**:

```python
# Track the last "Downloading" line
# If we see another download or finish, the previous succeeded
# If we see a skip warning, increment skipped counter
# Parse final error count from completion message
```

### 3. Updated PipelineStatistics

**Location**: `PipelineStatistics` class (lines ~1403-1420)

Changed:

```python
# Before
self.tracks_downloaded = 0  # Misleading - actually came from converter

# After
self.download_stats = None  # DownloadStatistics object
```

### 4. Updated Pipeline Methods

**Locations**:
- `_download_from_url()` (lines ~1560-1595)
- `_download_playlist()` (lines ~1597-1631)

Both methods now:
- Handle 4-tuple return from `downloader.download()`
- Store `download_stats` in pipeline statistics
- Remove workaround that used `converter.stats.total_found`

### 5. Enhanced Download Stage Summary

**Location**: `_print_pipeline_summary()` (lines ~1643-1716)

**Before**:

```text
DOWNLOAD STAGE
──────────────────────────────────────────────────────────────────────
  Status:                  ✅ Success
  Tracks downloaded:       42    ← Misleading! Actually from converter
```

**After**:

```text
DOWNLOAD STAGE
──────────────────────────────────────────────────────────────────────
  Total tracks in playlist:42
  Downloaded (new):        5
  Skipped (already exist): 37
  Failed:                  0
  Status:                  ✅ Success
```

### 6. Added Comprehensive Files Summary

**Location**: End of `_print_pipeline_summary()` (before overall status)

New section that provides a complete view of file progression:

```text
COMPREHENSIVE FILES SUMMARY
──────────────────────────────────────────────────────────────────────
  Playlist tracks:         102
  M4A files after download:102 (5 new, 97 existing)
  MP3s after conversion:   102 (5 converted, 97 skipped)
  Tags updated:            102
  Original tags stored:    15
  Files copied to USB:     102
```

This section:
- Shows file counts at each pipeline stage
- Clearly indicates new vs. existing files
- Helps identify issues (e.g., missing files, failed conversions)
- Only appears when relevant statistics are available

## Testing

### Unit Tests

Created and verified parsing logic with test scripts:
- ✅ Correctly parses track totals
- ✅ Correctly counts new downloads
- ✅ Correctly counts skipped files
- ✅ Correctly captures error counts
- ✅ Handles edge cases (no downloads, all skipped, errors)

### Integration Tests

- ✅ Script compiles without syntax errors
- ✅ `--version` flag works
- ✅ `--help` flags work for all commands
- ✅ Dry-run mode works (shows comprehensive summary)
- ✅ Backward compatible with existing functionality

## Benefits

1. **Accurate Download Reporting**: Shows exactly what gamdl did
   - How many tracks were in the playlist
   - How many were newly downloaded
   - How many were skipped (already existed)
   - How many failed

2. **Complete Pipeline Visibility**: Comprehensive summary shows:
   - File progression through all stages
   - Helps verify nothing was lost
   - Easy to spot issues

3. **Better Troubleshooting**: Users can:
   - Identify if downloads are failing
   - See if all playlist tracks were processed
   - Verify file counts match expectations

4. **No Breaking Changes**:
   - All existing functionality preserved
   - Error handling maintained
   - Backward compatible with dry-run, auto modes

## gamdl Output Format (Verified)

Based on actual gamdl 2.8.4 output (from logs):

```text
[INFO     HH:MM:SS] Starting Gamdl 2.8.4
[INFO     HH:MM:SS] [Track 1/102] Downloading "Track Name"
[WARNING  HH:MM:SS] [Track 1/102] Skipping "Track Name": Media file already exists at path: ...
[INFO     HH:MM:SS] [Track 2/102] Downloading "Track Name"
[INFO     HH:MM:SS] Finished with 0 error(s)
```

**Patterns**:
- Track count: `\[Track\s+\d+/(\d+)\]`
- Download: `[INFO` + `Downloading "`
- Skip: `[WARNING` + `Skipping "` + `Media file already exists`
- Errors: `Finished with (\d+) error`

## Error Handling

The parsing logic includes comprehensive error handling:
- Try-except around all regex operations
- Continues on parse failures (doesn't crash)
- If parsing fails, statistics remain at 0 (safe default)
- Original functionality preserved even if parsing fails

## Files Modified

- `apple-to-ride-command`: Main script (all changes)

## Future Enhancements

Potential improvements for future versions:
- Add duration/speed statistics (tracks per second)
- Track download size (MB downloaded)
- Show which specific tracks failed
- Add progress percentage during download
