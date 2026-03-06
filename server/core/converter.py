"""
core.converter - Converter and ConversionStatistics.

Handles M4A → MP3 conversion using ffmpeg with TagApplicator for ID3 tags.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.config import NullDisplayHandler
from core.constants import (
    APIC_MIME_PNG,
    DEFAULT_QUALITY_PRESET,
    DEFAULT_WORKERS,
    QUALITY_PRESETS,
    TXXX_TRACK_UUID,
)
from core.logging import Logger
from core.models import ConversionResult, EQConfig, _DisplayProgress
from core.utils import (
    _is_cancelled,
    get_artwork_dir,
    get_audio_dir,
    get_source_dir,
    read_m4a_cover_art,
    read_m4a_tags,
    sanitize_filename,
)

# Third-party imports — set by _init_third_party()
_ffmpeg = None
_mutagen_id3 = None
_mutagen_mp3 = None
_TXXX = None
_ID3NoHeaderError = None

# ══════════════════════════════════════════════════════════════════
# Section 6: Conversion Module
# ══════════════════════════════════════════════════════════════════

class ConversionStatistics:
    """Tracks conversion operation statistics (thread-safe)."""

    def __init__(self):
        self.total_found = 0
        self.converted = 0
        self.overwritten = 0
        self.skipped = 0
        self.errors = 0
        self.mp3_total = 0
        self._lock = threading.Lock()
        self._progress_counter = 0

    def increment(self, field):
        """Thread-safe increment of a statistics field."""
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def next_progress(self):
        """Return the next 1-based progress number atomically."""
        with self._lock:
            self._progress_counter += 1
            return self._progress_counter


class Converter:
    """Converts M4A files to clean library MP3s.

    Library MP3s contain only a TXXX:TrackUUID identifier tag.
    All human-readable metadata (title, artist, album) is stored in TrackDB.
    Cover art is extracted to disk files.
    Profile-specific tags are applied later by TagApplicator during sync/download.
    """

    def __init__(self, logger=None, quality_preset='lossless', workers=None,
                 track_db=None, display_handler=None, cancel_event=None,
                 audit_logger=None, audit_source='cli', eq_config=None):
        self.logger = logger or Logger()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self.stats = ConversionStatistics()
        self.quality_preset = quality_preset
        self.quality_settings = self._get_quality_settings(quality_preset)
        self.workers = workers if workers is not None else DEFAULT_WORKERS
        self.track_db = track_db
        self.eq_config = eq_config or EQConfig()

    def _get_quality_settings(self, preset):
        """Resolve quality preset to FFmpeg parameters."""
        # Check predefined presets
        if preset in QUALITY_PRESETS:
            return QUALITY_PRESETS[preset]

        # Custom quality value (0-9 for VBR)
        try:
            quality_val = int(preset)
            if 0 <= quality_val <= 9:
                return {'mode': 'vbr', 'value': str(quality_val)}
            else:
                self.logger.warn(f"Invalid quality '{preset}', using '{DEFAULT_QUALITY_PRESET}'")
                return QUALITY_PRESETS[DEFAULT_QUALITY_PRESET]
        except ValueError:
            self.logger.warn(f"Unknown preset '{preset}', using '{DEFAULT_QUALITY_PRESET}'")
            return QUALITY_PRESETS[DEFAULT_QUALITY_PRESET]

    def _sanitize_filename(self, name):
        """Remove invalid filename characters."""
        return sanitize_filename(name)

    def _build_output_filename(self, track_uuid: str) -> str:
        """Build library output filename: '<uuid>.mp3'."""
        return f"{track_uuid}.mp3"

    def _build_output_path(self, base_path: Path, filename: str) -> Path:
        """Build library output path — always flat: base_path/filename."""
        return base_path / filename

    @staticmethod
    def _extract_cover_art_to_disk(m4a_file, artwork_dir, track_uuid):
        """Extract cover art from M4A source and save to disk.

        Returns (relative_path, sha256_hash) or (None, None) if no art found.
        The relative_path is relative to the project root (e.g. library/artwork/<uuid>.ext).
        """
        import hashlib

        cover_data, cover_mime = read_m4a_cover_art(m4a_file)
        if not cover_data:
            return None, None

        ext = 'png' if cover_mime == APIC_MIME_PNG else 'jpg'
        artwork_dir = Path(artwork_dir)
        artwork_dir.mkdir(parents=True, exist_ok=True)

        art_filename = f"{track_uuid}.{ext}"
        art_path = artwork_dir / art_filename
        art_path.write_bytes(cover_data)

        art_hash = hashlib.sha256(cover_data).hexdigest()[:16]
        return f"{get_artwork_dir()}/{art_filename}", art_hash

    def _convert_single_file(self, input_file, input_path, output_path,
                             playlist_key, force, dry_run, verbose,
                             progress_bar=None):
        """Convert a single M4A file to a clean library MP3. Thread-safe."""
        import uuid as _uuid

        from mutagen.id3 import ID3, TXXX, ID3NoHeaderError  # type: ignore[attr-defined]
        from mutagen.mp3 import MP3

        display_name = input_file.relative_to(input_path)
        count = self.stats.next_progress()

        # Normalize source_m4a_path to always be relative
        # (e.g. library/source/gamdl/<key>/Artist/Album/Track.m4a)
        # regardless of whether input_path is absolute or relative
        rel_source = str(
            Path(get_source_dir(playlist_key)) / input_file.relative_to(input_path)
        )

        try:
            # Read M4A tags
            m4a_tags = read_m4a_tags(input_file)
            title = m4a_tags['title']
            artist = m4a_tags['artist']
            album = m4a_tags['album']
            human_label = f"{artist} - {title}"

            # Check TrackDB for existing conversion of this source M4A
            existing_track = None
            if self.track_db:
                existing_track = self.track_db.get_track_by_source_m4a(
                    rel_source)

            if existing_track:
                # Hidden tracks are never re-processed, even with force=True
                if existing_track.get('hidden'):
                    if progress_bar:
                        progress_bar.update(1)
                    return

                if not force:
                    self.stats.increment('skipped')
                    msg = (f"[{count}/{self.stats.total_found}] "
                           f"Skipping (already converted): {human_label}")
                    if progress_bar and not verbose:
                        self.logger.file_info(msg)
                    else:
                        self.logger.info(msg)
                    if progress_bar:
                        progress_bar.update(1)
                    return

                # Locked + force: reconvert audio only, preserve UUID and metadata
                if force and existing_track.get('locked'):
                    import ffmpeg as _locked_ffmpeg
                    existing_mp3 = Path(existing_track['file_path'])
                    if not existing_mp3.is_absolute():
                        existing_mp3 = output_path.parent / existing_mp3
                    try:
                        ffmpeg_params = {'acodec': 'libmp3lame'}
                        if self.quality_settings['mode'] == 'vbr':
                            ffmpeg_params['q:a'] = self.quality_settings['value']
                        else:
                            ffmpeg_params['b:a'] = (
                                self.quality_settings['value'] + 'k')
                        filter_chain = self.eq_config.build_filter_chain()
                        if filter_chain:
                            ffmpeg_params['af'] = filter_chain
                        (
                            _locked_ffmpeg
                            .input(str(input_file))
                            .output(str(existing_mp3), **ffmpeg_params)
                            .run(overwrite_output=True, quiet=True)
                        )
                        # Re-stamp TXXX:TrackUUID only
                        locked_uuid = existing_track['uuid']
                        id3_locked = ID3()
                        id3_locked.add(TXXX(encoding=3, desc=TXXX_TRACK_UUID,
                                            text=[locked_uuid]))
                        id3_locked.save(str(existing_mp3), v2_version=4, v1=0)
                        self.stats.increment('overwritten')
                        msg = (f"[{count}/{self.stats.total_found}] "
                               f"Reconverted (audio-only, locked): {human_label}")
                        if progress_bar and not verbose:
                            self.logger.file_info(msg)
                        else:
                            self.logger.info(msg)
                    except _locked_ffmpeg.Error as e:
                        err_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
                        self.logger.error(
                            f"FFmpeg error reconverting locked track '{human_label}': {err_msg}")
                        self.stats.increment('errors')
                    finally:
                        if progress_bar:
                            progress_bar.update(1)
                    return

            # Generate UUID first — used for both filename and DB record
            track_uuid = _uuid.uuid4().hex
            output_filename = self._build_output_filename(track_uuid)
            output_file = self._build_output_path(output_path, output_filename)

            # If force re-converting, delete old file + DB entry
            if existing_track and force:
                old_file_path = existing_track.get('file_path')
                if old_file_path:
                    old_path = Path(old_file_path)
                    if not old_path.is_absolute():
                        old_path = Path('.') / old_path
                    if old_path.exists():
                        old_path.unlink()
                # Clean up old cover art
                if existing_track.get('cover_art_path'):
                    old_art = Path(existing_track['cover_art_path'])
                    if not old_art.is_absolute():
                        old_art = Path('.') / old_art
                    if old_art.exists():
                        old_art.unlink()
                old_uuid = existing_track.get('uuid')
                if self.track_db and old_uuid:
                    self.track_db.delete_track(old_uuid)

            if verbose:
                self.logger.debug(f"Source file:  '{input_file}'")
                self.logger.debug(
                    f"File size:    {input_file.stat().st_size / 1024:.1f} KB")
                if existing_track and force:
                    self.logger.debug(
                        f"Force flag set — re-converting: {human_label}")
                quality_desc = f"{self.quality_settings['mode'].upper()}"
                if self.quality_settings['mode'] == 'vbr':
                    quality_desc += f" quality {self.quality_settings['value']}"
                else:
                    quality_desc += (
                        f" {self.quality_settings['value']}kbps")
                self.logger.debug(
                    f"Quality:      {quality_desc} "
                    f"(preset: {self.quality_preset})")
                if self.eq_config.any_enabled:
                    effects = ', '.join(self.eq_config.enabled_effects)
                    self.logger.debug(f"EQ effects:   {effects}")
                    self.logger.debug(
                        f"Filter chain: {self.eq_config.build_filter_chain()}")
                self.logger.debug("Source tags:")
                self.logger.debug(f"  → Title:  '{title}'")
                self.logger.debug(f"  → Artist: '{artist}'")
                self.logger.debug(f"  → Album:  '{album}'")

            if dry_run:
                if existing_track and force:
                    self.logger.dry_run(
                        f"Would re-convert: {human_label}")
                else:
                    self.logger.dry_run(
                        f"Would convert:   '{display_name}'")
                self.logger.dry_run(f"  → Output:     {output_filename}")
                self.logger.dry_run(f"  → Title:      '{title}'")
                self.logger.dry_run(f"  → Artist:     '{artist}'")
                self.logger.dry_run(f"  → Album:      '{album}'")
                cover_data, _ = read_m4a_cover_art(input_file)
                if cover_data:
                    self.logger.dry_run(
                        f"  → Cover art:  "
                        f"{len(cover_data) / 1024:.1f} KB (extract to disk)")
                else:
                    self.logger.dry_run(
                        "  → Cover art:  (none found in source)")
                if self.eq_config.any_enabled:
                    effects = ', '.join(self.eq_config.enabled_effects)
                    self.logger.dry_run(f"  → EQ effects: {effects}")
                return

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # FFmpeg conversion M4A → MP3
            import ffmpeg as _ffmpeg
            try:
                ffmpeg_params = {'acodec': 'libmp3lame'}
                if self.quality_settings['mode'] == 'vbr':
                    ffmpeg_params['q:a'] = self.quality_settings['value']
                else:
                    ffmpeg_params['b:a'] = (
                        self.quality_settings['value'] + 'k')

                filter_chain = self.eq_config.build_filter_chain()
                if filter_chain:
                    ffmpeg_params['af'] = filter_chain

                (
                    _ffmpeg
                    .input(str(input_file))
                    .output(str(output_file), **ffmpeg_params)
                    .run(overwrite_output=True, quiet=True)
                )
            except _ffmpeg.Error as e:
                error_msg = (e.stderr.decode('utf-8')
                             if e.stderr else str(e))
                raise Exception(
                    f"FFmpeg conversion failed: {error_msg}") from e

            # Write ONLY the TrackUUID identifier tag (no TIT2/TPE1/TALB/APIC)
            try:
                id3_tags = ID3(str(output_file))
            except ID3NoHeaderError:
                id3_tags = ID3()

            # Remove any tags ffmpeg may have copied from the M4A
            id3_tags.delete(str(output_file))
            id3_tags = ID3()
            id3_tags.add(TXXX(encoding=3, desc=TXXX_TRACK_UUID,
                          text=[track_uuid]))
            id3_tags.save(str(output_file), v2_version=4, v1=0)

            # Extract cover art to flat artwork directory
            artwork_dir = Path(get_artwork_dir())
            cover_art_path, cover_art_hash = self._extract_cover_art_to_disk(
                input_file, artwork_dir, track_uuid)

            if verbose and cover_art_path:
                self.logger.debug(
                    f"  → Cover art: extracted to {cover_art_path}")

            # Get MP3 duration and file size
            mp3_info = MP3(str(output_file))
            duration_s = mp3_info.info.length if mp3_info.info else None
            file_size_bytes = output_file.stat().st_size

            # Insert metadata into TrackDB
            if self.track_db:
                self.track_db.insert_track(
                    uuid=track_uuid,
                    playlist=playlist_key,
                    file_path=f"{get_audio_dir()}/{output_filename}",
                    title=title,
                    artist=artist,
                    album=album,
                    cover_art_path=cover_art_path,
                    cover_art_hash=cover_art_hash,
                    duration_s=duration_s,
                    file_size_bytes=file_size_bytes,
                    source_m4a_path=rel_source,
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

            if verbose:
                self.logger.debug(f"  → UUID:     {track_uuid}")
                self.logger.debug(
                    f"Output size: {file_size_bytes / 1024:.1f} KB")

            if existing_track and force:
                self.stats.increment('overwritten')
                msg = (f"[{count}/{self.stats.total_found}] "
                       f"Converted: {human_label} → {output_filename}")
            else:
                self.stats.increment('converted')
                msg = (f"[{count}/{self.stats.total_found}] "
                       f"Converted: {human_label} → {output_filename}")
            if progress_bar and not verbose:
                self.logger.file_info(msg)
            else:
                self.logger.info(msg)
            if progress_bar:
                progress_bar.update(1)

        except Exception as e:
            self.logger.error(f"Failed to convert '{display_name}': {e}")
            self.stats.increment('errors')
            if progress_bar:
                progress_bar.update(1)

    def convert(self, input_dir, output_dir, playlist_key=None,
                force=False, dry_run=False, verbose=False):
        """Convert M4A files to clean library MP3s.

        Recursively scans input_dir for .m4a files, converts to MP3 with
        ffmpeg, and saves flat into output_dir.  Each MP3 gets only a
        TXXX:TrackUUID tag; metadata is stored in TrackDB.

        Args:
            playlist_key: Playlist identifier for TrackDB records.
                         Defaults to output directory name.
        """
        start_time = time.time()

        input_path = Path(input_dir)
        output_path = Path(output_dir)

        if playlist_key is None:
            playlist_key = output_path.name

        if input_path.resolve() == output_path.resolve():
            self.logger.error(
                "Input and output directories cannot be the same")
            return ConversionResult(
                success=False, input_dir=str(input_dir),
                output_dir=str(output_dir),
                duration=0, quality_preset=self.quality_preset,
                quality_mode=self.quality_settings['mode'],
                quality_value=self.quality_settings['value'],
                workers=self.workers, total_found=0, converted=0,
                overwritten=0, skipped=0, errors=1)

        # Find all M4A files recursively
        m4a_files = [
            f for f in input_path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]

        if not m4a_files:
            self.logger.info(f"No .m4a files found in '{input_dir}'")
            return ConversionResult(
                success=True, input_dir=str(input_dir),
                output_dir=str(output_dir),
                duration=0, quality_preset=self.quality_preset,
                quality_mode=self.quality_settings['mode'],
                quality_value=self.quality_settings['value'],
                workers=self.workers, total_found=0, converted=0,
                overwritten=0, skipped=0, errors=0)

        self.stats.total_found = len(m4a_files)
        self.logger.info(
            f"Found {self.stats.total_found} .m4a file(s) (recursive)")
        self.logger.info(f"Output directory: '{output_dir}' (flat)")

        if force:
            self.logger.info(
                "Force mode enabled — existing files will be overwritten")

        if self.eq_config.any_enabled:
            effects = ', '.join(self.eq_config.enabled_effects)
            self.logger.info(f"EQ effects: {effects}")

        if not dry_run:
            output_path.mkdir(parents=True, exist_ok=True)

        effective_workers = min(self.workers, self.stats.total_found)

        progress = _DisplayProgress(
            self.display_handler, total=self.stats.total_found,
            desc="Converting",
        )

        try:
            if effective_workers > 1:
                self.logger.info(
                    f"Using {effective_workers} parallel workers")

                with ThreadPoolExecutor(
                        max_workers=effective_workers) as executor:
                    futures = {}
                    for input_file in m4a_files:
                        if _is_cancelled(self.cancel_event):
                            break
                        futures[executor.submit(
                            self._convert_single_file,
                            input_file, input_path, output_path,
                            playlist_key, force, dry_run, verbose,
                            progress
                        )] = input_file

                    for future in as_completed(futures):
                        if _is_cancelled(self.cancel_event):
                            for f in futures:
                                f.cancel()
                            self.logger.warn(
                                "Conversion cancelled by user")
                            break
                        try:
                            future.result()
                        except Exception as e:
                            input_file = futures[future]
                            self.logger.error(
                                f"Unexpected error processing "
                                f"'{input_file.name}': {e}")
                            self.stats.increment('errors')
            else:
                for input_file in m4a_files:
                    if _is_cancelled(self.cancel_event):
                        self.logger.warn(
                            "Conversion cancelled by user")
                        break
                    self._convert_single_file(
                        input_file, input_path, output_path,
                        playlist_key, force, dry_run, verbose,
                        progress
                    )
        finally:
            progress.close()

        duration = time.time() - start_time

        mp3_count = len([
            f for f in output_path.rglob("*.mp3")
            if not f.name.startswith('._')
        ])
        self.stats.mp3_total = mp3_count

        if self.audit_logger:
            self.audit_logger.log(
                'convert', f"Convert: {input_dir}",
                'completed' if self.stats.errors == 0 else 'failed',
                params={
                    'input_dir': str(input_dir),
                    'output_dir': str(output_dir),
                    'playlist_key': playlist_key,
                    'preset': self.quality_preset,
                    'converted': self.stats.converted,
                    'errors': self.stats.errors,
                    'eq_effects': self.eq_config.enabled_effects,
                },
                duration_s=duration, source=self._audit_source)

        return ConversionResult(
            success=self.stats.errors == 0,
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            duration=duration,
            quality_preset=self.quality_preset,
            quality_mode=self.quality_settings['mode'],
            quality_value=self.quality_settings['value'],
            workers=self.workers,
            total_found=self.stats.total_found,
            converted=self.stats.converted,
            overwritten=self.stats.overwritten,
            skipped=self.stats.skipped,
            errors=self.stats.errors,
            mp3_total=mp3_count,
            eq_effects=self.eq_config.enabled_effects,
        )

    def reconvert_track(self, uuid, project_root='.'):
        """Re-convert a single track from its source M4A.

        For locked tracks: reconverts audio only (skips metadata write).
        For unlocked tracks: full reconvert (deletes old MP3 + DB record, re-inserts).

        Returns a dict with 'success' (bool) and 'error' (str, only on failure).
        """
        if not self.track_db:
            return {'success': False, 'error': 'No TrackDB configured'}

        track = self.track_db.get_track(uuid)
        if not track:
            return {'success': False, 'error': f'Track {uuid} not found'}
        if track.get('hidden'):
            return {'success': False, 'error': 'Cannot reconvert a hidden track'}

        playlist_key = track['playlist']
        source_m4a_rel = track.get('source_m4a_path')
        if not source_m4a_rel:
            return {'success': False, 'error': 'No source M4A path recorded for this track'}

        # Build absolute path to the source M4A
        project_root = Path(project_root)
        abs_m4a = project_root / source_m4a_rel
        if not abs_m4a.exists():
            return {
                'success': False,
                'error': f'Source M4A not found on disk: {source_m4a_rel}',
            }

        import ffmpeg as _ffmpeg
        from mutagen.id3 import ID3, TXXX  # type: ignore[attr-defined]

        if track.get('locked'):
            # Locked: reconvert audio only — overwrite the existing MP3 file
            mp3_path = track['file_path']
            abs_mp3 = Path(mp3_path) if Path(mp3_path).is_absolute() else project_root / mp3_path
            abs_mp3.parent.mkdir(parents=True, exist_ok=True)
            try:
                ffmpeg_params = {'acodec': 'libmp3lame'}
                if self.quality_settings['mode'] == 'vbr':
                    ffmpeg_params['q:a'] = self.quality_settings['value']
                else:
                    ffmpeg_params['b:a'] = self.quality_settings['value'] + 'k'
                filter_chain = self.eq_config.build_filter_chain()
                if filter_chain:
                    ffmpeg_params['af'] = filter_chain
                (
                    _ffmpeg
                    .input(str(abs_m4a))
                    .output(str(abs_mp3), **ffmpeg_params)
                    .run(overwrite_output=True, quiet=True)
                )
                # Re-stamp only the TXXX:TrackUUID tag (strip anything ffmpeg copied)
                id3_tags = ID3()
                id3_tags.add(TXXX(encoding=3, desc=TXXX_TRACK_UUID, text=[uuid]))
                id3_tags.save(str(abs_mp3), v2_version=4, v1=0)
                self.logger.info(
                    f"Reconverted (audio-only, locked): {track.get('title', uuid)}")
            except _ffmpeg.Error as e:
                error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
                return {'success': False, 'error': f'FFmpeg error: {error_msg}'}
        else:
            # Unlocked: full reconvert via _convert_single_file with force=True
            input_path = abs_m4a.parent
            output_path = project_root / get_audio_dir()
            self._convert_single_file(
                abs_m4a, input_path, output_path, playlist_key,
                force=True, dry_run=False, verbose=False)

        return {'success': True}


