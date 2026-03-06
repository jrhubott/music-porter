"""
core.utils - Standalone utility functions with no heavy dependencies.

Includes file helpers, template expansion, ID3/M4A utilities, and pruning.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.constants import (
    APIC_MIME_JPEG,
    APIC_MIME_PNG,
    ARTWORK_SUBDIR,
    AUDIO_SUBDIR,
    DEFAULT_AUDIT_RETENTION_DAYS,
    DEFAULT_DB_FILE,
    DEFAULT_IMPORTER,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_RETENTION_DAYS,
    DEFAULT_TASK_HISTORY_RETENTION_DAYS,
    IS_WINDOWS,
    M4A_TAG_ALBUM,
    M4A_TAG_ALBUM_ARTIST,
    M4A_TAG_ARTIST,
    M4A_TAG_BPM,
    M4A_TAG_COMMENT,
    M4A_TAG_COMPILATION,
    M4A_TAG_COMPOSER,
    M4A_TAG_COPYRIGHT,
    M4A_TAG_COVER,
    M4A_TAG_DISC_NUMBER,
    M4A_TAG_GENRE,
    M4A_TAG_GROUPING,
    M4A_TAG_LYRICS,
    M4A_TAG_TITLE,
    M4A_TAG_TRACK_NUMBER,
    M4A_TAG_YEAR,
    SOURCE_SUBDIR,
)

DISPLAY_NAMES = {
    "full": "Artist - Title",
}


def display_name(value):
    """Convert a flag value to a human-readable display name."""
    if value in DISPLAY_NAMES:
        return DISPLAY_NAMES[value]
    return value.replace("-", " ").title()




def get_library_dir():
    """Return library root path: library/"""
    return DEFAULT_LIBRARY_DIR


def get_source_dir(playlist_key, importer=DEFAULT_IMPORTER):
    """Build source M4A path: library/source/<importer>/<playlist>/"""
    return f"{DEFAULT_LIBRARY_DIR}/{SOURCE_SUBDIR}/{importer}/{playlist_key}"


def get_audio_dir():
    """Build flat audio output path: library/audio/"""
    return f"{DEFAULT_LIBRARY_DIR}/{AUDIO_SUBDIR}"


def get_artwork_dir():
    """Build flat artwork path: library/artwork/"""
    return f"{DEFAULT_LIBRARY_DIR}/{ARTWORK_SUBDIR}"


class SafeTemplateDict(dict):
    """Dict subclass that returns '{key}' for missing keys in format_map().

    Allows templates to contain variables that may not be available without
    raising KeyError — unknown variables are left as literal placeholders.
    """

    def __missing__(self, key):
        return f"{{{key}}}"


def apply_template(template, **variables):
    """Apply template variables using str.format_map with safe fallback.

    Supported variables: title, artist, album, genre, track_number,
    track_total, disc_number, disc_total, year, composer, album_artist,
    bpm, comment, compilation, grouping, lyrics, copyright, playlist,
    playlist_key.
    Unknown variables are left as literal '{name}' in the output.
    """
    return template.format_map(SafeTemplateDict(variables))


# Third-party imports — deferred so the script can start without a venv
# and let DependencyChecker install missing packages first.
_tqdm: Any = None   # set by _init_third_party()

def _init_third_party():
    """Import third-party packages after DependencyChecker has ensured they exist."""
    global _tqdm
    if _tqdm is not None:
        return
    from tqdm import tqdm as _tqdm_cls
    _tqdm_cls.monitor_interval = 0  # Prevent TMonitor thread from interfering with input()
    _tqdm = _tqdm_cls
    # Update core.logging._tqdm so Logger/ProgressBar can use it
    import core.logging as _core_logging
    _core_logging._tqdm = _tqdm_cls


def prune_logs(log_dir=DEFAULT_LOG_DIR, retention_days=DEFAULT_LOG_RETENTION_DAYS,
               logger=None):
    """Delete log files older than retention_days. Returns count of deleted files."""
    log_path = Path(log_dir)
    if not log_path.is_dir():
        return 0
    cutoff = time.time() - (retention_days * 86400)
    count = 0
    for f in log_path.glob('*.log'):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            count += 1
    if count and logger:
        logger.info(f"Pruned {count} log file{'s' if count != 1 else ''}"
                    f" older than {retention_days} days")
    return count


def prune_audit_entries(db_path=DEFAULT_DB_FILE,
                        retention_days=DEFAULT_AUDIT_RETENTION_DAYS,
                        logger=None):
    """Delete audit entries older than retention_days. Returns count deleted."""
    if retention_days <= 0:
        return 0
    cutoff_epoch = time.time() - (retention_days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff_epoch, UTC).isoformat()
    count = 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "DELETE FROM audit_entries WHERE timestamp < ?", (cutoff_iso,))
            count = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        if logger:
            logger.warning(f"prune_audit_entries failed: {exc}")
        return 0
    if count and logger:
        logger.info(f"Pruned {count} audit entr{'ies' if count != 1 else 'y'}"
                    f" older than {retention_days} days")
    return count


def prune_task_history(db_path=DEFAULT_DB_FILE,
                       retention_days=DEFAULT_TASK_HISTORY_RETENTION_DAYS,
                       logger=None):
    """Delete task history entries older than retention_days. Returns count deleted."""
    if retention_days <= 0:
        return 0
    cutoff = time.time() - (retention_days * 86400)
    count = 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "DELETE FROM task_history WHERE started_at < ?", (cutoff,))
            count = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        if logger:
            logger.warning(f"prune_task_history failed: {exc}")
        return 0
    if count and logger:
        logger.info(f"Pruned {count} task history"
                    f" entr{'ies' if count != 1 else 'y'}"
                    f" older than {retention_days} days")
    return count




def _secure_path(path, logger=None):
    """Set owner-only permissions (0o700 for dirs, 0o600 for files).

    Protects sensitive files (config.yaml with API key, cookies.txt,
    database) from being read by other users on the system.
    Best-effort: logs a warning on failure (Docker bind mounts,
    read-only filesystems) but does not crash. Skipped on Windows.
    """
    if IS_WINDOWS:
        return
    try:
        p = Path(path)
        if p.is_dir():
            p.chmod(0o700)
        elif p.exists():
            p.chmod(0o600)
    except OSError as e:
        if logger:
            logger.warn(f"Could not set permissions on {path}: {e}")


def sanitize_filename(name):
    """Remove invalid filename characters."""
    invalid_chars = r'\/:*?"<>|'
    return "".join(c for c in name if c not in invalid_chars)


def deduplicate_filenames(filenames, scopes=None):
    """Deduplicate a list of filenames, appending (2), (3) for collisions.

    Args:
        filenames: List of filename strings.
        scopes: Optional list of scope keys (same length as filenames).
            Files in different scopes won't collide.

    Returns:
        List of deduplicated filenames (same length/order as input).
    """
    seen = {}
    result = []
    for i, filename in enumerate(filenames):
        scope = scopes[i] if scopes else ''
        full_key = (scope, filename)
        if full_key in seen:
            seen[full_key] += 1
            stem, ext = (filename.rsplit('.', 1)
                         if '.' in filename else (filename, ''))
            suffix = f" ({seen[full_key]})"
            result.append(
                f"{stem}{suffix}.{ext}" if ext else f"{stem}{suffix}")
        else:
            seen[full_key] = 1
            result.append(filename)
    return result


def read_m4a_tags(input_file):
    """Read metadata tags from an M4A file.

    Returns a dict with keys: title, artist, album, genre, track_number,
    track_total, disc_number, disc_total, year, composer, album_artist,
    bpm, comment, compilation, grouping, lyrics, copyright.
    """
    from mutagen.mp4 import MP4
    m4a = MP4(str(input_file))
    tags: Any = m4a.tags or {}

    # String tags with defaults
    title = str(tags.get(M4A_TAG_TITLE, ['Unknown Title'])[0])
    artist = str(tags.get(M4A_TAG_ARTIST, ['Unknown Artist'])[0])
    album = str(tags.get(M4A_TAG_ALBUM, ['Unknown Album'])[0])

    # String tags (empty string if missing)
    genre = str(tags.get(M4A_TAG_GENRE, [''])[0])
    year = str(tags.get(M4A_TAG_YEAR, [''])[0])
    composer = str(tags.get(M4A_TAG_COMPOSER, [''])[0])
    album_artist = str(tags.get(M4A_TAG_ALBUM_ARTIST, [''])[0])
    comment = str(tags.get(M4A_TAG_COMMENT, [''])[0])
    grouping = str(tags.get(M4A_TAG_GROUPING, [''])[0])
    lyrics = str(tags.get(M4A_TAG_LYRICS, [''])[0])
    copyright_text = str(tags.get(M4A_TAG_COPYRIGHT, [''])[0])

    # Tuple tags: (number, total) — None if 0
    trkn = tags.get(M4A_TAG_TRACK_NUMBER, [(0, 0)])[0]
    track_number = trkn[0] if trkn[0] else None
    track_total = trkn[1] if trkn[1] else None

    disk = tags.get(M4A_TAG_DISC_NUMBER, [(0, 0)])[0]
    disc_number = disk[0] if disk[0] else None
    disc_total = disk[1] if disk[1] else None

    # Integer tag
    bpm = tags.get(M4A_TAG_BPM, [None])[0]

    # Boolean tag (cpil is stored as a bare bool, not a list)
    compilation = bool(tags.get(M4A_TAG_COMPILATION, False))

    return {
        'title': title, 'artist': artist, 'album': album,
        'genre': genre, 'track_number': track_number,
        'track_total': track_total, 'disc_number': disc_number,
        'disc_total': disc_total, 'year': year, 'composer': composer,
        'album_artist': album_artist, 'bpm': bpm, 'comment': comment,
        'compilation': compilation, 'grouping': grouping,
        'lyrics': lyrics, 'copyright': copyright_text,
    }




def read_m4a_cover_art(input_file):
    """
    Read cover art data from an M4A file.
    Returns (cover_data: bytes, mime_type: str) or (None, None) if no art found.
    """
    from mutagen.mp4 import MP4, MP4Cover
    try:
        m4a = MP4(str(input_file))
        covers = (m4a.tags or {}).get(M4A_TAG_COVER)
        if not covers:
            return None, None
        cover = covers[0]
        # Detect format from MP4Cover imageformat attribute
        if hasattr(cover, 'imageformat'):
            if cover.imageformat == MP4Cover.FORMAT_PNG:
                return bytes(cover), APIC_MIME_PNG
        return bytes(cover), APIC_MIME_JPEG
    except Exception:
        return None, None


def resize_cover_art_bytes(image_data, max_size, mime_type="image/jpeg"):
    """
    Resize cover art image data to fit within max_size x max_size pixels.
    Returns (resized_bytes, mime_type). If already small enough, returns originals unchanged.
    Lazy-imports PIL to avoid startup cost.
    """
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_data))
    width, height = img.size

    if width <= max_size and height <= max_size:
        return image_data, mime_type

    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    if mime_type == APIC_MIME_PNG:
        img.save(buf, format="PNG")
    else:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=90)
        mime_type = APIC_MIME_JPEG

    return buf.getvalue(), mime_type








def _format_bytes(num_bytes):
    """Format byte count as human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


def _is_cancelled(event):
    """Check if a cancellation event has been signalled."""
    return event is not None and event.is_set()


