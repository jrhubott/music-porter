"""
core.sync - SyncManager, USBSyncStatistics, and removed-track helpers.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from core.config import NonInteractivePromptHandler, NullDisplayHandler
from core.constants import (
    CURRENT_OS,
    DEFAULT_USB_DIR,
    EXCLUDED_USB_VOLUMES,
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
)
from core.logging import Logger
from core.models import SyncDestination, SyncResult, _DisplayProgress
from core.utils import (
    _format_bytes,
    _is_cancelled,
    deduplicate_filenames,
    get_audio_dir,
)

# ══════════════════════════════════════════════════════════════════
# Section 8: Sync Module (formerly USB Sync)
# ══════════════════════════════════════════════════════════════════

class USBSyncStatistics:
    """Tracks sync operation statistics."""

    def __init__(self):
        self.files_found = 0         # Total files to copy
        self.files_copied = 0        # Successfully copied
        self.files_skipped = 0       # Files skipped (unchanged)
        self.files_failed = 0        # Copy failures


class SyncManager:
    """Manages sync destination selection, USB drive detection, and file copying."""

    def __init__(self, logger=None, excluded_volumes=None, prompt_handler=None,
                 display_handler=None, cancel_event=None, sync_tracker=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.excluded_volumes = excluded_volumes or EXCLUDED_USB_VOLUMES
        self.sync_tracker = sync_tracker

    def find_usb_drives(self):
        """
        Find available USB drives on current platform.
        Returns list of volume names/mount points.
        """
        if IS_MACOS:
            return self._find_usb_drives_macos()
        elif IS_LINUX:
            return self._find_usb_drives_linux()
        elif IS_WINDOWS:
            return self._find_usb_drives_windows()
        else:
            self.logger.error(f"Unsupported operating system: {CURRENT_OS}")
            return []

    def _find_usb_drives_macos(self):
        """Find USB drives on macOS using /Volumes/."""
        volumes_path = Path('/Volumes')

        if not volumes_path.exists():
            self.logger.error("/Volumes directory not found")
            return []

        # Get all volumes, excluding system volumes
        volumes = [
            v.name for v in volumes_path.iterdir()
            if v.is_dir() and v.name not in self.excluded_volumes
        ]

        return volumes

    def _find_usb_drives_linux(self):
        """Find USB drives on Linux using /media/ and /mnt/."""
        drives = []

        # Check /media/$USER/ (common for desktop environments)
        if 'USER' in os.environ:
            media_user_path = Path(f"/media/{os.environ['USER']}")
            if media_user_path.exists():
                drives.extend([
                    d.name for d in media_user_path.iterdir()
                    if d.is_dir() and d.name not in self.excluded_volumes
                ])

        # Check /mnt/ (common for manual mounts)
        mnt_path = Path('/mnt')
        if mnt_path.exists():
            drives.extend([
                d.name for d in mnt_path.iterdir()
                if d.is_dir() and d.name not in self.excluded_volumes
            ])

        if not drives:
            self.logger.warn("No USB drives found in /media/ or /mnt/")

        return list(set(drives))  # Remove duplicates

    def _find_usb_drives_windows(self):
        """Find USB drives on Windows using drive letters."""
        import string

        drives = []
        # Check all drive letters
        for letter in string.ascii_uppercase:
            drive = f"{letter}:"
            drive_path = Path(drive + "\\")

            # Check if drive exists and is not in excluded list
            if drive_path.exists() and drive not in self.excluded_volumes:
                drives.append(drive)

        if not drives:
            self.logger.warn("No removable drives found")

        return drives

    def _get_usb_base_path(self, volume):
        """Get the full path to a USB volume based on OS."""
        if IS_MACOS:
            return Path('/Volumes') / volume
        elif IS_LINUX:
            # Try /media/$USER/ first, then /mnt/
            if 'USER' in os.environ:
                media_path = Path(f"/media/{os.environ['USER']}") / volume
                if media_path.exists():
                    return media_path
            return Path('/mnt') / volume
        elif IS_WINDOWS:
            # volume is already the drive letter (e.g., "D:")
            return Path(volume + "\\")
        else:
            return Path(volume)

    def select_usb_drive(self):
        """
        Interactively select a USB drive if multiple are available.
        Returns selected volume name or None.
        """
        volumes = self.find_usb_drives()

        if not volumes:
            self.logger.error("No external drives found")
            self.logger.error("Make sure your USB drive is connected and mounted")
            return None

        if len(volumes) == 1:
            self.logger.info(f"Using USB drive: {volumes[0]}")
            return volumes[0]

        # Multiple drives found - prompt user
        selection = self.prompt_handler.select_from_list(
            "Select USB drive", volumes, allow_cancel=True)

        if selection is not None:
            return volumes[selection]
        return None

    def _should_copy_file(self, src_path, dst_path):
        """
        Determine if file needs copying (incremental logic).
        Returns True if file should be copied, False if up-to-date.

        Args:
            src_path: Path object for source file
            dst_path: Path object for destination file

        Returns:
            bool: True if file should be copied
        """
        # If destination doesn't exist, must copy
        if not dst_path.exists():
            return True

        # Compare file size
        src_size = src_path.stat().st_size
        dst_size = dst_path.stat().st_size
        if src_size != dst_size:
            return True

        # Compare modification time (source newer than dest)
        # Use 2-second tolerance for FAT32/exFAT timestamp precision
        src_mtime = src_path.stat().st_mtime
        dst_mtime = dst_path.stat().st_mtime
        if src_mtime > dst_mtime + 2:
            return True

        # File is up-to-date, skip
        return False

    def select_destination(self, output_profile=None):
        """Interactive destination picker showing USB drives, saved destinations, and custom path.

        Returns SyncDestination or None if cancelled.
        """
        options = []
        option_dests = []  # Parallel list: SyncDestination or None (for custom)

        # 1. Auto-detected USB drives
        usb_drives = self.find_usb_drives()
        usb_dir = output_profile.usb_dir if output_profile else DEFAULT_USB_DIR
        saved = self.sync_tracker.get_all_destinations() if self.sync_tracker else []
        saved_names = {d.name.lower() for d in saved}
        for vol in usb_drives:
            base = self._get_usb_base_path(vol)
            full_path = str(base / usb_dir) if usb_dir else str(base)
            # Skip if already saved as a destination
            if vol.lower() in saved_names:
                continue
            options.append(f"[USB] {vol} ({full_path})")
            option_dests.append(
                SyncDestination(vol, f'usb://{full_path}'))

        # 2. Saved destinations from DB
        for dest in saved:
            status = "" if dest.available else " [not found]"
            badge = "[USB]" if dest.is_usb else "[Folder]"
            options.append(f"{badge} {dest.name} ({dest.raw_path}){status}")
            option_dests.append(dest)

        # 3. Custom path option
        options.append("Enter custom path...")
        option_dests.append(None)

        if len(options) == 1:
            self.logger.info("No USB drives or saved destinations found")

        selection = self.prompt_handler.select_from_list(
            "Select sync destination", options, allow_cancel=True)

        if selection is None:
            return None

        dest = option_dests[selection]

        # Handle custom path option
        if dest is None:
            try:
                custom_path = input("  Enter destination path: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return None
            if not custom_path:
                self.logger.error("No path provided")
                return None
            p = Path(custom_path)
            if not p.exists() or not p.is_dir():
                self.logger.error(f"Path does not exist or is not a directory: {custom_path}")
                return None
            dest_name = self._sanitize_dest_name(p.name)
            if self.sync_tracker:
                self.sync_tracker.add_destination(
                    dest_name, f'folder://{custom_path}',
                    validate_path=False)
                dest = self.sync_tracker.get_destination(dest_name)
                if dest:
                    return dest
            # Fallback if no tracker
            dest = SyncDestination(dest_name, f'folder://{custom_path}')
            return dest

        # Auto-save USB selections and get back with proper sync_key
        if dest.is_usb and self.sync_tracker:
            self.sync_tracker.add_destination(
                dest.name, dest.path, validate_path=False)
            saved_dest = self.sync_tracker.get_destination(dest.name)
            if saved_dest:
                return saved_dest

        return dest

    @staticmethod
    def _sanitize_dest_name(name):
        """Sanitize a directory name into a valid destination name (alphanumeric, hyphens, underscores)."""
        import re as _re
        sanitized = _re.sub(r'[^a-zA-Z0-9_-]', '-', name)
        sanitized = _re.sub(r'-+', '-', sanitized).strip('-')
        return sanitized or 'custom-dest'

    def sync_to_destination(self, source_dir, dest_path, sync_key,
                            dry_run=False, tag_applicator=None,
                            profile=None, playlist_name=None,
                            playlist_keys=None, clean_destination=False):
        """Sync files to any destination with incremental copy logic.

        Args:
            source_dir: Source directory containing MP3 files
            dest_path: Schemed path (usb:// or folder://) or raw filesystem path
            sync_key: Internal sync key UUID for tracking
            dry_run: Preview changes without copying
            tag_applicator: Optional TagApplicator for profile-based tagging
            profile: Optional OutputProfile (required if tag_applicator is set)
            playlist_name: Display name of playlist (for template variables)
            playlist_keys: Optional list of playlist keys to restrict sync to.
                None or empty list means sync all playlists.

        When tag_applicator and profile are provided, files are tagged on-the-fly
        during copy using the profile's template settings.  When omitted, files
        are copied as-is (raw library MP3s).

        Returns:
            SyncResult with operation stats.
        """
        start_time = time.time()
        stats = USBSyncStatistics()
        source_path = Path(source_dir)

        # Derive is_usb and filesystem path from scheme
        is_usb = dest_path.startswith('usb://')
        if dest_path.startswith('usb://'):
            fs_path = dest_path[6:]
        elif dest_path.startswith('folder://'):
            fs_path = dest_path[9:]
        else:
            fs_path = dest_path

        if not source_path.exists():
            self.logger.error(
                f"Source directory does not exist: {source_path}")
            return SyncResult(success=False, source=str(source_dir),
                              destination='',
                              duration=0, is_usb=is_usb)

        # Normalise playlist filter: None/[] → no filter (all playlists)
        playlist_filter: set | None = (
            set(playlist_keys) if playlist_keys else None)

        # Collect all .mp3 files to process
        mp3_files = []
        if source_path.is_file():
            if source_path.suffix == '.mp3':
                mp3_files.append(source_path)
        else:
            for root, _dirs, files in os.walk(source_path):
                for file in files:
                    if file.endswith('.mp3'):
                        mp3_files.append(Path(root) / file)

        # Filter by playlist if requested (requires TrackDB via tag_applicator)
        if playlist_filter is not None:
            if tag_applicator and tag_applicator.track_db:
                track_db = tag_applicator.track_db
                filtered = []
                for f in mp3_files:
                    db_path = f"{get_audio_dir()}/{f.name}"
                    meta = track_db.get_track_by_path(db_path)
                    if meta and meta.get('playlist') in playlist_filter:
                        filtered.append(f)
                mp3_files = filtered
            else:
                self.logger.warn(
                    "playlist_keys filter ignored: TrackDB not available")

        stats.files_found = len(mp3_files)
        self.logger.info(f"Files to process: {stats.files_found}")

        dest = Path(fs_path)
        self.logger.info(f"Syncing {source_path} to {dest}")

        # Helper to look up track metadata from tag_applicator's TrackDB
        def _get_track_meta(src_file):
            if not tag_applicator or not tag_applicator.track_db:
                return None
            # DB stores paths like library/audio/<uuid>.mp3
            db_path = f"{get_audio_dir()}/{src_file.name}"
            return tag_applicator.track_db.get_track_by_path(db_path)

        # Pre-compute destination paths for all files, then deduplicate
        track_metas = {}  # src_file -> track_meta (or None)
        raw_filenames = []
        raw_subdirs = []
        for src_file in mp3_files:
            meta = _get_track_meta(src_file)
            track_metas[src_file] = meta
            if tag_applicator and profile and meta:
                pname = playlist_name or meta.get('playlist', '')
                fname = tag_applicator.build_output_filename(
                    meta, profile, pname)
                subdir = tag_applicator.build_output_subdir(
                    meta, profile, pname)
            else:
                # Fallback: preserve relative path
                if source_path.is_dir():
                    rel = src_file.relative_to(source_path)
                    fname = rel.name
                    subdir = (str(rel.parent)
                              if len(rel.parts) > 1 else '')
                else:
                    fname = src_file.name
                    subdir = ''
            raw_filenames.append(fname)
            raw_subdirs.append(subdir or '')

        deduped_names = deduplicate_filenames(raw_filenames, raw_subdirs)

        # Build src_file -> deduped dest path map
        dest_path_map = {}
        for i, src_file in enumerate(mp3_files):
            subdir = raw_subdirs[i]
            if subdir:
                dest_path_map[src_file] = dest / subdir / deduped_names[i]
            else:
                dest_path_map[src_file] = dest / deduped_names[i]

        if dry_run:
            self.logger.dry_run(f"Would create directory: {dest}")
            for src_file in mp3_files:
                dst_file = dest_path_map[src_file]
                if self._should_copy_file(src_file, dst_file):
                    self.logger.dry_run(f"Would copy: {src_file.name}")
                    stats.files_copied += 1
                else:
                    if self.logger.verbose:
                        self.logger.dry_run(
                            f"Would skip (unchanged): {src_file.name}")
                    stats.files_skipped += 1
            if is_usb:
                self.logger.dry_run(
                    "Would prompt to eject USB drive after copy")
            duration = time.time() - start_time

            return SyncResult(
                success=True, source=str(source_path), destination=str(dest),
                duration=duration, is_usb=is_usb,
                files_found=stats.files_found, files_copied=stats.files_copied,
                files_skipped=stats.files_skipped,
                files_failed=stats.files_failed)

        # Create destination directory
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(
                f"Failed to create destination directory: {e}")
            stats.files_failed = stats.files_found
            duration = time.time() - start_time

            return SyncResult(
                success=False, source=str(source_path),
                destination=str(dest),
                duration=duration, is_usb=is_usb,
                files_found=stats.files_found, files_copied=stats.files_copied,
                files_skipped=stats.files_skipped,
                files_failed=stats.files_failed)

        # Copy files with incremental check
        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files),
            desc="Syncing files",
        )
        expected_dest_paths: set[Path] = set()

        try:
            for src_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Sync cancelled by user")
                    break
                try:
                    track_meta = track_metas[src_file]
                    dst_file = dest_path_map[src_file]
                    expected_dest_paths.add(dst_file)

                    dst_file.parent.mkdir(parents=True, exist_ok=True)

                    if self._should_copy_file(src_file, dst_file):
                        if (tag_applicator and profile
                                and track_meta):
                            # Apply profile tags on-the-fly during copy
                            pname = (playlist_name
                                     or track_meta.get('playlist', ''))
                            tag_applicator.apply_tags_to_file(
                                str(src_file), track_meta, profile,
                                pname, str(dst_file))
                        else:
                            # Raw copy (no profile tagging)
                            shutil.copy2(src_file, dst_file)
                        stats.files_copied += 1
                        if self.logger.verbose:
                            self.logger.info(f"Copied: {src_file.name}")
                        else:
                            self.logger.file_info(
                                f"Copied: {src_file.name}")
                        if self.sync_tracker and not dry_run:
                            record_name = dst_file.name
                            pl_name = (playlist_name
                                       or source_path.parent.name)
                            self.sync_tracker.record_file(
                                sync_key, pl_name, record_name,
                                track_uuid=track_meta.get('uuid') if track_meta else None)
                    else:
                        stats.files_skipped += 1
                        if self.logger.verbose:
                            self.logger.info(
                                f"Skipped (unchanged): {src_file.name}")
                        else:
                            self.logger.file_info(
                                f"Skipped (unchanged): {src_file.name}")

                except Exception as e:
                    stats.files_failed += 1
                    self.logger.error(
                        f"Failed to copy {src_file.name}: {e}")

                progress.update(1)
        finally:
            progress.close()

        self.logger.ok("Sync complete")

        # ── Scan-based destination cleanup (mirror mode) ──────────────
        orphaned_cleaned = 0
        orphaned_bytes_freed = 0
        if clean_destination and not dry_run and Path(dest).exists():
            for existing in Path(dest).rglob("*.mp3"):
                if existing not in expected_dest_paths:
                    try:
                        orphaned_bytes_freed += existing.stat().st_size
                        existing.unlink()
                        orphaned_cleaned += 1
                        self.logger.info(f"  Removed orphan: {existing.name}")
                    except OSError as exc:
                        self.logger.warn(
                            f"  Could not remove orphan {existing.name}: {exc}")
            # Remove empty subdirectories left behind
            for d in sorted(Path(dest).rglob("*"), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    try:
                        d.rmdir()
                    except OSError:
                        pass
            if orphaned_cleaned > 0:
                self.logger.ok(
                    f"Destination cleanup: {orphaned_cleaned} file(s) removed, "
                    f"{_format_bytes(orphaned_bytes_freed)} freed")
        # Clean up stale sync_files DB records regardless of scan cleanup
        if self.sync_tracker and not dry_run:
            self.sync_tracker.delete_orphaned_records(sync_key)

        duration = time.time() - start_time

        # Prompt to eject USB drive (only for USB destinations)
        if is_usb and not dry_run:
            # Extract volume name from path for eject
            volume_name = Path(fs_path).parts[2] if IS_MACOS and len(Path(fs_path).parts) > 2 else Path(fs_path).name
            self._prompt_and_eject_usb(volume_name)

        return SyncResult(
            success=stats.files_failed == 0, source=str(source_path),
            destination=str(dest), duration=duration,
            is_usb=is_usb, files_found=stats.files_found,
            files_copied=stats.files_copied,
            files_skipped=stats.files_skipped,
            files_failed=stats.files_failed,
            orphaned_detected=orphaned_cleaned,
            orphaned_cleaned=orphaned_cleaned,
            orphaned_bytes_freed=orphaned_bytes_freed)

    def sync_to_usb(self, source_dir, usb_dir=DEFAULT_USB_DIR, dry_run=False, volume=None):
        """Backwards-compatible wrapper: sync files to a USB drive."""
        if volume is None:
            volume = self.select_usb_drive()
        if not volume:
            return SyncResult(success=False, source=str(source_dir),
                              destination='', duration=0, is_usb=True)

        base_path = str(self._get_usb_base_path(volume))
        full_path = str(Path(base_path) / usb_dir) if usb_dir else base_path
        # Resolve destination to get internal sync_key
        sync_key = volume  # fallback
        if self.sync_tracker:
            result = self.sync_tracker.resolve_destination(
                path=f'usb://{full_path}', drive_name=volume)
            if result:
                sync_key = result['destination'].sync_key
        return self.sync_to_destination(
            source_dir, dest_path=f'usb://{full_path}', sync_key=sync_key,
            dry_run=dry_run)

    def _prompt_and_eject_usb(self, volume_name):
        """
        Prompt user to eject USB drive and execute eject if confirmed.

        Args:
            volume_name: Name of the volume to eject (e.g., "MY_USB")

        Returns:
            bool: True if eject succeeded or was skipped, False if failed
        """
        if not self.prompt_handler.confirm(f"Eject USB drive '{volume_name}'?", default=False):
            self.logger.info("Skipping USB eject")
            return True

        try:
            self.logger.info(f"Ejecting USB drive: {volume_name}")

            if IS_MACOS:
                return self._eject_macos(volume_name)
            elif IS_LINUX:
                return self._eject_linux(volume_name)
            elif IS_WINDOWS:
                return self._eject_windows(volume_name)
            else:
                self.logger.warn(f"USB eject not supported on {CURRENT_OS}")
                return True

        except KeyboardInterrupt:
            self.logger.info("Eject cancelled by user")
            return True

    def _eject_macos(self, volume_name):
        """Eject USB on macOS using diskutil."""
        volume_path = f"/Volumes/{volume_name}"
        cmd = ["diskutil", "eject", volume_path]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.logger.ok(f"USB drive '{volume_name}' ejected successfully")
            return True
        except FileNotFoundError:
            self.logger.error("diskutil command not found")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to eject USB: {e.stderr.strip() if e.stderr else str(e)}")
            self.logger.error("You may need to eject manually from Finder")
            return False

    def _eject_linux(self, volume_name):
        """Eject USB on Linux using udisksctl or umount."""
        # Try udisksctl first (modern systems)
        mount_paths = []
        if 'USER' in os.environ:
            mount_paths.append(f"/media/{os.environ['USER']}/{volume_name}")
        mount_paths.append(f"/mnt/{volume_name}")

        for mount_path in mount_paths:
            if Path(mount_path).exists():
                # Try udisksctl first
                try:
                    cmd = ["udisksctl", "unmount", "-b", mount_path]
                    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
                    self.logger.ok(f"USB drive '{volume_name}' unmounted successfully")
                    return True
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pass

                # Fallback to umount
                try:
                    cmd = ["umount", mount_path]
                    subprocess.run(cmd, check=True)
                    self.logger.ok(f"USB drive '{volume_name}' unmounted successfully")
                    return True
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pass

        self.logger.warn("Could not eject USB - please unmount manually")
        return True

    def _eject_windows(self, volume_name):
        """Eject USB on Windows (manual instruction)."""
        self.logger.info(f"Please safely eject drive '{volume_name}' using Windows Explorer")
        self.logger.info("(Automatic eject not implemented on Windows)")
        return True


# Backwards compatibility alias
USBManager = SyncManager


def detect_removed_tracks(playlist_key, playlist_track_names,
                          track_db, logger=None):
    """Identify tracks in the library that are no longer in the Apple Music
    playlist.

    Compares the list of track names gamdl processed during this download
    run (the complete current playlist) against what is recorded in TrackDB.
    Tracks in TrackDB that do not appear in the current playlist are returned
    as removed.

    Args:
        playlist_key: Playlist identifier used in TrackDB queries.
        playlist_track_names: List of track names from gamdl "Downloading"
            messages — one entry per current playlist track.
        track_db: TrackDB instance for library queries.
        logger: Optional logger for informational messages.

    Returns:
        List of track dicts (from TrackDB) that were removed, or empty list
        if detection is not possible or encounters an error (SRS 23.6.1).
    """
    if not playlist_track_names or track_db is None:
        if logger:
            logger.info(
                "Removed track detection skipped: insufficient data "
                "(no track names captured from gamdl output)")
        return []

    try:
        db_tracks = track_db.get_tracks_by_playlist(playlist_key)
        if not db_tracks:
            return []

        # Build a Counter of current playlist titles for duplicate handling
        current_counts = Counter(playlist_track_names)
        # Build a Counter of library titles
        db_counts = Counter(t['title'] for t in db_tracks)

        # Titles with more library entries than current playlist entries are
        # candidates for removal
        removed_titles = {}
        for title, db_count in db_counts.items():
            current_count = current_counts.get(title, 0)
            if db_count > current_count:
                removed_titles[title] = db_count - current_count

        if not removed_titles:
            return []

        # Collect specific removed track records; when multiple tracks share
        # a title, prefer the oldest (by created_at) as the removed ones
        removed = []
        for title, excess_count in removed_titles.items():
            matching = sorted(
                [t for t in db_tracks if t['title'] == title],
                key=lambda t: t.get('created_at', 0),
            )
            removed.extend(matching[:excess_count])

        return removed

    except Exception as exc:
        if logger:
            logger.info(
                f"Removed track detection skipped due to error: {exc}")
        return []


def cleanup_removed_tracks(removed_tracks, track_db, sync_tracker,
                           logger, project_root,
                           audit_logger=None, audit_source='cli'):
    """Cascade-delete removed tracks from the library.

    For each removed track, deletes the source M4A, library MP3, artwork file,
    TrackDB record, and SyncTracker records.

    Args:
        removed_tracks: List of track dicts from detect_removed_tracks().
        track_db: TrackDB instance.
        sync_tracker: SyncTracker instance (may be None).
        logger: Logger instance.
        project_root: Path to the project root for resolving file paths.

    Returns:
        Dict with ``tracks_cleaned`` and ``bytes_freed`` counts.
    """
    tracks_cleaned = 0
    bytes_freed = 0

    if not removed_tracks:
        return {'tracks_cleaned': 0, 'bytes_freed': 0}

    root = Path(project_root)

    for track in removed_tracks:
        uuid = track.get('uuid', '')
        title = track.get('title', '')
        artist = track.get('artist', '')

        # Skip locked tracks — they are protected from deletion even when
        # the source playlist no longer contains them.
        if track.get('locked'):
            logger.warn(
                f"Skipping removal of locked track: {title} — {artist} "
                f"(unlock to allow deletion)")
            continue

        # 1. Delete source M4A
        src_m4a = track.get('source_m4a_path')
        if src_m4a:
            src_path = root / src_m4a
            try:
                if src_path.exists():
                    bytes_freed += src_path.stat().st_size
                    src_path.unlink()
            except OSError as exc:
                logger.warn(f"Could not delete source M4A for '{title}': {exc}")

        # 3. Delete library MP3
        mp3_path_rel = track.get('file_path')
        if mp3_path_rel:
            mp3_path = root / mp3_path_rel
            try:
                if mp3_path.exists():
                    bytes_freed += mp3_path.stat().st_size
                    mp3_path.unlink()
            except OSError as exc:
                logger.warn(f"Could not delete MP3 for '{title}': {exc}")

        # 4. Delete artwork
        art_path_rel = track.get('cover_art_path')
        if art_path_rel:
            art_path = root / art_path_rel
            try:
                if art_path.exists():
                    bytes_freed += art_path.stat().st_size
                    art_path.unlink()
            except OSError as exc:
                logger.warn(f"Could not delete artwork for '{title}': {exc}")

        # 5. Delete TrackDB record
        try:
            track_db.delete_track(uuid)
        except Exception as exc:
            logger.warn(f"Could not delete TrackDB record for '{title}': {exc}")

        # 6. Delete SyncTracker records by track_uuid
        if sync_tracker and uuid:
            try:
                sync_tracker.delete_sync_files_by_track_uuid(uuid)
            except Exception as exc:
                logger.warn(
                    f"Could not delete sync records for '{title}': {exc}")

        logger.info(f"Cleaned up removed track: {title} — {artist}")
        tracks_cleaned += 1

    logger.ok(
        f"Library cleanup: {tracks_cleaned} track(s) removed, "
        f"{_format_bytes(bytes_freed)} freed")
    if audit_logger and tracks_cleaned > 0:
        playlist_key = removed_tracks[0].get('playlist', '') if removed_tracks else ''
        audit_logger.log(
            'track_removal',
            f"Track removal: {tracks_cleaned} track(s) from {playlist_key}",
            'completed',
            params={
                'playlist_key': playlist_key,
                'tracks_cleaned': tracks_cleaned,
                'bytes_freed': bytes_freed,
            },
            source=audit_source,
        )
    return {'tracks_cleaned': tracks_cleaned, 'bytes_freed': bytes_freed}


