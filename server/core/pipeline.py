"""
core.pipeline - PipelineOrchestrator, DataManager, SummaryManager, and helpers.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from core.config import (
    ConfigManager,
    DependencyChecker,
    NonInteractivePromptHandler,
    NullDisplayHandler,
)
from core.constants import (
    DEFAULT_COOKIES,
    DEFAULT_IMPORTER,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_OUTPUT_TYPE,
    IMPORTER_YTDLP,
    OUTPUT_PROFILES,
    SOURCE_SUBDIR,
)
from core.converter import ConversionStatistics, Converter
from core.downloader import Downloader, YouTubeMusicDownloader
from core.logging import Logger
from core.models import (
    AggregateResult,
    DeleteResult,
    PipelineResult,
)
from core.sync import SyncManager, cleanup_removed_tracks, detect_removed_tracks
from core.utils import (
    _format_bytes,
    _is_cancelled,
    get_artwork_dir,
    get_audio_dir,
    get_source_dir,
    read_m4a_tags,
)


def backfill_track_metadata(track_db, project_root=None, logger=None,
                            display_handler=None, cancel_event=None):
    """Re-read M4A tags for all tracks and update extended metadata columns.

    Queries all tracks with a non-null source_m4a_path, re-reads the M4A
    tags, and calls update_track_metadata() to populate the 14 new columns.
    Skips tracks where the source file doesn't exist on disk.
    """
    logger = logger or Logger()
    root = Path(project_root) if project_root else Path('.')
    tracks = track_db.get_all_tracks()
    total = len(tracks)
    updated = 0
    skipped = 0
    errors = 0

    logger.info(f"Backfill: scanning {total} tracks for metadata updates")

    for i, track in enumerate(tracks):
        if cancel_event and cancel_event.is_set():
            logger.warn("Backfill cancelled by user")
            break

        source_path = track.get('source_m4a_path')
        if not source_path:
            skipped += 1
            continue
        # Resolve relative paths against project root
        source_file = Path(source_path)
        if not source_file.is_absolute():
            source_file = root / source_file
        if not source_file.exists():
            skipped += 1
            continue

        try:
            m4a_tags = read_m4a_tags(source_file)
            track_db.update_track_metadata(
                uuid=track['uuid'],
                title=m4a_tags['title'],
                artist=m4a_tags['artist'],
                album=m4a_tags['album'],
                genre=m4a_tags.get('genre') or None,
                track_number=m4a_tags.get('track_number'),
                track_total=m4a_tags.get('track_total'),
                disc_number=m4a_tags.get('disc_number'),
                disc_total=m4a_tags.get('disc_total'),
                year=m4a_tags.get('year') or None,
                composer=m4a_tags.get('composer') or None,
                album_artist=m4a_tags.get('album_artist') or None,
                bpm=m4a_tags.get('bpm'),
                comment=m4a_tags.get('comment') or None,
                compilation=1 if m4a_tags.get('compilation') else None,
                grouping=m4a_tags.get('grouping') or None,
                lyrics=m4a_tags.get('lyrics') or None,
                copyright_text=m4a_tags.get('copyright') or None,
            )
            updated += 1
        except Exception as e:
            logger.error(f"Failed to backfill {track['uuid']}: {e}")
            errors += 1

        if display_handler and (i + 1) % 10 == 0:
            display_handler.show_progress(i + 1, total,
                                          f"Backfill: {i + 1}/{total}")

    logger.info(f"Backfill complete: {updated} updated, {skipped} skipped, {errors} errors")
    return {'updated': updated, 'skipped': skipped, 'errors': errors,
            'total': total}


AUDIT_PROGRESS_INTERVAL = 10


def audit_library(track_db, project_root=None, logger=None,
                  display_handler=None, cancel_event=None,
                  sync_tracker=None, allow_updates=False):
    """Verify DB records match filesystem and clean up orphans.

    Four phases:
    1. Verify DB records against filesystem (remove stale records, normalize paths)
    2. Deduplicate tracks sharing the same source M4A (before clearing missing sources)
    3. Clear missing source paths, find orphan files on disk
    4. Cross-check sync DB against track DB (remove stale sync records)

    When allow_updates=False (default), no destructive actions are performed —
    only reports what would happen. Pass allow_updates=True to actually modify
    the database and delete orphan files.

    Returns a structured summary dict.
    """
    logger = logger or Logger()
    root = Path(project_root) if project_root else Path('.')
    audio_dir = root / get_audio_dir()
    artwork_dir = root / get_artwork_dir()

    stats = {
        'total_tracks_checked': 0,
        'records_removed': 0,
        'orphan_files_removed': 0,
        'orphan_artwork_removed': 0,
        'cover_art_cleared': 0,
        'source_cleared': 0,
        'paths_normalized': 0,
        'sizes_updated': 0,
        'duplicates_removed': 0,
        'sync_records_removed': 0,
        'sync_uuid_orphans_removed': 0,
        'orphan_source_m4as_removed': 0,
        'orphaned_playlist_tracks_removed': 0,
        'details': [],
    }

    def _detail(msg):
        stats['details'].append(msg)
        logger.info(msg)

    # ── Phase 1: Verify DB records, normalize paths ─────────────────
    logger.info("=== Phase 1: Verifying DB records against filesystem ===")
    tracks = track_db.get_all_tracks()
    stats['total_tracks_checked'] = len(tracks)

    # Collect artwork paths referenced by surviving tracks (for Phase 4)
    referenced_artwork = set()

    for i, track in enumerate(tracks):
        if cancel_event and cancel_event.is_set():
            logger.warn("Audit cancelled by user")
            return stats

        uuid = track['uuid']
        file_path = track.get('file_path', '')
        mp3_path = root / file_path if file_path else None

        # Check MP3 exists
        if not mp3_path or not mp3_path.exists():
            if allow_updates:
                track_db.delete_track(uuid)
            else:
                logger.dry_run(f"Would remove DB record: uuid={uuid} "
                               f"(MP3 missing: {file_path})")
            _detail(f"{'Removed' if allow_updates else 'Would remove'} "
                    f"DB record: uuid={uuid} (MP3 missing: {file_path})")
            stats['records_removed'] += 1
            continue

        # Check cover art exists
        cover_art = track.get('cover_art_path')
        if cover_art:
            art_path = root / cover_art
            if art_path.exists():
                referenced_artwork.add(cover_art)
            else:
                if allow_updates:
                    track_db.repair_track(uuid,
                                          cover_art_path=None,
                                          cover_art_hash=None)
                else:
                    logger.dry_run(
                        f"Would clear stale cover_art_path for {uuid}")
                _detail(f"{'Cleared' if allow_updates else 'Would clear'} "
                        f"stale cover_art_path for {uuid}")
                stats['cover_art_cleared'] += 1

        # Normalize absolute source_m4a_path to relative (but don't clear
        # missing paths yet — dedup needs them intact in Phase 2)
        source_m4a = track.get('source_m4a_path')
        if source_m4a:
            source_path = Path(source_m4a)
            if source_path.is_absolute():
                try:
                    rel = source_path.relative_to(root.resolve())
                    if allow_updates:
                        track_db.repair_track(uuid,
                                              source_m4a_path=str(rel))
                    else:
                        logger.dry_run(
                            f"Would normalize path for track {uuid}")
                    _detail(
                        f"{'Normalized' if allow_updates else 'Would normalize'}"
                        f" path for track {uuid}")
                    stats['paths_normalized'] += 1
                except ValueError:
                    if allow_updates:
                        track_db.repair_track(uuid, source_m4a_path=None)
                    else:
                        logger.dry_run(
                            f"Would clear unreachable source_m4a_path "
                            f"for {uuid}")
                    _detail(
                        f"{'Cleared' if allow_updates else 'Would clear'} "
                        f"unreachable source_m4a_path for {uuid}")
                    stats['source_cleared'] += 1

        # Fix file_size_bytes if missing or zero
        file_size = track.get('file_size_bytes')
        if (not file_size or file_size == 0) and mp3_path.exists():
            actual_size = mp3_path.stat().st_size
            if allow_updates:
                track_db.repair_track(uuid, file_size_bytes=actual_size)
            else:
                logger.dry_run(
                    f"Would update file_size_bytes for {uuid}: "
                    f"{actual_size}")
            _detail(
                f"{'Updated' if allow_updates else 'Would update'} "
                f"file_size_bytes for {uuid}: {actual_size}")
            stats['sizes_updated'] += 1

        if display_handler and (i + 1) % AUDIT_PROGRESS_INTERVAL == 0:
            display_handler.show_progress(
                i + 1, len(tracks),
                f"Phase 1: {i + 1}/{len(tracks)} tracks")

    # ── Phase 2: Deduplicate tracks sharing the same source M4A ──
    # Run BEFORE clearing missing source paths so duplicates are still
    # detectable even when the source file has been deleted.
    if cancel_event and cancel_event.is_set():
        logger.warn("Audit cancelled by user")
        return stats

    logger.info("=== Phase 2: Detecting duplicate source_m4a_path entries ===")
    # Re-fetch tracks (Phase 1 may have deleted some)
    tracks = track_db.get_all_tracks()
    source_map = {}  # source_m4a_path → list of track dicts
    for t in tracks:
        src = t.get('source_m4a_path')
        if src:
            source_map.setdefault(src, []).append(t)

    for src_path, dupes in source_map.items():
        if len(dupes) < 2:
            continue
        # Keep the newest record (highest created_at), remove the rest
        dupes.sort(key=lambda t: t.get('created_at', 0), reverse=True)
        keeper = dupes[0]
        for dup in dupes[1:]:
            if cancel_event and cancel_event.is_set():
                logger.warn("Audit cancelled by user")
                return stats
            dup_uuid = dup['uuid']
            if allow_updates:
                # Delete the duplicate MP3
                dup_mp3 = root / dup.get('file_path', '')
                if dup_mp3.is_file():
                    dup_mp3.unlink()
                # Delete the duplicate artwork
                dup_art = dup.get('cover_art_path')
                if dup_art:
                    dup_art_path = root / dup_art
                    if dup_art_path.is_file():
                        dup_art_path.unlink()
                # Remove from referenced_artwork so Phase 4 can clean up
                if dup_art and dup_art in referenced_artwork:
                    referenced_artwork.discard(dup_art)
                track_db.delete_track(dup_uuid)
            else:
                logger.dry_run(
                    f"Would remove duplicate: uuid={dup_uuid} "
                    f"(kept {keeper['uuid']}, source={src_path})")
            _detail(
                f"{'Removed' if allow_updates else 'Would remove'} "
                f"duplicate: uuid={dup_uuid} "
                f"(kept {keeper['uuid']}, source={src_path})")
            stats['duplicates_removed'] += 1

    # ── Phase 3: Clear missing source paths, find orphan files ────
    if cancel_event and cancel_event.is_set():
        logger.warn("Audit cancelled by user")
        return stats

    logger.info("=== Phase 3: Clearing stale source paths ===")
    # Re-fetch after dedup
    tracks = track_db.get_all_tracks()
    for track in tracks:
        if cancel_event and cancel_event.is_set():
            logger.warn("Audit cancelled by user")
            return stats
        source_m4a = track.get('source_m4a_path')
        if not source_m4a:
            continue
        source_path = Path(source_m4a)
        if not source_path.is_absolute():
            source_path = root / source_path
        if not source_path.exists():
            if allow_updates:
                track_db.repair_track(track['uuid'],
                                      source_m4a_path=None)
            else:
                logger.dry_run(
                    f"Would clear missing source_m4a_path "
                    f"for {track['uuid']}")
            _detail(
                f"{'Cleared' if allow_updates else 'Would clear'} "
                f"missing source_m4a_path for {track['uuid']}")
            stats['source_cleared'] += 1

    logger.info("=== Phase 3b: Finding orphan files on disk ===")

    # Orphan MP3s
    if audio_dir.exists():
        for mp3_file in sorted(audio_dir.glob('*.mp3')):
            if cancel_event and cancel_event.is_set():
                logger.warn("Audit cancelled by user")
                return stats
            rel_path = str(Path(get_audio_dir()) / mp3_file.name)
            if not track_db.get_track_by_path(rel_path):
                if allow_updates:
                    mp3_file.unlink()
                else:
                    logger.dry_run(
                        f"Would delete orphan file: {rel_path}")
                _detail(
                    f"{'Deleted' if allow_updates else 'Would delete'} "
                    f"orphan file: {rel_path}")
                stats['orphan_files_removed'] += 1

    # Orphan artwork
    if artwork_dir.exists():
        for art_file in sorted(artwork_dir.iterdir()):
            if cancel_event and cancel_event.is_set():
                logger.warn("Audit cancelled by user")
                return stats
            if not art_file.is_file():
                continue
            rel_art = str(Path(get_artwork_dir()) / art_file.name)
            if rel_art not in referenced_artwork:
                if allow_updates:
                    art_file.unlink()
                else:
                    logger.dry_run(
                        f"Would delete orphan artwork: {rel_art}")
                _detail(
                    f"{'Deleted' if allow_updates else 'Would delete'} "
                    f"orphan artwork: {rel_art}")
                stats['orphan_artwork_removed'] += 1

    # Orphan source M4As
    logger.info("=== Phase 3c: Finding orphan source M4A files ===")
    source_base = root / SOURCE_SUBDIR / DEFAULT_IMPORTER
    if source_base.exists():
        all_source_m4as = {
            str(p.relative_to(root))
            for p in source_base.rglob('*.m4a')
        }
        all_db_m4as = {
            t.get('source_m4a_path') or ''
            for t in track_db.get_all_tracks()
        }
        for m4a_rel in sorted(all_source_m4as):
            if cancel_event and cancel_event.is_set():
                logger.warn("Audit cancelled by user")
                return stats
            if m4a_rel not in all_db_m4as:
                m4a_path = root / m4a_rel
                if allow_updates:
                    try:
                        m4a_path.unlink()
                    except OSError as exc:
                        logger.warn(f"Could not delete orphan M4A {m4a_rel}: {exc}")
                else:
                    logger.dry_run(
                        f"Would delete orphan source M4A: {m4a_rel}")
                _detail(
                    f"{'Deleted' if allow_updates else 'Would delete'} "
                    f"orphan source M4A: {m4a_rel}")
                stats['orphan_source_m4as_removed'] += 1
    else:
        logger.info("  Source directory not found — skipping M4A scan")

    # ── Phase 4: Cross-check sync DB against track DB ─────────────
    if sync_tracker:
        if cancel_event and cancel_event.is_set():
            logger.warn("Audit cancelled by user")
            return stats

        logger.info("=== Phase 4: Verifying sync records against track DB ===")
        all_sync_files = sync_tracker.get_all_sync_files()
        # Get all playlists that still have tracks
        db_playlists = set(track_db.get_all_playlists())
        stale_ids = []

        for sf in all_sync_files:
            if sf['playlist'] not in db_playlists:
                stale_ids.append(sf['id'])
                _detail(
                    f"Stale sync record: key={sf['sync_key']}, "
                    f"playlist={sf['playlist']}, file={sf['file_path']} "
                    f"(playlist no longer in library)")

        if stale_ids:
            if allow_updates:
                removed = sync_tracker.delete_sync_files_by_ids(stale_ids)
                stats['sync_records_removed'] = removed
                logger.info(f"Removed {removed} stale sync records")
            else:
                stats['sync_records_removed'] = len(stale_ids)
                logger.dry_run(
                    f"Would remove {len(stale_ids)} stale sync records")

        # UUID-level orphans: sync_files referencing deleted track UUIDs
        stale_id_set = set(stale_ids)
        uuid_orphans = sync_tracker.get_all_orphaned_files()
        uuid_orphan_ids = [sf['id'] for sf in uuid_orphans
                           if sf['id'] not in stale_id_set]
        for sf in uuid_orphans:
            if sf['id'] in stale_id_set:
                continue
            _detail(
                f"Orphaned sync record (deleted track): key={sf['sync_key']}, "
                f"uuid={sf['track_uuid']}, file={sf['file_path']}")
        if uuid_orphan_ids:
            if allow_updates:
                removed = sync_tracker.delete_sync_files_by_ids(uuid_orphan_ids)
                stats['sync_uuid_orphans_removed'] = removed
                logger.info(
                    f"Removed {removed} UUID-orphaned sync records")
            else:
                stats['sync_uuid_orphans_removed'] = len(uuid_orphan_ids)
                logger.dry_run(
                    f"Would remove {len(uuid_orphan_ids)} UUID-orphaned sync records")
    else:
        logger.info("Phase 4: Skipped (no sync tracker)")

    # ── Phase 5: Orphaned playlist tracks ─────────────────────────
    if cancel_event and cancel_event.is_set():
        logger.warn("Audit cancelled by user")
        return stats

    logger.info("=== Phase 5: Detecting tracks with missing playlist references ===")
    orphaned_pl_tracks = track_db.get_orphaned_playlist_tracks()
    if orphaned_pl_tracks:
        for track in orphaned_pl_tracks:
            if cancel_event and cancel_event.is_set():
                logger.warn("Audit cancelled by user")
                return stats
            uuid = track['uuid']
            playlist = track.get('playlist', '')
            title = track.get('title', '')
            if allow_updates:
                # Delete MP3
                mp3_rel = track.get('file_path')
                if mp3_rel:
                    mp3_path = root / mp3_rel
                    try:
                        if mp3_path.exists():
                            mp3_path.unlink()
                    except OSError as exc:
                        logger.warn(f"Could not delete MP3 for orphaned track {uuid}: {exc}")
                # Delete artwork
                art_rel = track.get('cover_art_path')
                if art_rel:
                    art_path = root / art_rel
                    try:
                        if art_path.exists():
                            art_path.unlink()
                    except OSError as exc:
                        logger.warn(f"Could not delete artwork for orphaned track {uuid}: {exc}")
                # Delete TrackDB record
                track_db.delete_track(uuid)
            else:
                logger.dry_run(
                    f"Would remove track {uuid} ({title!r}) "
                    f"— playlist {playlist!r} no longer exists")
            _detail(
                f"{'Removed' if allow_updates else 'Would remove'} "
                f"orphaned track {uuid} ({title!r}) from deleted playlist {playlist!r}")
            stats['orphaned_playlist_tracks_removed'] += 1
    else:
        logger.info("  No orphaned playlist tracks found")

    # ── Summary ───────────────────────────────────────────────────
    stats['allow_updates'] = allow_updates
    mode_label = "Audit Summary" if allow_updates else "Audit Summary (report only)"
    logger.info(f"=== {mode_label} ===")
    verb = "" if allow_updates else "would be "
    logger.info(f"  Tracks checked:        {stats['total_tracks_checked']}")
    logger.info(f"  DB records {verb}removed:    {stats['records_removed']}")
    logger.info(f"  Orphan files {verb}removed:  {stats['orphan_files_removed']}")
    logger.info(f"  Orphan artwork {verb}removed:{stats['orphan_artwork_removed']}")
    logger.info(f"  Cover art {verb}cleared:     {stats['cover_art_cleared']}")
    logger.info(f"  Source paths {verb}cleared:  {stats['source_cleared']}")
    logger.info(f"  Paths {verb}normalized:      {stats['paths_normalized']}")
    logger.info(f"  Sizes {verb}updated:         {stats['sizes_updated']}")
    logger.info(f"  Duplicates {verb}removed:    {stats['duplicates_removed']}")
    logger.info(f"  Sync records {verb}removed:  {stats['sync_records_removed']}")
    logger.info(
        f"  Sync UUID orphans {verb}removed: "
        f"{stats['sync_uuid_orphans_removed']}")
    logger.info(
        f"  Orphan M4As {verb}removed:   {stats['orphan_source_m4as_removed']}")
    logger.info(
        f"  Orphan playlist tracks {verb}removed: "
        f"{stats['orphaned_playlist_tracks_removed']}")
    return stats


# ══════════════════════════════════════════════════════════════════
# Section 8A: Library Summary Management
# ══════════════════════════════════════════════════════════════════

class MusicLibraryStats:
    """Statistics for the source M4A library (library/<playlist>/source/)."""

    def __init__(self):
        self.total_playlists = 0
        self.total_files = 0
        self.total_size_bytes = 0
        self.total_exported = 0
        self.total_unconverted = 0
        self.scan_duration = 0.0
        self.playlists = []  # List of dicts: {name, m4a_count, size_bytes, exported_count, unconverted_count}


class SummaryManager:
    """Scans library directories for source/output statistics."""

    def __init__(self, logger=None):
        self.logger = logger or Logger()

    def scan_music_library(self, track_db=None):
        """Scan library/source/gamdl/ for M4A stats and conversion status.

        Uses TrackDB for per-playlist MP3 counts when available, otherwise
        counts MP3s in the flat library/audio/ directory.

        Returns:
            MusicLibraryStats or None if source directory doesn't exist
        """
        source_root = Path(DEFAULT_LIBRARY_DIR) / SOURCE_SUBDIR / DEFAULT_IMPORTER
        if not source_root.exists():
            return None

        stats = MusicLibraryStats()
        start_time = time.time()

        # Get per-playlist MP3 counts from TrackDB.
        # exported_count uses only active (non-hidden) tracks for display.
        # converted_count includes hidden tracks so they are not falsely
        # reported as unconverted when a track is hidden.
        db_counts = {}
        if track_db:
            for ps in track_db.get_playlist_stats():
                db_counts[ps['playlist']] = {
                    'exported': ps['track_count'],
                    'converted': ps['total_track_count'],
                }

        try:
            for item in sorted(source_root.iterdir(), key=lambda p: p.name):
                if not item.is_dir() or item.name.startswith('.'):
                    continue

                playlist_name = item.name

                m4a_count = 0
                size_bytes = 0

                # Walk recursively — source has nested Artist/Album/Track.m4a structure
                for root, _dirs, files in os.walk(item):
                    for f in files:
                        if f.lower().endswith('.m4a'):
                            m4a_count += 1
                            try:
                                size_bytes += os.path.getsize(
                                    os.path.join(root, f))
                            except OSError:
                                pass

                if m4a_count == 0:
                    continue

                # exported_count: active tracks only (for display)
                # converted_count: all tracks including hidden (for unconverted calc)
                playlist_db = db_counts.get(playlist_name, {})
                exported_count = playlist_db.get('exported', 0)
                converted_count = playlist_db.get('converted', 0)
                unconverted_count = max(0, m4a_count - converted_count)

                stats.playlists.append({
                    'name': playlist_name,
                    'm4a_count': m4a_count,
                    'size_bytes': size_bytes,
                    'exported_count': exported_count,
                    'unconverted_count': unconverted_count,
                })

                stats.total_files += m4a_count
                stats.total_size_bytes += size_bytes
                stats.total_exported += exported_count
                stats.total_unconverted += unconverted_count

        except PermissionError as e:
            self.logger.warn(
                f"Permission denied accessing library directory: {e}")
        except Exception as e:
            self.logger.warn(f"Error scanning library directory: {e}")

        stats.total_playlists = len(stats.playlists)
        stats.scan_duration = time.time() - start_time

        return stats



# ══════════════════════════════════════════════════════════════════
# Section 8b: Data Management (Deletion)
# ══════════════════════════════════════════════════════════════════

class DataManager:
    """Manages playlist data lifecycle (deletion, cleanup)."""

    def __init__(self, logger=None, config=None, prompt_handler=None, output_profile=None,
                 audit_logger=None, audit_source='cli', track_db=None,
                 playlist_db=None):
        self.logger = logger or Logger()
        self.config = config or ConfigManager(logger=self.logger)
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self.track_db = track_db
        self.playlist_db = playlist_db

    def delete_playlist_data(self, playlist_key, delete_source=True, delete_library=True,
                             remove_config=False, dry_run=False):
        """Delete source M4A and/or library MP3/artwork for a playlist.

        Source files are in library/source/<importer>/<playlist>/ (directory).
        MP3 and artwork files are in flat dirs — identified via TrackDB.

        Returns DeleteResult with stats about what was deleted.
        """
        # Determine importer from playlist source_type (falls back to gamdl)
        importer = DEFAULT_IMPORTER
        if self.playlist_db:
            pl = self.playlist_db.get(playlist_key)
            if pl and pl.get('source_type') == 'youtube_music':
                importer = IMPORTER_YTDLP
        source_dir = Path(get_source_dir(playlist_key, importer))

        errors = []
        files_deleted = 0
        bytes_freed = 0
        source_deleted = False
        library_deleted = False
        config_removed = False

        # Count source files
        source_files = 0
        source_bytes = 0
        if delete_source and source_dir.exists():
            for f in source_dir.rglob('*'):
                if f.is_file():
                    source_files += 1
                    source_bytes += f.stat().st_size

        # Count library files (MP3 + artwork) via TrackDB
        lib_files = 0
        lib_bytes = 0
        lib_file_paths = []  # (path, is_mp3_or_art)
        if delete_library and self.track_db:
            tracks = self.track_db.get_tracks_by_playlist(playlist_key)
            for t in tracks:
                # MP3 file
                mp3_path = Path(t['file_path'])
                if mp3_path.exists():
                    lib_files += 1
                    lib_bytes += mp3_path.stat().st_size
                    lib_file_paths.append(mp3_path)
                # Artwork file
                if t.get('cover_art_path'):
                    art_path = Path(t['cover_art_path'])
                    if art_path.exists():
                        lib_files += 1
                        lib_bytes += art_path.stat().st_size
                        lib_file_paths.append(art_path)

        total_files = source_files + lib_files
        total_bytes = source_bytes + lib_bytes

        if total_files == 0 and not remove_config:
            self.logger.info(f"Nothing to delete for '{playlist_key}'")
            return DeleteResult(success=True, playlist_key=playlist_key, dry_run=dry_run)

        # Build summary for confirmation
        parts = []
        if source_files > 0:
            parts.append(f"{source_files} source files ({_format_bytes(source_bytes)})")
        if lib_files > 0:
            parts.append(f"{lib_files} library files ({_format_bytes(lib_bytes)})")
        if remove_config:
            parts.append("config entry")

        summary = f"Delete {', '.join(parts)} for '{playlist_key}'?"
        self.logger.info(f"\n  {summary}")

        if dry_run:
            if delete_source and source_dir.exists():
                self.logger.info(f"  [DRY-RUN] Would delete: {source_dir}/ ({source_files} files, {_format_bytes(source_bytes)})")
            if lib_files > 0:
                self.logger.info(f"  [DRY-RUN] Would delete: {lib_files} library files ({_format_bytes(lib_bytes)})")
            if remove_config:
                self.logger.info(f"  [DRY-RUN] Would remove config entry for '{playlist_key}'")
            return DeleteResult(
                success=True, playlist_key=playlist_key,
                files_deleted=total_files, bytes_freed=total_bytes,
                dry_run=True)

        # Confirm destructive action
        if not self.prompt_handler.confirm_destructive(summary):
            self.logger.info("Cancelled")
            return DeleteResult(success=False, playlist_key=playlist_key)

        # Delete source directory
        if delete_source and source_dir.exists():
            try:
                shutil.rmtree(source_dir)
                source_deleted = True
                files_deleted += source_files
                bytes_freed += source_bytes
                self.logger.info(f"  Deleted source: {source_dir}/ ({source_files} files, {_format_bytes(source_bytes)})")
            except OSError as e:
                errors.append(f"Failed to delete {source_dir}: {e}")
                self.logger.error(errors[-1])

        # Delete library files (MP3 + artwork) individually from flat dirs
        if delete_library and lib_file_paths:
            deleted_count = 0
            deleted_bytes = 0
            for fpath in lib_file_paths:
                try:
                    sz = fpath.stat().st_size
                    fpath.unlink()
                    deleted_count += 1
                    deleted_bytes += sz
                except OSError as e:
                    errors.append(f"Failed to delete {fpath}: {e}")
                    self.logger.error(errors[-1])
            if deleted_count > 0:
                library_deleted = True
                files_deleted += deleted_count
                bytes_freed += deleted_bytes
                self.logger.info(f"  Deleted library: {deleted_count} files ({_format_bytes(deleted_bytes)})")
            # Remove TrackDB entries
            if self.track_db:
                self.track_db.delete_tracks_by_playlist(playlist_key)

        # Remove playlist entry
        if remove_config:
            removed = False
            if self.playlist_db:
                removed = self.playlist_db.remove(playlist_key)
            if removed:
                config_removed = True
                self.logger.info(f"  Removed playlist entry for '{playlist_key}'")
            else:
                self.logger.info(f"  Playlist entry for '{playlist_key}' not found")

        result = DeleteResult(
            success=len(errors) == 0,
            playlist_key=playlist_key,
            source_deleted=source_deleted,
            library_deleted=library_deleted,
            config_removed=config_removed,
            files_deleted=files_deleted,
            bytes_freed=bytes_freed,
            errors=errors)
        if self.audit_logger and not dry_run:
            self.audit_logger.log(
                'playlist_delete_data', f"Delete data: {playlist_key}",
                'completed' if result.success else 'failed',
                params={'playlist_key': playlist_key,
                        'files_deleted': files_deleted,
                        'bytes_freed': bytes_freed},
                source=self._audit_source)
        return result


# ══════════════════════════════════════════════════════════════════
# Section 9: Pipeline Orchestration
# ══════════════════════════════════════════════════════════════════

class PipelineStatistics:
    """Aggregate statistics across all pipeline stages."""

    def __init__(self):
        # Download stats
        self.download_success = False
        self.playlist_key = None
        self.playlist_name = None
        self.playlist_importer = DEFAULT_IMPORTER  # gamdl or ytdlp
        self.download_stats = None  # DownloadStatistics object

        # Conversion stats
        self.conversion_stats: ConversionStatistics | None = None

        # Tagging stats
        self.tagging_stats = None

        # Sync stats
        self.sync_success = False
        self.sync_destination = None
        self.sync_stats: dict | None = None

        # Overall
        self.start_time = time.time()
        self.stages_completed = []
        self.stages_failed = []
        self.stages_skipped = []
        self.tracks_removed = 0
        self.bytes_freed_from_removal = 0


class PlaylistResult:
    """Results for a single playlist in multi-playlist processing."""

    def __init__(self, key, name):
        self.key = key
        self.name = name
        self.success = False
        self.failed_stage = None  # "download", "convert", "sync"
        self.download_stats = None  # DownloadStatistics
        self.conversion_stats = None  # ConversionStatistics
        self.tagging_stats = None
        self.sync_success = False
        self.duration = 0.0


class AggregateStatistics:
    """Tracks cumulative statistics across multiple playlists."""

    def __init__(self):
        self.playlist_results = []  # List[PlaylistResult]
        self.total_playlists = 0
        self.successful_playlists = 0
        self.failed_playlists = 0
        self.start_time = time.time()
        self.end_time: float | None = None
        self.usb_destination = None

    def add_playlist_result(self, orchestrator_stats):
        """Add results from a PipelineOrchestrator run."""
        result = PlaylistResult(
            orchestrator_stats.playlist_key,
            orchestrator_stats.playlist_name
        )
        result.success = len(orchestrator_stats.stages_failed) == 0
        result.failed_stage = orchestrator_stats.stages_failed[0] if orchestrator_stats.stages_failed else None
        result.download_stats = orchestrator_stats.download_stats
        result.conversion_stats = orchestrator_stats.conversion_stats
        result.tagging_stats = orchestrator_stats.tagging_stats
        result.sync_success = orchestrator_stats.sync_success
        result.duration = time.time() - orchestrator_stats.start_time

        self.playlist_results.append(result)
        self.total_playlists += 1
        if result.success:
            self.successful_playlists += 1
        else:
            self.failed_playlists += 1

        if orchestrator_stats.sync_destination:
            self.usb_destination = orchestrator_stats.sync_destination

    def get_cumulative_stats(self):
        """Calculate cumulative statistics across all playlists."""
        totals = {
            'playlist_total': 0,
            'downloaded': 0,
            'skipped_download': 0,
            'failed_download': 0,
            'converted': 0,
            'overwritten': 0,
            'skipped_conversion': 0,
            'errors_conversion': 0,
            'mp3_total': 0,
            'title_updated': 0,
            'original_tags_stored': 0,
            'files_on_usb': 0
        }

        for result in self.playlist_results:
            if result.download_stats:
                totals['playlist_total'] += result.download_stats.playlist_total
                totals['downloaded'] += result.download_stats.downloaded
                totals['skipped_download'] += result.download_stats.skipped
                totals['failed_download'] += result.download_stats.failed

            if result.conversion_stats:
                totals['converted'] += result.conversion_stats.converted
                totals['overwritten'] += result.conversion_stats.overwritten
                totals['skipped_conversion'] += result.conversion_stats.skipped
                totals['errors_conversion'] += result.conversion_stats.errors
                totals['mp3_total'] += result.conversion_stats.mp3_total

            if result.tagging_stats:
                totals['title_updated'] += result.tagging_stats.title_updated
                totals['original_tags_stored'] += (
                    result.tagging_stats.title_stored +
                    result.tagging_stats.artist_stored +
                    result.tagging_stats.album_stored
                )

            if result.sync_success and result.conversion_stats:
                totals['files_on_usb'] += result.conversion_stats.mp3_total

        return totals

    def to_result(self) -> AggregateResult:
        """Convert to AggregateResult for rendering."""
        duration = (self.end_time or time.time()) - self.start_time
        return AggregateResult(
            success=self.failed_playlists == 0,
            duration=duration,
            total_playlists=self.total_playlists,
            successful_playlists=self.successful_playlists,
            failed_playlists=self.failed_playlists,
            playlist_results=self.playlist_results,
            cumulative_stats=self.get_cumulative_stats(),
            usb_destination=self.usb_destination,
        )


class PipelineOrchestrator:
    """Coordinates multi-stage workflows: download → convert → sync."""

    def __init__(self, logger=None, deps=None, config=None, quality_preset='lossless',
                 cookie_path=DEFAULT_COOKIES, workers=None,
                 prompt_handler=None, display_handler=None,
                 cancel_event=None, audit_logger=None, audit_source='cli',
                 sync_tracker=None, track_db=None, playlist_db=None,
                 eq_config_manager=None, eq_config_override=None,
                 project_root=None,
                 cleanup_removed_tracks_enabled=False):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.audit_logger = audit_logger
        self.eq_config_manager = eq_config_manager
        self.eq_config_override = eq_config_override
        self._audit_source = audit_source
        self.sync_tracker = sync_tracker
        self.track_db = track_db
        self.playlist_db = playlist_db
        self.deps = deps or DependencyChecker(self.logger)
        self.config = config or ConfigManager(logger=self.logger)
        self.stats = PipelineStatistics()
        self.quality_preset = quality_preset
        self.cookie_path = cookie_path
        self.workers = workers
        self.project_root = Path(project_root) if project_root else Path('.')
        self.cleanup_removed_tracks_enabled = cleanup_removed_tracks_enabled
        self.clean_destination_enabled = False  # set via run_full_pipeline param

    def run_full_pipeline(self, playlist=None, url=None, auto=False,
                         sync_destination=None,
                         dry_run=False, verbose=False, quality_preset=None,
                         validate_cookies=True, auto_refresh_cookies=False,
                         cleanup_removed_tracks_enabled=None,
                         clean_destination_enabled=None):
        """Execute the complete pipeline: download → convert → sync.

        Args:
            sync_destination: SyncDestination object for post-pipeline sync (optional)
            cleanup_removed_tracks_enabled: override instance default for removed track cleanup
            clean_destination_enabled: when True, remove orphaned files from the sync destination
        """
        if cleanup_removed_tracks_enabled is None:
            cleanup_removed_tracks_enabled = self.cleanup_removed_tracks_enabled
        if clean_destination_enabled is None:
            clean_destination_enabled = self.clean_destination_enabled
        self.stats.start_time = time.time()
        convert_result = None
        usb_result = None
        removed_tracks_found = []
        cleanup_result = None

        # ── Stage 1: Determine source ─────────────────────────────────
        if url:
            self.logger.info("=== STAGE 1: Download from URL ===")
            success = self._download_from_url(url, auto, dry_run, verbose,
                                             validate_cookies, auto_refresh_cookies)
            if not success:
                duration = time.time() - self.stats.start_time
                return PipelineResult(
                    success=False, playlist_name=self.stats.playlist_name,
                    playlist_key=self.stats.playlist_key, duration=duration,
                    stages_failed=list(self.stats.stages_failed),
                    stages_completed=list(self.stats.stages_completed),
                    stages_skipped=list(self.stats.stages_skipped))

        elif playlist:
            self.logger.info("=== STAGE 1: Download playlist ===")
            success = self._download_playlist(playlist, auto, dry_run, verbose,
                                             validate_cookies, auto_refresh_cookies)
            if not success:
                duration = time.time() - self.stats.start_time
                return PipelineResult(
                    success=False, playlist_name=self.stats.playlist_name,
                    playlist_key=self.stats.playlist_key, duration=duration,
                    stages_failed=list(self.stats.stages_failed),
                    stages_completed=list(self.stats.stages_completed),
                    stages_skipped=list(self.stats.stages_skipped))

        else:
            self.logger.error(
                "Either --playlist or --url must be specified for pipeline")
            duration = time.time() - self.stats.start_time
            return PipelineResult(
                success=False, playlist_name=None, playlist_key=None,
                duration=duration, stages_failed=["download"])

        # ── Cancellation check before Stage 2 ────────────────────────
        if _is_cancelled(self.cancel_event):
            self.logger.warn("Pipeline cancelled by user")
            duration = time.time() - self.stats.start_time
            return PipelineResult(
                success=False, playlist_name=self.stats.playlist_name,
                playlist_key=self.stats.playlist_key, duration=duration,
                stages_completed=list(self.stats.stages_completed),
                stages_failed=["cancelled"],
                stages_skipped=list(self.stats.stages_skipped))

        # ── Removed track detection (between Stage 1 and Stage 2) ────
        dl_stats = self.stats.download_stats
        if dl_stats and self.stats.playlist_key and self.track_db:
            removed_tracks_found = detect_removed_tracks(
                self.stats.playlist_key,
                dl_stats.playlist_track_names,
                self.track_db,
                logger=self.logger,
            )
            if removed_tracks_found:
                self.logger.info(
                    f"Removed from playlist: {len(removed_tracks_found)} track(s)")
                for t in removed_tracks_found:
                    self.logger.info(f"  Removed: {t['title']} — {t['artist']}")

        # ── Stage 2: Convert M4A → clean library MP3 ─────────────────
        self.logger.info("\n=== STAGE 2: Convert M4A → MP3 ===")
        music_dir = str(self.project_root / get_source_dir(
            self.stats.playlist_key, self.stats.playlist_importer))
        library_dir = str(self.project_root / get_audio_dir())

        preset = (quality_preset if quality_preset is not None
                  else self.quality_preset)

        # Resolve EQ: override > DB playlist > none
        eq_config = self.eq_config_override
        if eq_config is None and self.eq_config_manager:
            eq_config = self.eq_config_manager.get_eq(
                DEFAULT_OUTPUT_TYPE, self.stats.playlist_key)

        converter = Converter(
            self.logger, quality_preset=preset, workers=self.workers,
            track_db=self.track_db,
            display_handler=self.display_handler,
            cancel_event=self.cancel_event,
            eq_config=eq_config)
        convert_result = converter.convert(
            music_dir, library_dir,
            playlist_key=self.stats.playlist_key,
            force=False, dry_run=dry_run, verbose=verbose)

        if convert_result.success:
            self.stats.stages_completed.append("convert")
            self.stats.conversion_stats = converter.stats
            # ── Duplicate detection (post-convert) ───────────────────────
            if self.track_db and self.stats.playlist_key:
                dup_hidden = self.track_db.hide_duplicates(self.stats.playlist_key)
                if dup_hidden > 0:
                    self.logger.info(
                        f"Duplicate detection: hid {dup_hidden} duplicate track(s)")
        else:
            self.stats.stages_failed.append("convert")
            self.logger.error("Conversion stage failed")

        # ── Library cleanup (removed tracks) ─────────────────────────
        if cleanup_removed_tracks_enabled and removed_tracks_found:
            cleanup_result = cleanup_removed_tracks(
                removed_tracks_found,
                track_db=self.track_db,
                sync_tracker=self.sync_tracker,
                logger=self.logger,
                project_root=self.project_root,
                audit_logger=self.audit_logger,
                audit_source=self._audit_source,
            )
            self.stats.tracks_removed = cleanup_result.get('tracks_cleaned', 0)
            self.stats.bytes_freed_from_removal = cleanup_result.get('bytes_freed', 0)

        # ── Cancellation check before Stage 3 ────────────────────────
        if _is_cancelled(self.cancel_event):
            self.logger.warn("Pipeline cancelled by user")
            duration = time.time() - self.stats.start_time
            return PipelineResult(
                success=False, playlist_name=self.stats.playlist_name,
                playlist_key=self.stats.playlist_key, duration=duration,
                stages_completed=list(self.stats.stages_completed),
                stages_failed=["cancelled"],
                stages_skipped=list(self.stats.stages_skipped))

        # ── Stage 3: Sync (optional) ─────────────────────────────────
        if sync_destination:
            sync_mgr = SyncManager(
                self.logger, prompt_handler=self.prompt_handler,
                display_handler=self.display_handler,
                cancel_event=self.cancel_event,
                sync_tracker=self.sync_tracker)
            self.logger.info(
                f"\n=== STAGE 3: Sync to {sync_destination.name} ===")
            usb_result = sync_mgr.sync_to_destination(
                library_dir, dest_path=sync_destination.path,
                sync_key=sync_destination.sync_key, dry_run=dry_run,
                clean_destination=clean_destination_enabled)

            if usb_result.success:
                self.stats.stages_completed.append("sync")
                self.stats.sync_stats = {
                    "files_copied": usb_result.files_copied,
                    "files_skipped": usb_result.files_skipped,
                }
                self.stats.sync_success = True
                self.stats.sync_destination = usb_result.destination
            else:
                self.stats.stages_failed.append("sync")
                self.logger.error("Sync stage failed")

        duration = time.time() - self.stats.start_time
        if self.audit_logger:
            self.audit_logger.log(
                'pipeline',
                f"Pipeline: {self.stats.playlist_name or 'unknown'}",
                'completed' if not self.stats.stages_failed else 'failed',
                params={
                    'playlist_key': self.stats.playlist_key,
                    'stages_completed': list(self.stats.stages_completed),
                    'stages_failed': list(self.stats.stages_failed),
                    'tracks_removed': self.stats.tracks_removed,
                    'bytes_freed_from_removal': self.stats.bytes_freed_from_removal,
                },
                duration_s=duration, source=self._audit_source)

        return PipelineResult(
            success=not self.stats.stages_failed,
            playlist_name=self.stats.playlist_name,
            playlist_key=self.stats.playlist_key,
            duration=duration,
            stages_completed=list(self.stats.stages_completed),
            stages_failed=list(self.stats.stages_failed),
            stages_skipped=list(self.stats.stages_skipped),
            download_result=self.stats.download_stats,
            conversion_result=convert_result,
            usb_result=usb_result,
            usb_destination=self.stats.sync_destination,
            removed_tracks=removed_tracks_found,
            cleanup_stats=cleanup_result,
        )

    def _download_from_url(self, url, auto, dry_run, verbose,
                           validate_cookies=True, auto_refresh_cookies=False):
        """Download playlist from URL."""
        downloader = Downloader(self.logger, self.deps.venv_python,
                               cookie_path=self.cookie_path,
                               prompt_handler=self.prompt_handler,
                               display_handler=self.display_handler,
                               cancel_event=self.cancel_event)

        key, album_name = downloader.extract_url_info(url)
        if not key:
            self.logger.error(f"Could not extract playlist info from URL: {url}")
            self.stats.stages_failed.append("download")
            return False

        output_dir = get_source_dir(key)

        # Ask to save to config BEFORE download (only if not dry-run and not auto)
        if not dry_run and not auto:
            self._ask_save_to_config(key, url, album_name)

        dl_result = downloader.download(
            url,
            output_dir,
            key=key,
            confirm=not auto,
            dry_run=dry_run,
            validate_cookies=validate_cookies,
            auto_refresh=auto_refresh_cookies
        )

        if dl_result.success:
            self.stats.download_success = True
            self.stats.playlist_key = dl_result.key
            self.stats.playlist_name = dl_result.album_name
            self.stats.download_stats = dl_result
            self.stats.stages_completed.append("download")

            return True
        else:
            # Check if user skipped (no stats and we have key/album_name)
            # In this case, store the info and allow pipeline to continue
            if dl_result.downloaded == 0 and dl_result.failed == 0 and dl_result.key and dl_result.album_name:
                self.stats.playlist_key = dl_result.key
                self.stats.playlist_name = dl_result.album_name
                self.stats.stages_skipped.append("download")
                return True  # Continue to next stage
            else:
                # Actual failure
                self.stats.stages_failed.append("download")
                return False

    def _download_playlist(self, playlist_arg, auto, dry_run, verbose,
                           validate_cookies=True, auto_refresh_cookies=False):
        """Download playlist from configuration."""
        # Find playlist by key or index from PlaylistDB
        playlist = None
        if self.playlist_db:
            if playlist_arg.isdigit():
                all_pl = self.playlist_db.get_all()
                idx = int(playlist_arg) - 1
                if 0 <= idx < len(all_pl):
                    playlist = all_pl[idx]
            else:
                playlist = self.playlist_db.get(playlist_arg)

        if not playlist:
            self.logger.error(f"Playlist not found: {playlist_arg}")
            self.stats.stages_failed.append("download")
            return False

        pl_key = playlist['key']
        pl_name = playlist['name']
        pl_url = playlist['url']
        pl_source_type = playlist.get('source_type', 'apple_music')
        self.stats.playlist_key = pl_key
        self.stats.playlist_name = pl_name

        if pl_source_type == 'youtube_music':
            self.stats.playlist_importer = IMPORTER_YTDLP
            output_dir = get_source_dir(pl_key, IMPORTER_YTDLP)
            ytdl = YouTubeMusicDownloader(
                logger=self.logger,
                display_handler=self.display_handler,
                cancel_event=self.cancel_event,
            )
            dl_result = ytdl.download(
                pl_url,
                output_dir,
                key=pl_key,
                display_handler=self.display_handler,
                cancel_event=self.cancel_event,
            )
        else:
            self.stats.playlist_importer = DEFAULT_IMPORTER
            output_dir = get_source_dir(pl_key, DEFAULT_IMPORTER)
            downloader = Downloader(self.logger, self.deps.venv_python,
                                   cookie_path=self.cookie_path,
                                   prompt_handler=self.prompt_handler,
                                   display_handler=self.display_handler,
                                   cancel_event=self.cancel_event)
            dl_result = downloader.download(
                pl_url,
                output_dir,
                key=pl_key,
                confirm=not auto,
                dry_run=dry_run,
                validate_cookies=validate_cookies,
                auto_refresh=auto_refresh_cookies
            )

        if dl_result.success:
            self.stats.download_success = True
            self.stats.download_stats = dl_result
            self.stats.stages_completed.append("download")
            if self.playlist_db:
                self.playlist_db.record_download(pl_key)
            return True
        else:
            # Check if user skipped (no stats and we have playlist info)
            # In this case, allow pipeline to continue
            if dl_result.downloaded == 0 and dl_result.failed == 0 and self.stats.playlist_key:
                self.stats.stages_skipped.append("download")
                if self.playlist_db:
                    self.playlist_db.record_download(pl_key)
                return True  # Continue to next stage
            else:
                # Actual failure
                self.stats.stages_failed.append("download")
                return False

    def _ask_save_to_config(self, key, url, album_name):
        """Ask user if they want to save a new playlist."""
        if self.prompt_handler.confirm(f"Save '{album_name}' to configuration?", default=False):
            if self.playlist_db:
                self.playlist_db.add(key, url, album_name)


