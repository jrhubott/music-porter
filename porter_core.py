"""
porter_core - Business logic for music-porter

Contains all business logic classes, protocols, result dataclasses,
and supporting utilities. CLI-specific code lives in music-porter.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

# ══════════════════════════════════════════════════════════════════
# Section 0: Platform Detection
# ══════════════════════════════════════════════════════════════════

# OS Detection - determine at module load time
CURRENT_OS = platform.system()  # Returns: 'Darwin' (macOS), 'Linux', 'Windows'
IS_MACOS = CURRENT_OS == 'Darwin'
IS_LINUX = CURRENT_OS == 'Linux'
IS_WINDOWS = CURRENT_OS == 'Windows'

def get_os_display_name():
    """Return user-friendly OS name."""
    os_names = {
        'Darwin': 'macOS',
        'Linux': 'Linux',
        'Windows': 'Windows'
    }
    return os_names.get(CURRENT_OS, CURRENT_OS)


# ══════════════════════════════════════════════════════════════════
# Section 1: Constants and Configuration
# ══════════════════════════════════════════════════════════════════

VERSION = "2.37.1"

DEFAULT_DATA_DIR = "data"
DEFAULT_LIBRARY_DIR = "library"
SOURCE_SUBDIR = "source"
AUDIO_SUBDIR = "audio"
ARTWORK_SUBDIR = "artwork"
DEFAULT_IMPORTER = "gamdl"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_RETENTION_DAYS = 7
DEFAULT_CONFIG_FILE = "data/config.yaml"
DEFAULT_COOKIES = "data/cookies.txt"
DEFAULT_DB_FILE = "data/music-porter.db"
DEFAULT_USB_DIR = "RZR/Music"

# TXXX frame name used to uniquely identify library MP3 files in the DB
TXXX_TRACK_UUID = "TrackUUID"

# Schema version constants — increment and add a migration case when changing
# the config.yaml structure or DB tables/columns.
CONFIG_SCHEMA_VERSION = 3
DB_SCHEMA_VERSION = 6

# Excluded USB volumes by OS
if IS_MACOS:
    EXCLUDED_USB_VOLUMES = (
        "Macintosh HD",
        "Macintosh HD - Data",
    )
elif IS_WINDOWS:
    EXCLUDED_USB_VOLUMES = (
        "C:",  # System drive
    )
else:  # Linux
    EXCLUDED_USB_VOLUMES = (
        "boot",
        "root",
    )

# Quality presets for MP3 conversion
QUALITY_PRESETS = {
    'lossless': {'mode': 'cbr', 'value': '320'},  # 320kbps CBR (default)
    'high': {'mode': 'vbr', 'value': '2'},        # ~190-250kbps VBR
    'medium': {'mode': 'vbr', 'value': '4'},      # ~165-210kbps VBR
    'low': {'mode': 'vbr', 'value': '6'},         # ~115-150kbps VBR
}
DEFAULT_QUALITY_PRESET = 'lossless'

# ── EQ Audio Effects ──────────────────────────────────────────────
# Available audio effects with their FFmpeg filter strings.
EQ_EFFECTS = {
    'loudnorm': {
        'description': 'Loudness normalization (EBU R128)',
        'filter': 'loudnorm=I=-14:TP=-1:LRA=11',
    },
    'bass_boost': {
        'description': 'Bass boost (+6dB below 100Hz)',
        'filter': 'bass=gain=6:frequency=100:width_type=h:width=100',
    },
    'treble_boost': {
        'description': 'Treble boost (+4dB above 3kHz)',
        'filter': 'treble=gain=4:frequency=3000:width_type=h:width=2000',
    },
    'compressor': {
        'description': 'Dynamic range compression',
        'filter': 'acompressor=threshold=-20dB:ratio=4:attack=5:release=50',
    },
}

# Canonical filter chain order (shape signal → compress → normalize last)
EQ_CHAIN_ORDER = ['bass_boost', 'treble_boost', 'compressor', 'loudnorm']


@dataclass
class EQConfig:
    """Audio equalizer/processing configuration."""
    loudnorm: bool = False
    bass_boost: bool = False
    treble_boost: bool = False
    compressor: bool = False

    @property
    def any_enabled(self) -> bool:
        return any([self.loudnorm, self.bass_boost,
                    self.treble_boost, self.compressor])

    @property
    def enabled_effects(self) -> list[str]:
        """Return list of enabled effect names in canonical chain order."""
        return [e for e in EQ_CHAIN_ORDER if getattr(self, e)]

    def build_filter_chain(self) -> str | None:
        """Build the FFmpeg audio filter chain string.
        Returns None if no effects are enabled."""
        if not self.any_enabled:
            return None
        filters = [EQ_EFFECTS[e]['filter'] for e in self.enabled_effects]
        return ','.join(filters)

    def to_dict(self) -> dict:
        return {
            'loudnorm': self.loudnorm,
            'bass_boost': self.bass_boost,
            'treble_boost': self.treble_boost,
            'compressor': self.compressor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EQConfig:
        return cls(
            loudnorm=bool(data.get('loudnorm', False)),
            bass_boost=bool(data.get('bass_boost', False)),
            treble_boost=bool(data.get('treble_boost', False)),
            compressor=bool(data.get('compressor', False)),
        )


# Freshness thresholds for summary display (calendar days)
FRESHNESS_CURRENT_DAYS = 0
FRESHNESS_RECENT_DAYS = 7
FRESHNESS_STALE_DAYS = 30

# Worker pool defaults for parallel conversion
MAX_DEFAULT_WORKERS = 6
DEFAULT_WORKERS = min(os.cpu_count() or 1, MAX_DEFAULT_WORKERS)

# Default cleanup options for ID3 tag operations

# TXXX frame description constants for original tag preservation

# M4A tag key constants
M4A_TAG_TITLE = '\xa9nam'
M4A_TAG_ARTIST = '\xa9ART'
M4A_TAG_ALBUM = '\xa9alb'
M4A_TAG_COVER = 'covr'
M4A_TAG_GENRE = '\xa9gen'
M4A_TAG_TRACK_NUMBER = 'trkn'
M4A_TAG_DISC_NUMBER = 'disk'
M4A_TAG_YEAR = '\xa9day'
M4A_TAG_COMPOSER = '\xa9wrt'
M4A_TAG_ALBUM_ARTIST = 'aART'
M4A_TAG_BPM = 'tmpo'
M4A_TAG_COMMENT = '\xa9cmt'
M4A_TAG_COMPILATION = 'cpil'
M4A_TAG_GROUPING = '\xa9grp'
M4A_TAG_LYRICS = '\xa9lyr'
M4A_TAG_COPYRIGHT = 'cprt'

# Cover art constants
APIC_MIME_JPEG = "image/jpeg"
APIC_MIME_PNG = "image/png"
APIC_TYPE_FRONT_COVER = 3

# Apple domain filter for cookie cleanup
# Used by CookieManager.clean_cookies() to strip non-Apple cookies
APPLE_COOKIE_DOMAIN = 'apple.com'


# ── Output Type Profiles ──────────────────────────────────────────────────────

@dataclass
class OutputProfile:
    name: str
    description: str
    id3_title: str            # TIT2 template — e.g. "{artist} - {title}"
    id3_artist: str           # TPE1 template — e.g. "Various" or "{artist}"
    id3_album: str            # TALB template — e.g. "{playlist}" or "{album}"
    id3_genre: str            # TCON template — e.g. "Playlist" or "" (omit)
    id3_extra: dict           # Frame ID → template value, e.g. {"COMM": "note"}
    filename: str             # Output filename template — e.g. "{artist} - {title}"
    directory: str            # Output subdirectory template — "" (flat), "{artist}"
    id3_versions: list        # ID3 versions to include — e.g. ["v2.3"] or ["v2.4", "v1"]
    artwork_size: int         # >0=resize to max px, 0=original, -1=strip
    usb_dir: str = ""         # Subdirectory within USB volumes (e.g. "RZR/Music")


# Seed defaults — used for auto-migration and _create_default().
# At runtime, OUTPUT_PROFILES is populated from config.yaml via load_output_profiles().
DEFAULT_OUTPUT_PROFILES: dict = {
    "ride-command": {
        "description": "Polaris Ride Command infotainment system",
        "id3_title": "{artist} - {title}",
        "id3_artist": "Various",
        "id3_album": "{playlist}",
        "id3_genre": "Playlist",
        "id3_extra": {},
        "filename": "{artist} - {title}",
        "directory": "",
        "id3_versions": ["v2.3"],
        "artwork_size": 100,
        "usb_dir": "RZR/Music",
    },
    "basic": {
        "description": "Standard MP3 with original tags and artwork",
        "id3_title": "{title}",
        "id3_artist": "{artist}",
        "id3_album": "{album}",
        "id3_genre": "",
        "id3_extra": {},
        "filename": "{artist} - {title}",
        "directory": "{artist}/{album}",
        "id3_versions": ["v2.4"],
        "artwork_size": 0,
        "usb_dir": "",
    },
}

OUTPUT_PROFILES: dict = {}  # Populated at runtime by load_output_profiles()
DEFAULT_OUTPUT_TYPE = "ride-command"

# Valid ID3 version tokens for the id3_versions list
VALID_ID3_VERSIONS = ("v2.3", "v2.4", "v1")

# Profile name validation: lowercase alphanumeric with hyphens
VALID_PROFILE_NAME_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')

# Required fields for each profile entry in config.yaml
_PROFILE_REQUIRED_FIELDS = (
    "description", "id3_title", "id3_artist", "id3_album", "id3_genre",
    "id3_extra", "filename", "directory", "id3_versions",
    "artwork_size",
)


def _validate_profile(name, data):
    """Validate a single profile entry from config.yaml.

    Raises ValueError with a descriptive message on any validation failure.
    """
    # Name validation
    if not VALID_PROFILE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid profile name '{name}': must be lowercase alphanumeric "
            f"with hyphens (e.g., 'my-device', 'car-stereo')")

    # Required fields
    for field_name in _PROFILE_REQUIRED_FIELDS:
        if field_name not in data:
            raise ValueError(
                f"Profile '{name}': missing required field '{field_name}'")

    # Type and value validation
    desc = data["description"]
    if not isinstance(desc, str) or not desc.strip():
        raise ValueError(
            f"Profile '{name}': 'description' must be a non-empty string")

    # Template string fields — must be non-empty strings
    for field_name in ("id3_title", "id3_artist", "id3_album"):
        val = data[field_name]
        if not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"Profile '{name}': '{field_name}' must be a non-empty string")

    # id3_genre — must be a string (empty string = omit genre tag)
    ig = data["id3_genre"]
    if not isinstance(ig, str):
        raise ValueError(
            f"Profile '{name}': 'id3_genre' must be a string, got {ig!r}")

    # id3_extra — must be a dict with string keys and string values
    et = data["id3_extra"]
    if not isinstance(et, dict):
        raise ValueError(
            f"Profile '{name}': 'id3_extra' must be a mapping, got {type(et).__name__}")
    for frame_id, val in et.items():
        if not isinstance(frame_id, str) or not isinstance(val, str):
            raise ValueError(
                f"Profile '{name}': 'id3_extra' keys and values must be strings, "
                f"got {frame_id!r}: {val!r}")

    # filename — must be a non-empty template string
    ff = data["filename"]
    if not isinstance(ff, str) or not ff.strip():
        raise ValueError(
            f"Profile '{name}': 'filename' must be a non-empty string")

    # directory — empty string means flat output
    df = data["directory"]
    if not isinstance(df, str):
        raise ValueError(
            f"Profile '{name}': 'directory' must be a string, got {df!r}")

    # id3_versions — must be a non-empty list of valid version tokens
    iv = data["id3_versions"]
    if not isinstance(iv, list) or not iv:
        raise ValueError(
            f"Profile '{name}': 'id3_versions' must be a non-empty list")
    for v in iv:
        if v not in VALID_ID3_VERSIONS:
            raise ValueError(
                f"Profile '{name}': 'id3_versions' contains invalid version '{v}' "
                f"(valid: {', '.join(VALID_ID3_VERSIONS)})")

    asize = data["artwork_size"]
    if not isinstance(asize, int) or isinstance(asize, bool) or asize < -1:
        raise ValueError(
            f"Profile '{name}': 'artwork_size' must be an integer >= -1, got {asize!r}")

    # usb_dir is optional (defaults to "")
    if "usb_dir" in data:
        ud = data["usb_dir"]
        if not isinstance(ud, str):
            raise ValueError(
                f"Profile '{name}': 'usb_dir' must be a string, got {ud!r}")


_KNOWN_SETTINGS_KEYS = {
    'output_type', 'workers', 'quality_preset',
    'api_key', 'server_name', 'log_retention_days', 'scheduler',
}


def validate_config(conf_path=DEFAULT_CONFIG_FILE):
    """Validate config.yaml independently and return a structured report.

    Returns a list of (level, message) tuples where level is "ok", "warning",
    or "error". Does not modify any state or raise exceptions.
    """
    import yaml

    results = []
    path = Path(conf_path)

    # 1. File exists and is readable
    if not path.exists():
        results.append(("error", f"Config file not found: {conf_path}"))
        return results

    try:
        raw = path.read_text()
    except OSError as e:
        results.append(("error", f"Cannot read config file: {e}"))
        return results
    results.append(("ok", f"Config file readable: {conf_path}"))

    # 2. Valid YAML syntax
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        results.append(("error", f"Invalid YAML syntax: {e}"))
        return results
    results.append(("ok", "Valid YAML syntax"))

    if not isinstance(data, dict):
        results.append(("error", "Config root must be a YAML mapping"))
        return results

    # 2b. schema_version
    sv = data.get('schema_version')
    if sv is None:
        results.append(("warning", "Missing 'schema_version' "
                         "(run migrate_config_schema() to add it)"))
    elif not isinstance(sv, int) or isinstance(sv, bool) or sv < 1:
        results.append(("error", f"'schema_version' must be a positive integer, got {sv!r}"))
    else:
        results.append(("ok", f"schema_version = {sv}"))

    # 3. settings section
    settings = data.get('settings')
    if settings is None:
        results.append(("warning", "Missing 'settings' section"))
        settings = {}
    elif not isinstance(settings, dict):
        results.append(("error", "'settings' must be a mapping"))
        settings = {}
    else:
        results.append(("ok", "'settings' section present"))

    # Collect profile names for output_type validation
    raw_types = data.get('output_types')
    profile_names = list(raw_types.keys()) if isinstance(raw_types, dict) else []

    # 4. settings.output_type
    if 'output_type' in settings:
        ot = settings['output_type']
        if not isinstance(ot, str):
            results.append(("error", f"settings.output_type must be a string, got {type(ot).__name__}"))
        elif profile_names and ot not in profile_names:
            results.append(("error", f"settings.output_type '{ot}' not found in output_types "
                            f"(available: {', '.join(profile_names)})"))
        else:
            results.append(("ok", f"settings.output_type = '{ot}'"))

    # 6. settings.workers
    if 'workers' in settings:
        w = settings['workers']
        if not isinstance(w, int) or isinstance(w, bool) or w < 1:
            results.append(("error", f"settings.workers must be an integer >= 1, got {w!r}"))
        else:
            results.append(("ok", f"settings.workers = {w}"))

    # 10. Warn on unknown settings keys
    unknown = set(settings.keys()) - _KNOWN_SETTINGS_KEYS
    for key in sorted(unknown):
        results.append(("warning", f"Unknown settings key: '{key}'"))

    # 7. output_types section
    if raw_types is None:
        results.append(("warning", "Missing 'output_types' section (will be auto-created on next run)"))
    elif not isinstance(raw_types, dict):
        results.append(("error", "'output_types' must be a mapping"))
    elif len(raw_types) == 0:
        results.append(("error", "'output_types' is empty — at least one profile is required"))
    else:
        results.append(("ok", f"'output_types' section has {len(raw_types)} profile(s)"))

        # 8. Validate each profile
        for name, fields in raw_types.items():
            try:
                _validate_profile(name, fields)
                results.append(("ok", f"Profile '{name}' is valid"))
            except ValueError as e:
                results.append(("error", str(e)))

    # 9. playlists section
    playlists_raw = data.get('playlists')
    if playlists_raw is None:
        results.append(("warning", "Missing 'playlists' section"))
    elif not isinstance(playlists_raw, list):
        results.append(("error", "'playlists' must be a list"))
    else:
        results.append(("ok", f"'playlists' section has {len(playlists_raw)} entry/entries"))
        for i, entry in enumerate(playlists_raw):
            if not isinstance(entry, dict):
                results.append(("error", f"Playlist entry {i + 1}: must be a mapping"))
                continue
            missing = [f for f in ('key', 'url', 'name') if not entry.get(f)]
            if missing:
                results.append(("error", f"Playlist entry {i + 1}: missing required field(s): "
                                f"{', '.join(missing)}"))

        # 11. Warn on duplicate playlist keys
        seen_keys = {}
        for i, entry in enumerate(playlists_raw):
            if isinstance(entry, dict):
                key = entry.get('key', '')
                if key:
                    if key in seen_keys:
                        results.append(("warning", f"Duplicate playlist key '{key}' "
                                        f"(entries {seen_keys[key]} and {i + 1})"))
                    else:
                        seen_keys[key] = i + 1

    # 12. destinations section (optional)
    destinations_raw = data.get('destinations')
    if destinations_raw is not None:
        if not isinstance(destinations_raw, list):
            results.append(("error", "'destinations' must be a list"))
        else:
            if destinations_raw:
                results.append(("ok", f"'destinations' section has {len(destinations_raw)} entry/entries"))
            for i, entry in enumerate(destinations_raw):
                if not isinstance(entry, dict):
                    results.append(("error", f"Destination entry {i + 1}: must be a mapping"))
                    continue
                if not entry.get('name'):
                    results.append(("error", f"Destination entry {i + 1}: missing 'name'"))
                if not entry.get('path'):
                    results.append(("error", f"Destination entry {i + 1}: missing 'path'"))

    return results


def load_output_profiles(config):
    """Populate the module-level OUTPUT_PROFILES dict from a ConfigManager instance.

    Must be called after ConfigManager has loaded config.yaml.
    Raises ValueError if settings.output_type references a nonexistent profile.
    """
    OUTPUT_PROFILES.clear()
    for name, profile in config.output_profiles.items():
        OUTPUT_PROFILES[name] = profile

    # Validate that settings.output_type references an existing profile
    selected = config.get_setting('output_type', DEFAULT_OUTPUT_TYPE)
    if selected not in OUTPUT_PROFILES:
        available = ", ".join(OUTPUT_PROFILES.keys())
        raise ValueError(
            f"settings.output_type '{selected}' not found in output_types. "
            f"Available profiles: {available}")


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
_tqdm = None   # set by _init_third_party()

def _init_third_party():
    """Import third-party packages after DependencyChecker has ensured they exist."""
    global _tqdm
    if _tqdm is not None:
        return
    from tqdm import tqdm as _tqdm_cls
    _tqdm_cls.monitor_interval = 0  # Prevent TMonitor thread from interfering with input()
    _tqdm = _tqdm_cls


# ══════════════════════════════════════════════════════════════════
# Section 2: Logging Infrastructure
# ══════════════════════════════════════════════════════════════════

class Logger:
    """Manages logging to both console and timestamped log file."""

    def __init__(self, log_dir=DEFAULT_LOG_DIR, verbose=False, echo_to_console=True):
        self.verbose = verbose
        self.echo_to_console = echo_to_console
        self._lock = threading.Lock()
        self._active_bars = []
        self.log_file = None

        try:
            self.log_dir = Path(log_dir)
            self.log_dir.mkdir(exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.log_file = self.log_dir / f"{date_str}.log"
            # Verify we can write to the log file (creates or appends)
            self.log_file.touch()
        except PermissionError:
            self.log_file = None
            if echo_to_console:
                print(f"Warning: Permission denied writing to {log_dir}/. "
                      "File logging disabled for this session.")

    def register_bar(self, bar):
        """Register an active tqdm bar for write routing."""
        self._active_bars.append(bar)

    def unregister_bar(self, bar):
        """Unregister a tqdm bar."""
        try:
            self._active_bars.remove(bar)
        except ValueError:
            pass

    def _write(self, level, message):
        """Write message to both console and log file."""
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_with_prefix = f"[{timestamp}] [{level}] {message}"

            # Console: route through tqdm.write() if a bar is active
            if self.echo_to_console:
                if self._active_bars and _tqdm is not None:
                    _tqdm.write(message)
                else:
                    print(message)

            # File: full format with timestamp and level
            if self.log_file:
                try:
                    with open(self.log_file, 'a') as f:
                        f.write(formatted_with_prefix + '\n')
                except PermissionError:
                    pass

    def _write_file_only(self, level, message):
        """Write message to log file only (no console output)."""
        if not self.log_file:
            return
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_with_prefix = f"[{timestamp}] [{level}] {message}"

            # File only: full format with timestamp and level
            try:
                with open(self.log_file, 'a') as f:
                    f.write(formatted_with_prefix + '\n')
            except PermissionError:
                pass

    def info(self, message):
        """Log informational message."""
        self._write("INFO", message)

    def file_info(self, message):
        """Log informational message to file only."""
        self._write_file_only("INFO", message)

    def warn(self, message):
        """Log warning message."""
        self._write("WARN", message)

    def error(self, message):
        """Log error message."""
        self._write("ERROR", message)

    def skip(self, message):
        """Log skip message."""
        self._write("SKIP", message)

    def ok(self, message):
        """Log success message."""
        self._write("OK", message)

    def dry_run(self, message):
        """Log dry-run message."""
        self._write("DRY-RUN", message)

    def debug(self, message):
        """Log debug message (only if verbose enabled)."""
        if self.verbose:
            self._write("VERBOSE", message)


class ProgressBar:
    """Context manager wrapping tqdm with project conventions.

    Disables gracefully during dry-run or when disable=True.
    Supports deferred initialization via set_total() for
    cases where the total isn't known upfront (e.g. Downloader).

    Saves and restores terminal state around the tqdm bar lifetime to
    prevent input() from hanging after the bar closes.
    """

    def __init__(self, total=0, desc="Processing", logger=None,
                 unit="file", disable=False):
        self._desc = desc
        self._unit = unit
        self._disabled = disable
        self._bar = None
        self.logger = logger
        self.total = total
        self._saved_termios = None
        self._current = 0
        self._update_lock = threading.Lock()
        self._progress_callback = None

        # If the logger supports progress callbacks (e.g. WebLogger), wire it up
        if logger and hasattr(logger, '_make_progress_callback'):
            self._progress_callback = logger._make_progress_callback()

        if not self._disabled and total > 0:
            self._create_bar(total)

    def _save_terminal(self):
        """Save terminal attributes before tqdm takes over."""
        try:
            import termios
            self._saved_termios = termios.tcgetattr(sys.stdin)
        except Exception:
            pass

    def _restore_terminal(self):
        """Restore terminal attributes after tqdm is done."""
        if self._saved_termios is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved_termios)
            except Exception:
                pass
            self._saved_termios = None

    def _create_bar(self, total):
        """Create the underlying tqdm bar."""
        self._save_terminal()
        self._bar = _tqdm(
            total=total,
            desc=self._desc,
            unit=self._unit,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            dynamic_ncols=True,
        )
        if self.logger:
            self.logger.register_bar(self._bar)

    def set_total(self, total):
        """Lazily initialize the bar when total becomes known."""
        self.total = total
        if self._bar is not None or self._disabled:
            return
        self._create_bar(total)

    def update(self, n=1):
        """Advance the progress bar."""
        if self._bar is not None:
            self._bar.update(n)
        if self._progress_callback is not None:
            with self._update_lock:
                self._current += n
            self._progress_callback(self._current, self.total, self._desc)

    def close(self):
        """Close the progress bar and unregister from logger."""
        if self._bar is not None:
            try:
                self._bar.close()
            finally:
                if self.logger:
                    self.logger.unregister_bar(self._bar)
                self._bar = None
                self._restore_terminal()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


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


# ══════════════════════════════════════════════════════════════════
# Section 2b: Data Directory Migration & Audit Logger
# ══════════════════════════════════════════════════════════════════

@dataclass
class MigrationEvent:
    """Deferred audit entry for schema/data migrations that run before AuditLogger exists."""
    operation: str
    description: str
    status: str
    params: dict = field(default_factory=dict)


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


def migrate_data_dir(logger=None):
    """Create data/ dir and migrate config.yaml/cookies.txt from project root if needed.

    Also enforces owner-only permissions on the data directory and all
    sensitive files within it (config.yaml, cookies.txt, database).

    Returns a list of MigrationEvent entries for deferred audit logging.
    """
    data_dir = Path(DEFAULT_DATA_DIR)
    data_dir.mkdir(exist_ok=True)
    _secure_path(data_dir, logger)

    # Enforce owner-only permissions on all sensitive files every startup
    for sensitive_file in (DEFAULT_CONFIG_FILE, DEFAULT_COOKIES, DEFAULT_DB_FILE,
                           'data/cookies.txt.backup', 'data/config.yaml.backup'):
        _secure_path(Path(sensitive_file), logger)

    migrations = [
        ('config.yaml', DEFAULT_CONFIG_FILE),
        ('cookies.txt', DEFAULT_COOKIES),
        ('cookies.txt.backup', 'data/cookies.txt.backup'),
        ('config.yaml.backup', 'data/config.yaml.backup'),
    ]
    moved = []
    for old, new in migrations:
        old_path, new_path = Path(old), Path(new)
        if old_path.exists() and not new_path.exists():
            shutil.move(str(old_path), str(new_path))
            moved.append(f"{old} → {new}")
            if logger:
                logger.info(f"Migrated {old} → {new}")

    if moved:
        return [MigrationEvent(
            'data_migrate',
            f"Migrated {len(moved)} legacy file{'s' if len(moved) != 1 else ''} to data/",
            'completed',
            {'files': moved},
        )]
    return []


def migrate_db_schema(logger=None):
    """Apply sequential DB schema migrations using PRAGMA user_version.

    Call once at startup, before any DB class is instantiated.
    Creates all tables on a fresh DB; upgrades existing DBs version-by-version.

    Returns a list of MigrationEvent entries for deferred audit logging.
    """
    db_path = Path(DEFAULT_DB_FILE)
    if not db_path.parent.exists():
        return []  # data/ dir not yet created — nothing to migrate

    fresh = not db_path.exists()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]

        if current >= DB_SCHEMA_VERSION:
            return []  # already up to date

        from_version = current
        changes = []

        # ── Version 0 → 1 ────────────────────────────────────────────
        if current < 1:
            if not fresh:
                # Migrate legacy usb_keys/usb_sync_files → sync_keys/sync_files
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
                if 'usb_keys' in tables and 'sync_keys' not in tables:
                    conn.execute("ALTER TABLE usb_keys RENAME TO sync_keys")
                    conn.execute(
                        "ALTER TABLE usb_sync_files RENAME TO sync_files")
                    try:
                        conn.execute(
                            "ALTER TABLE sync_files "
                            "RENAME COLUMN usb_key TO sync_key")
                    except Exception:
                        conn.execute("""
                            CREATE TABLE sync_files_new (
                                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                                sync_key  TEXT NOT NULL,
                                file_path TEXT NOT NULL,
                                playlist  TEXT NOT NULL,
                                synced_at REAL NOT NULL,
                                FOREIGN KEY (sync_key)
                                    REFERENCES sync_keys(key_name)
                                    ON DELETE CASCADE,
                                UNIQUE(sync_key, file_path, playlist)
                            )
                        """)
                        conn.execute("""
                            INSERT INTO sync_files_new
                                (id, sync_key, file_path, playlist, synced_at)
                            SELECT id, usb_key, file_path, playlist, synced_at
                            FROM sync_files
                        """)
                        conn.execute("DROP TABLE sync_files")
                        conn.execute(
                            "ALTER TABLE sync_files_new "
                            "RENAME TO sync_files")
                    conn.execute("DROP INDEX IF EXISTS idx_usb_sync_key")
                    conn.execute("DROP INDEX IF EXISTS idx_usb_sync_playlist")
                    changes.append("renamed usb_keys → sync_keys")
                    if logger:
                        logger.info(
                            "DB migration 0→1: renamed usb_keys → sync_keys")

            changes.append("ensured tables: audit_entries, task_history, sync_keys, sync_files")
            # Safety net: ensure all current tables and indexes exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    operation   TEXT NOT NULL,
                    description TEXT NOT NULL,
                    params      TEXT,
                    status      TEXT NOT NULL,
                    duration_s  REAL,
                    source      TEXT NOT NULL DEFAULT 'cli'
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_entries(timestamp)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_audit_operation
                ON audit_entries(operation)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_audit_status
                ON audit_entries(status)""")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id          TEXT PRIMARY KEY,
                    operation   TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    result      TEXT,
                    error       TEXT NOT NULL DEFAULT '',
                    started_at  REAL NOT NULL DEFAULT 0,
                    finished_at REAL NOT NULL DEFAULT 0,
                    source      TEXT NOT NULL DEFAULT 'web'
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_task_status
                ON task_history(status)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_task_operation
                ON task_history(operation)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_task_started_at
                ON task_history(started_at)""")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_keys (
                    key_name    TEXT PRIMARY KEY,
                    last_sync_at REAL NOT NULL DEFAULT 0,
                    created_at  REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_files (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_key  TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    playlist  TEXT NOT NULL,
                    synced_at REAL NOT NULL,
                    FOREIGN KEY (sync_key) REFERENCES sync_keys(key_name)
                        ON DELETE CASCADE,
                    UNIQUE(sync_key, file_path, playlist)
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_sync_files_key
                ON sync_files(sync_key)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_sync_files_playlist
                ON sync_files(sync_key, playlist)""")

            conn.execute("PRAGMA user_version = 1")
            conn.commit()
            if logger:
                logger.info("DB schema initialized at version 1")

        # ── Version 1 → 2: eq_presets table ──────────────────────────
        if current < 2:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eq_presets (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile      TEXT NOT NULL,
                    playlist     TEXT,
                    loudnorm     INTEGER NOT NULL DEFAULT 0,
                    bass_boost   INTEGER NOT NULL DEFAULT 0,
                    treble_boost INTEGER NOT NULL DEFAULT 0,
                    compressor   INTEGER NOT NULL DEFAULT 0,
                    updated_at   REAL NOT NULL DEFAULT 0,
                    UNIQUE(profile, playlist)
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_eq_profile
                ON eq_presets(profile)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_eq_profile_playlist
                ON eq_presets(profile, playlist)""")
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
            changes.append("added eq_presets table for audio EQ configuration")
            if logger:
                logger.info("DB migration 1→2: added eq_presets table")

        # ── Version 2 → 3: scheduled_jobs table ───────────────────────
        if current < 3:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_name         TEXT PRIMARY KEY,
                    next_run_time    REAL,
                    last_run_time    REAL,
                    last_run_status  TEXT NOT NULL DEFAULT '',
                    last_run_error   TEXT NOT NULL DEFAULT '',
                    on_missed        TEXT NOT NULL DEFAULT 'run',
                    updated_at       REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next
                ON scheduled_jobs(next_run_time)""")
            conn.execute("PRAGMA user_version = 3")
            conn.commit()
            changes.append("added scheduled_jobs table for persistent scheduling")
            if logger:
                logger.info("DB migration 2→3: added scheduled_jobs table")

        # ── Version 3 → 4: tracks table for library metadata ─────────
        if current < 4:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    uuid            TEXT PRIMARY KEY,
                    playlist        TEXT NOT NULL,
                    file_path       TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    artist          TEXT NOT NULL,
                    album           TEXT NOT NULL,
                    cover_art_path  TEXT,
                    cover_art_hash  TEXT,
                    duration_s      REAL,
                    file_size_bytes INTEGER,
                    source_m4a_path TEXT,
                    created_at      REAL NOT NULL,
                    updated_at      REAL NOT NULL
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_tracks_playlist
                ON tracks(playlist)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_tracks_file_path
                ON tracks(file_path)""")
            conn.execute("PRAGMA user_version = 4")
            conn.commit()
            changes.append("added tracks table for library metadata storage")
            if logger:
                logger.info("DB migration 3→4: added tracks table")

        # ── Version 4 → 5: index on source_m4a_path ──────────────────
        if current < 5:
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_tracks_source_m4a
                ON tracks(source_m4a_path)""")
            conn.execute("PRAGMA user_version = 5")
            conn.commit()
            changes.append("added index on tracks.source_m4a_path")
            if logger:
                logger.info("DB migration 4→5: added source_m4a_path index")

        # ── Version 5 → 6: extended metadata columns + library restructure ──
        if current < 6:
            # 1. DDL: add 14 new metadata columns to tracks table
            new_columns = [
                ("genre", "TEXT"),
                ("track_number", "INTEGER"),
                ("track_total", "INTEGER"),
                ("disc_number", "INTEGER"),
                ("disc_total", "INTEGER"),
                ("year", "TEXT"),
                ("composer", "TEXT"),
                ("album_artist", "TEXT"),
                ("bpm", "INTEGER"),
                ("comment", "TEXT"),
                ("compilation", "INTEGER"),
                ("grouping", "TEXT"),
                ("lyrics", "TEXT"),
                ("copyright", "TEXT"),
            ]
            existing_cols = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(tracks)").fetchall()
            }
            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    conn.execute(
                        f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}")
            conn.commit()

            # 2. File moves: restructure library directories on disk
            library_root = Path(DEFAULT_LIBRARY_DIR)
            new_source_root = library_root / SOURCE_SUBDIR / DEFAULT_IMPORTER
            new_mp3_dir = library_root / AUDIO_SUBDIR
            new_artwork_dir = library_root / ARTWORK_SUBDIR

            if library_root.exists():
                new_source_root.mkdir(parents=True, exist_ok=True)
                new_mp3_dir.mkdir(parents=True, exist_ok=True)
                new_artwork_dir.mkdir(parents=True, exist_ok=True)

                reserved_dirs = {SOURCE_SUBDIR, AUDIO_SUBDIR, ARTWORK_SUBDIR}
                for item in sorted(library_root.iterdir()):
                    if not item.is_dir() or item.name.startswith('.'):
                        continue
                    if item.name in reserved_dirs:
                        continue

                    playlist_name = item.name
                    old_source = item / "source"
                    old_output = item / "output"
                    old_artwork = item / "artwork"

                    # Move source/ → library/source/gamdl/<playlist>/
                    if old_source.exists():
                        dest = new_source_root / playlist_name
                        if not dest.exists():
                            shutil.move(str(old_source), str(dest))

                    # Move output/*.mp3 → library/audio/
                    if old_output.exists():
                        for f in old_output.iterdir():
                            if f.is_file():
                                dest_file = new_mp3_dir / f.name
                                if not dest_file.exists():
                                    shutil.move(str(f), str(dest_file))

                    # Move artwork/* → library/artwork/
                    if old_artwork.exists():
                        for f in old_artwork.iterdir():
                            if f.is_file():
                                dest_file = new_artwork_dir / f.name
                                if not dest_file.exists():
                                    shutil.move(str(f), str(dest_file))

                    # Remove empty old playlist directory
                    try:
                        shutil.rmtree(str(item))
                    except OSError:
                        pass  # Non-empty — skip

            # 3. DB path updates
            # file_path: library/<pl>/output/<uuid>.mp3 → library/audio/<uuid>.mp3
            conn.execute("""
                UPDATE tracks
                SET file_path = 'library/audio/' || SUBSTR(file_path,
                    INSTR(file_path, '/output/') + 8)
                WHERE file_path LIKE '%/output/%'
            """)
            # cover_art_path: artwork/<uuid>.ext → library/artwork/<uuid>.ext
            conn.execute("""
                UPDATE tracks
                SET cover_art_path = 'library/' || cover_art_path
                WHERE cover_art_path IS NOT NULL
                  AND cover_art_path LIKE 'artwork/%'
            """)
            # source_m4a_path: .../<pl>/source/... → .../source/gamdl/<pl>/...
            # Handles both relative (library/<pl>/source/...) and absolute paths
            conn.execute("""
                UPDATE tracks
                SET source_m4a_path = REPLACE(
                    source_m4a_path,
                    playlist || '/source/',
                    'source/gamdl/' || playlist || '/'
                )
                WHERE source_m4a_path LIKE '%' || playlist || '/source/%'
            """)
            conn.execute("PRAGMA user_version = 6")
            conn.commit()
            changes.append(
                "added extended metadata columns, restructured library layout")
            if logger:
                logger.info(
                    "DB migration 5→6: extended metadata + library restructure")

        return [MigrationEvent(
            'schema_migrate',
            f"DB schema migrated from version {from_version} to {DB_SCHEMA_VERSION}",
            'completed',
            {'target': 'database', 'from_version': from_version,
             'to_version': DB_SCHEMA_VERSION, 'changes': changes},
        )]

    finally:
        conn.close()

    return []


def migrate_config_schema(logger=None):
    """Apply sequential config.yaml schema migrations using a schema_version key.

    Call once at startup, before ConfigManager is instantiated.
    Consolidates inline migrations that previously lived in _load_yaml().

    Returns a list of MigrationEvent entries for deferred audit logging.
    """
    conf_path = Path(DEFAULT_CONFIG_FILE)
    if not conf_path.exists():
        return []  # will be created by ConfigManager._create_default()

    try:
        import yaml
    except ImportError:
        return []  # PyYAML not yet installed — DependencyChecker handles this

    with open(conf_path) as f:
        data = yaml.safe_load(f) or {}

    current = data.get('schema_version', 0)
    if current >= CONFIG_SCHEMA_VERSION:
        return []  # already up to date

    from_version = current
    changes = []

    dirty = False

    # ── Version 0 → 1 ────────────────────────────────────────────────
    if current < 1:
        # 1. Path scheme migration: plain paths → folder://
        for entry in data.get('destinations', []):
            dpath = str(entry.get('path', '')).strip()
            if (dpath and not dpath.startswith('usb://')
                    and not dpath.startswith('folder://')
                    and not dpath.startswith('web-client://')):
                entry['path'] = f'folder://{dpath}'
                dirty = True
                changes.append("path scheme migration")

        # 2. Output types auto-seed if missing/null
        import copy
        raw_types = data.get('output_types')
        if raw_types is None:
            data['output_types'] = copy.deepcopy(DEFAULT_OUTPUT_PROFILES)
            dirty = True
            changes.append("added default output_types")
            if logger:
                logger.info("Config migration 0→1: added default output_types")

        # 3. Relocate usb_dir from settings into per-profile
        settings = data.get('settings', {})
        if 'usb_dir' in settings:
            old_usb_dir = settings.pop('usb_dir')
            ot = data.get('output_types')
            if isinstance(ot, dict):
                for _pname, pfields in ot.items():
                    if isinstance(pfields, dict) and 'usb_dir' not in pfields:
                        pfields['usb_dir'] = old_usb_dir
            dirty = True
            changes.append("moved usb_dir into output profiles")
            if logger:
                logger.info(
                    "Config migration 0→1: moved usb_dir into output profiles")

        # 4. Backfill usb_dir in each profile from defaults
        ot = data.get('output_types')
        if isinstance(ot, dict):
            for pname, pfields in ot.items():
                if isinstance(pfields, dict) and 'usb_dir' not in pfields:
                    default_usb = DEFAULT_OUTPUT_PROFILES.get(
                        pname, {}).get('usb_dir', '')
                    pfields['usb_dir'] = default_usb
                    dirty = True

        data['schema_version'] = 1
        dirty = True

    # ── Version 1 → 2: template-based output profiles ──────────────
    if current < 2:
        ot = data.get('output_types')
        if isinstance(ot, dict):
            for _pname, pf in ot.items():
                if not isinstance(pf, dict):
                    continue

                # Move quality_preset from profile to settings (global)
                qp = pf.pop('quality_preset', None)
                if qp and 'quality_preset' not in data.get('settings', {}):
                    data.setdefault('settings', {})['quality_preset'] = qp

                # Convert pipeline_album → album_format
                pa = pf.pop('pipeline_album', None)
                if 'album_format' not in pf:
                    if pa == 'playlist_name':
                        pf['album_format'] = '{playlist}'
                    else:
                        pf['album_format'] = '{album}'

                # Convert pipeline_artist → artist_format
                par = pf.pop('pipeline_artist', None)
                if 'artist_format' not in pf:
                    if par == 'various':
                        pf['artist_format'] = 'Various'
                    else:
                        pf['artist_format'] = '{artist}'

                # Convert title_tag_format → title_format
                ttf = pf.pop('title_tag_format', None)
                if 'title_format' not in pf:
                    if ttf == 'artist_title':
                        pf['title_format'] = '{artist} - {title}'
                    else:
                        pf['title_format'] = '{title}'

                # Convert directory_structure → directory_format
                ds = pf.pop('directory_structure', None)
                if 'directory_format' not in pf:
                    if ds == 'nested-artist':
                        pf['directory_format'] = '{artist}'
                    elif ds == 'nested-artist-album':
                        pf['directory_format'] = '{artist}/{album}'
                    else:
                        pf['directory_format'] = ''

                # Convert filename_format fixed values → templates
                ff = pf.get('filename_format', '')
                if ff == 'full':
                    pf['filename_format'] = '{artist} - {title}'
                elif ff == 'title-only':
                    pf['filename_format'] = '{title}'

                # Convert id3_version + strip_id3v1 → id3_versions list
                iv = pf.pop('id3_version', None)
                si = pf.pop('strip_id3v1', None)
                if 'id3_versions' not in pf:
                    v2_tag = f'v2.{iv}' if iv in (3, 4) else 'v2.3'
                    if si is False:
                        pf['id3_versions'] = [v2_tag, 'v1']
                    else:
                        pf['id3_versions'] = [v2_tag]

                # Add extra_tags if missing
                if 'extra_tags' not in pf:
                    pf['extra_tags'] = {}

            dirty = True
            changes.append("migrated output profiles to template-based format")
            if logger:
                logger.info(
                    "Config migration 1→2: migrated profiles to templates")

        data['schema_version'] = 2
        dirty = True

    # ── Version 2 → 3: rename ID3 content fields with id3_ prefix ────
    if current < 3:
        ot = data.get('output_types')
        if isinstance(ot, dict):
            # Field renames: old_name → new_name
            _field_renames = {
                'title_format': 'id3_title',
                'artist_format': 'id3_artist',
                'album_format': 'id3_album',
                'extra_tags': 'id3_extra',
                'filename_format': 'filename',
                'directory_format': 'directory',
            }
            for _pname, pf in ot.items():
                if not isinstance(pf, dict):
                    continue

                # Rename fields
                for old_key, new_key in _field_renames.items():
                    if old_key in pf and new_key not in pf:
                        pf[new_key] = pf.pop(old_key)

                # Extract TCON from id3_extra into id3_genre
                if 'id3_genre' not in pf:
                    extra = pf.get('id3_extra', {})
                    if isinstance(extra, dict) and 'TCON' in extra:
                        pf['id3_genre'] = extra.pop('TCON')
                    else:
                        pf['id3_genre'] = ''

            dirty = True
            changes.append("renamed profile fields with id3_ prefix")
            if logger:
                logger.info(
                    "Config migration 2→3: renamed profile fields")

        data['schema_version'] = 3
        dirty = True

    if dirty:
        with open(conf_path, 'w') as f:
            f.write("# Music Porter Configuration\n")
            f.write("# CLI flags override these settings when specified.\n\n")
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        if logger:
            logger.info(
                f"Config schema updated to version {CONFIG_SCHEMA_VERSION}")
        return [MigrationEvent(
            'schema_migrate',
            f"Config schema migrated from version {from_version} to {CONFIG_SCHEMA_VERSION}",
            'completed',
            {'target': 'config', 'from_version': from_version,
             'to_version': CONFIG_SCHEMA_VERSION, 'changes': changes},
        )]

    return []


def flush_migration_events(events, audit_logger, source='cli'):
    """Flush deferred MigrationEvent entries into the audit trail."""
    for evt in events:
        audit_logger.log(evt.operation, evt.description, evt.status,
                         params=evt.params, source=source)


class AuditLogger:
    """Persistent audit trail using SQLite.

    Thread-safe via a write lock; reads are lockless (WAL mode).
    Each call opens/closes its own connection for thread safety.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    operation   TEXT NOT NULL,
                    description TEXT NOT NULL,
                    params      TEXT,
                    status      TEXT NOT NULL,
                    duration_s  REAL,
                    source      TEXT NOT NULL DEFAULT 'cli'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_entries(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_operation
                ON audit_entries(operation)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_status
                ON audit_entries(status)
            """)
            conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            conn.commit()
        finally:
            conn.close()

    def log(self, operation, description, status,
            params=None, duration_s=None, source='cli'):
        """Insert an audit entry."""
        ts = datetime.now(UTC).isoformat()
        params_json = json.dumps(params) if params else None
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO audit_entries
                       (timestamp, operation, description, params,
                        status, duration_s, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (ts, operation, description, params_json,
                     status, duration_s, source),
                )
                conn.commit()
            finally:
                conn.close()

    def get_entries(self, limit=50, offset=0,
                    operation=None, status=None,
                    date_from=None, date_to=None):
        """Return (entries, total) with optional filtering."""
        where_clauses = []
        params = []
        if operation:
            where_clauses.append("operation = ?")
            params.append(operation)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if date_from:
            where_clauses.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("timestamp <= ?")
            params.append(date_to + "T23:59:59")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = self._connect()
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM audit_entries {where_sql}",
                params,
            ).fetchone()[0]

            rows = conn.execute(
                f"""SELECT * FROM audit_entries {where_sql}
                    ORDER BY id DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()

            entries = []
            for row in rows:
                entry = dict(row)
                if entry.get('params'):
                    try:
                        entry['params'] = json.loads(entry['params'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                entries.append(entry)

            return entries, total
        finally:
            conn.close()

    def get_stats(self):
        """Return aggregate statistics."""
        conn = self._connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM audit_entries"
            ).fetchone()[0]

            today = datetime.now(UTC).strftime('%Y-%m-%d')
            today_count = conn.execute(
                "SELECT COUNT(*) FROM audit_entries WHERE timestamp >= ?",
                (today,),
            ).fetchone()[0]

            by_operation = {}
            for row in conn.execute(
                "SELECT operation, COUNT(*) as cnt FROM audit_entries "
                "GROUP BY operation ORDER BY cnt DESC"
            ):
                by_operation[row['operation']] = row['cnt']

            by_status = {}
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM audit_entries "
                "GROUP BY status ORDER BY cnt DESC"
            ):
                by_status[row['status']] = row['cnt']

            return {
                'total': total,
                'today': today_count,
                'by_operation': by_operation,
                'by_status': by_status,
            }
        finally:
            conn.close()

    def clear(self, before_date=None):
        """Delete entries, return count deleted."""
        with self._write_lock:
            conn = self._connect()
            try:
                if before_date:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM audit_entries "
                        "WHERE timestamp < ?",
                        (before_date + "T00:00:00",),
                    ).fetchone()[0]
                    conn.execute(
                        "DELETE FROM audit_entries WHERE timestamp < ?",
                        (before_date + "T00:00:00",),
                    )
                else:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM audit_entries"
                    ).fetchone()[0]
                    conn.execute("DELETE FROM audit_entries")
                conn.commit()
                return count
            finally:
                conn.close()


class TaskHistoryDB:
    """Persistent task history using SQLite.

    Follows the AuditLogger pattern: WAL mode, write lock, lockless reads,
    connection-per-call for thread safety.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id          TEXT PRIMARY KEY,
                    operation   TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'pending',
                    result      TEXT,
                    error       TEXT NOT NULL DEFAULT '',
                    started_at  REAL NOT NULL DEFAULT 0,
                    finished_at REAL NOT NULL DEFAULT 0,
                    source      TEXT NOT NULL DEFAULT 'web'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_status
                ON task_history(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_operation
                ON task_history(operation)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_started_at
                ON task_history(started_at)
            """)
            # Startup recovery: mark stale running/pending rows as failed
            conn.execute(
                """UPDATE task_history SET status = 'failed',
                   error = 'Server restarted during execution',
                   finished_at = ?
                   WHERE status IN ('running', 'pending')""",
                (time.time(),),
            )
            conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            conn.commit()
        finally:
            conn.close()

    def insert(self, task_id, operation, description, source='web'):
        """Insert a new task record."""
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO task_history
                       (id, operation, description, status, source)
                       VALUES (?, ?, ?, 'pending', ?)""",
                    (task_id, operation, description, source),
                )
                conn.commit()
            finally:
                conn.close()

    def update_status(self, task_id, status, result=None, error='',
                      started_at=None, finished_at=None):
        """Update task status and optional fields."""
        with self._write_lock:
            conn = self._connect()
            try:
                sets = ["status = ?"]
                params = [status]
                if result is not None:
                    sets.append("result = ?")
                    params.append(json.dumps(result))
                if error:
                    sets.append("error = ?")
                    params.append(error)
                if started_at is not None:
                    sets.append("started_at = ?")
                    params.append(started_at)
                if finished_at is not None:
                    sets.append("finished_at = ?")
                    params.append(finished_at)
                params.append(task_id)
                conn.execute(
                    f"UPDATE task_history SET {', '.join(sets)} WHERE id = ?",
                    params,
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, task_id):
        """Return a single task dict or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM task_history WHERE id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        finally:
            conn.close()

    def get_entries(self, limit=50, offset=0,
                    operation=None, status=None,
                    date_from=None, date_to=None):
        """Return (entries, total) with optional filtering."""
        where_clauses = []
        params = []
        if operation:
            where_clauses.append("operation = ?")
            params.append(operation)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if date_from:
            where_clauses.append("started_at >= ?")
            # Convert date string to epoch
            params.append(self._date_to_epoch(date_from))
        if date_to:
            where_clauses.append("started_at <= ?")
            params.append(self._date_to_epoch(date_to, end_of_day=True))

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        conn = self._connect()
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM task_history {where_sql}",
                params,
            ).fetchone()[0]

            rows = conn.execute(
                f"""SELECT * FROM task_history {where_sql}
                    ORDER BY started_at DESC, rowid DESC
                    LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()

            entries = [self._row_to_dict(row) for row in rows]
            return entries, total
        finally:
            conn.close()

    def get_stats(self):
        """Return aggregate statistics."""
        conn = self._connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM task_history"
            ).fetchone()[0]

            today_start = time.mktime(
                datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).timetuple()
            )
            today_count = conn.execute(
                "SELECT COUNT(*) FROM task_history WHERE started_at >= ?",
                (today_start,),
            ).fetchone()[0]

            by_operation = {}
            for row in conn.execute(
                "SELECT operation, COUNT(*) as cnt FROM task_history "
                "GROUP BY operation ORDER BY cnt DESC"
            ):
                by_operation[row['operation']] = row['cnt']

            by_status = {}
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM task_history "
                "GROUP BY status ORDER BY cnt DESC"
            ):
                by_status[row['status']] = row['cnt']

            return {
                'total': total,
                'today': today_count,
                'by_operation': by_operation,
                'by_status': by_status,
            }
        finally:
            conn.close()

    def clear(self, before_date=None):
        """Delete entries, return count deleted."""
        with self._write_lock:
            conn = self._connect()
            try:
                if before_date:
                    epoch = self._date_to_epoch(before_date)
                    count = conn.execute(
                        "SELECT COUNT(*) FROM task_history "
                        "WHERE started_at < ? AND status NOT IN ('running', 'pending')",
                        (epoch,),
                    ).fetchone()[0]
                    conn.execute(
                        "DELETE FROM task_history "
                        "WHERE started_at < ? AND status NOT IN ('running', 'pending')",
                        (epoch,),
                    )
                else:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM task_history "
                        "WHERE status NOT IN ('running', 'pending')"
                    ).fetchone()[0]
                    conn.execute(
                        "DELETE FROM task_history "
                        "WHERE status NOT IN ('running', 'pending')"
                    )
                conn.commit()
                return count
            finally:
                conn.close()

    @staticmethod
    def _date_to_epoch(date_str, end_of_day=False):
        """Convert 'YYYY-MM-DD' to epoch seconds."""
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return time.mktime(dt.timetuple())

    @staticmethod
    def _row_to_dict(row):
        entry = dict(row)
        # Parse JSON result
        if entry.get('result'):
            try:
                entry['result'] = json.loads(entry['result'])
            except (json.JSONDecodeError, TypeError):
                pass
        # Compute elapsed/duration
        started = entry.get('started_at', 0)
        finished = entry.get('finished_at', 0)
        if started and finished:
            entry['elapsed'] = round(finished - started, 1)
        elif started and entry.get('status') == 'running':
            entry['elapsed'] = round(time.time() - started, 1)
        else:
            entry['elapsed'] = 0
        return entry


class ScheduledJobsDB:
    """Persistent scheduled job state using SQLite.

    Follows the AuditLogger/TaskHistoryDB pattern: WAL mode, write lock,
    lockless reads, connection-per-call for thread safety.

    Stores runtime state (next_run_time, last_run_time, on_missed policy)
    for scheduled jobs so they survive server restarts.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_name         TEXT PRIMARY KEY,
                    next_run_time    REAL,
                    last_run_time    REAL,
                    last_run_status  TEXT NOT NULL DEFAULT '',
                    last_run_error   TEXT NOT NULL DEFAULT '',
                    on_missed        TEXT NOT NULL DEFAULT 'run',
                    updated_at       REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next
                ON scheduled_jobs(next_run_time)""")
            conn.commit()
        finally:
            conn.close()

    def get(self, job_name):
        """Return job state dict or None (lockless read)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE job_name = ?",
                (job_name,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def upsert(self, job_name, **fields):
        """Insert or update a job's state. Only provided fields are updated."""
        with self._write_lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT job_name FROM scheduled_jobs WHERE job_name = ?",
                    (job_name,),
                ).fetchone()

                fields['updated_at'] = time.time()

                if existing:
                    sets = []
                    params = []
                    for key, val in fields.items():
                        sets.append(f"{key} = ?")
                        params.append(val)
                    params.append(job_name)
                    conn.execute(
                        f"UPDATE scheduled_jobs SET {', '.join(sets)} "
                        f"WHERE job_name = ?",
                        params,
                    )
                else:
                    fields['job_name'] = job_name
                    cols = ', '.join(fields.keys())
                    placeholders = ', '.join('?' for _ in fields)
                    conn.execute(
                        f"INSERT INTO scheduled_jobs ({cols}) VALUES ({placeholders})",
                        list(fields.values()),
                    )
                conn.commit()
            finally:
                conn.close()

    def delete(self, job_name):
        """Remove a job's persisted state."""
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM scheduled_jobs WHERE job_name = ?",
                    (job_name,),
                )
                conn.commit()
            finally:
                conn.close()


class SyncTracker:
    """Persistent per-key file-level sync tracking using SQLite.

    Follows the AuditLogger/TaskHistoryDB pattern: WAL mode, write lock,
    lockless reads, connection-per-call for thread safety.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_keys (
                    key_name    TEXT PRIMARY KEY,
                    last_sync_at REAL NOT NULL DEFAULT 0,
                    created_at  REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_files (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_key  TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    playlist  TEXT NOT NULL,
                    synced_at REAL NOT NULL,
                    FOREIGN KEY (sync_key) REFERENCES sync_keys(key_name)
                        ON DELETE CASCADE,
                    UNIQUE(sync_key, file_path, playlist)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_files_key
                ON sync_files(sync_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_files_playlist
                ON sync_files(sync_key, playlist)
            """)
            conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            conn.commit()
        finally:
            conn.close()

    def record_file(self, sync_key, playlist, file_path):
        """Record a single synced file for a sync key and playlist."""
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO sync_keys (key_name, last_sync_at, created_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key_name) DO UPDATE SET last_sync_at = ?""",
                    (sync_key, now, now, now),
                )
                conn.execute(
                    """INSERT INTO sync_files
                           (sync_key, file_path, playlist, synced_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(sync_key, file_path, playlist)
                       DO UPDATE SET synced_at = ?""",
                    (sync_key, file_path, playlist, now, now),
                )
                conn.commit()
            finally:
                conn.close()

    def record_batch(self, sync_key, playlist, file_paths):
        """Record synced files for a sync key and playlist.

        Upserts the sync_keys row and inserts/replaces file records.
        """
        if not file_paths:
            return
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO sync_keys (key_name, last_sync_at, created_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key_name) DO UPDATE SET last_sync_at = ?""",
                    (sync_key, now, now, now),
                )
                conn.executemany(
                    """INSERT INTO sync_files
                           (sync_key, file_path, playlist, synced_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(sync_key, file_path, playlist)
                       DO UPDATE SET synced_at = ?""",
                    [(sync_key, fp, playlist, now, now) for fp in file_paths],
                )
                conn.commit()
            finally:
                conn.close()

    def delete_key(self, sync_key):
        """Delete a sync key and cascade-delete all its file records."""
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM sync_keys WHERE key_name = ?", (sync_key,)
                )
                conn.commit()
            finally:
                conn.close()

    def delete_playlist(self, sync_key, playlist):
        """Delete tracking records for one playlist on a sync key.

        Returns count of deleted records.
        """
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM sync_files WHERE sync_key = ? AND playlist = ?",
                    (sync_key, playlist),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def get_keys(self):
        """List all tracked sync keys with total synced file counts.

        Returns list of dicts: {key_name, last_sync_at, created_at,
        total_synced_files}.
        """
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT k.key_name, k.last_sync_at, k.created_at,
                       COUNT(f.id) AS total_synced_files
                FROM sync_keys k
                LEFT JOIN sync_files f ON f.sync_key = k.key_name
                GROUP BY k.key_name
                ORDER BY k.last_sync_at DESC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_synced_counts(self, sync_key):
        """Return per-playlist synced file counts for a sync key."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT playlist, COUNT(*) AS cnt
                   FROM sync_files WHERE sync_key = ?
                   GROUP BY playlist""",
                (sync_key,),
            ).fetchall()
            return {r['playlist']: r['cnt'] for r in rows}
        finally:
            conn.close()

    def get_synced_files(self, sync_key, playlist=None):
        """Return set of tracked file paths for a sync key.

        If playlist is provided, filter to that playlist only.
        """
        conn = self._connect()
        try:
            if playlist:
                rows = conn.execute(
                    """SELECT file_path FROM sync_files
                       WHERE sync_key = ? AND playlist = ?""",
                    (sync_key, playlist),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT file_path FROM sync_files WHERE sync_key = ?",
                    (sync_key,),
                ).fetchall()
            return {r['file_path'] for r in rows}
        finally:
            conn.close()

    def get_sync_status(self, sync_key, export_base_dir):
        """Diff export directory against tracked files for a sync key.

        Returns SyncStatusResult with per-playlist breakdown.
        """
        export_path = Path(export_base_dir)
        if not export_path.exists():
            return SyncStatusResult(
                sync_key=sync_key, last_sync_at=0, playlists=[],
                total_files=0, synced_files=0, new_files=0,
                new_playlists=0)

        # Get the key's last sync time
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT last_sync_at FROM sync_keys WHERE key_name = ?",
                (sync_key,),
            ).fetchone()
            last_sync = row['last_sync_at'] if row else 0
        finally:
            conn.close()

        synced_files_by_playlist = {}
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT playlist, file_path FROM sync_files
                   WHERE sync_key = ?""",
                (sync_key,),
            ).fetchall()
            for r in rows:
                synced_files_by_playlist.setdefault(
                    r['playlist'], set()).add(r['file_path'])
        finally:
            conn.close()

        playlists = []
        total_files = 0
        total_synced = 0
        total_new = 0
        new_playlist_count = 0

        for subdir in sorted(export_path.iterdir()):
            if not subdir.is_dir():
                continue
            playlist_name = subdir.name
            files_on_disk = {
                f.name for f in subdir.iterdir()
                if f.is_file() and f.suffix == '.mp3'
            }
            if not files_on_disk:
                continue

            tracked = synced_files_by_playlist.get(playlist_name, set())
            synced = files_on_disk & tracked
            new = files_on_disk - tracked
            is_new_playlist = len(tracked) == 0

            playlists.append({
                'name': playlist_name,
                'total_files': len(files_on_disk),
                'synced_files': len(synced),
                'new_files': len(new),
                'is_new_playlist': is_new_playlist,
            })
            total_files += len(files_on_disk)
            total_synced += len(synced)
            total_new += len(new)
            if is_new_playlist:
                new_playlist_count += 1

        return SyncStatusResult(
            sync_key=sync_key, last_sync_at=last_sync,
            playlists=playlists, total_files=total_files,
            synced_files=total_synced, new_files=total_new,
            new_playlists=new_playlist_count)

    def get_all_keys_summary(self, export_base_dir):
        """Summary for all tracked sync keys.

        Returns list of dicts: {key_name, last_sync_at, total_files,
        synced_files, new_files, new_playlists}.
        """
        keys = self.get_keys()
        results = []
        for key_info in keys:
            status = self.get_sync_status(
                key_info['key_name'], export_base_dir)
            results.append({
                'key_name': key_info['key_name'],
                'last_sync_at': key_info['last_sync_at'],
                'total_files': status.total_files,
                'synced_files': status.synced_files,
                'new_files': status.new_files,
                'new_playlists': status.new_playlists,
            })
        return results

    def prune_stale(self, sync_key, export_base_dir):
        """Remove DB records for files no longer in the export directory.

        Returns dict: {pruned_count, playlists_affected}.
        """
        export_path = Path(export_base_dir)

        # Fetch all tracked records for this key
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, playlist, file_path FROM sync_files WHERE sync_key = ?",
                (sync_key,),
            ).fetchall()
        finally:
            conn.close()

        stale_ids = []
        playlists_affected = set()
        for r in rows:
            file_on_disk = export_path / r['playlist'] / r['file_path']
            if not file_on_disk.exists():
                stale_ids.append(r['id'])
                playlists_affected.add(r['playlist'])

        if stale_ids:
            with self._write_lock:
                conn = self._connect()
                try:
                    conn.execute(
                        f"DELETE FROM sync_files WHERE id IN ({','.join('?' * len(stale_ids))})",
                        stale_ids,
                    )
                    conn.commit()
                finally:
                    conn.close()

        return {
            'pruned_count': len(stale_ids),
            'playlists_affected': sorted(playlists_affected),
        }

    def prune_all_keys(self, export_base_dir):
        """Prune stale records for all tracked sync keys.

        Returns dict: {total_pruned, keys_pruned}.
        """
        keys = self.get_keys()
        total_pruned = 0
        keys_pruned = []
        for key_info in keys:
            result = self.prune_stale(key_info['key_name'], export_base_dir)
            if result['pruned_count'] > 0:
                keys_pruned.append({
                    'key_name': key_info['key_name'],
                    'pruned_count': result['pruned_count'],
                    'playlists_affected': result['playlists_affected'],
                })
                total_pruned += result['pruned_count']
        return {'total_pruned': total_pruned, 'keys_pruned': keys_pruned}

    def merge_key(self, source_key, target_key):
        """Merge tracking records from source_key into target_key.

        Moves all sync_files records from source to target. Duplicate
        records (same file_path + playlist) keep the latest synced_at.
        After merge, the source key is deleted.

        Returns dict: {records_moved, records_merged, source_deleted}.
        """
        with self._write_lock:
            conn = self._connect()
            try:
                # Check if source key exists and has records
                source_count = conn.execute(
                    "SELECT COUNT(*) FROM sync_files WHERE sync_key = ?",
                    (source_key,),
                ).fetchone()[0]

                if source_count == 0:
                    return {'records_moved': 0, 'records_merged': 0,
                            'source_deleted': False}

                # Ensure target key exists
                now = time.time()
                conn.execute(
                    """INSERT INTO sync_keys (key_name, last_sync_at, created_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(key_name) DO UPDATE SET last_sync_at = ?""",
                    (target_key, now, now, now),
                )

                # Count existing overlaps for stats
                overlap_count = conn.execute(
                    """SELECT COUNT(*) FROM sync_files s
                       JOIN sync_files t ON t.sync_key = ?
                           AND t.file_path = s.file_path
                           AND t.playlist = s.playlist
                       WHERE s.sync_key = ?""",
                    (target_key, source_key),
                ).fetchone()[0]

                # Merge: insert or update keeping latest synced_at
                conn.execute(
                    """INSERT INTO sync_files (sync_key, file_path, playlist, synced_at)
                       SELECT ?, file_path, playlist, synced_at
                       FROM sync_files WHERE sync_key = ?
                       ON CONFLICT(sync_key, file_path, playlist)
                       DO UPDATE SET synced_at = MAX(synced_at, excluded.synced_at)""",
                    (target_key, source_key),
                )

                # Delete source key (CASCADE deletes remaining source records)
                conn.execute(
                    "DELETE FROM sync_keys WHERE key_name = ?",
                    (source_key,),
                )
                conn.commit()

                records_moved = source_count - overlap_count
                return {
                    'records_moved': records_moved,
                    'records_merged': overlap_count,
                    'source_deleted': True,
                }
            finally:
                conn.close()

    def rename_key(self, old_key, new_key):
        """Rename a sync key, moving all tracking records to the new name.

        Returns dict with stats, or None if new_key already exists.
        Unlike merge_key, rename requires the target name to be unused.
        """
        with self._write_lock:
            conn = self._connect()
            try:
                exists = conn.execute(
                    "SELECT 1 FROM sync_keys WHERE key_name = ?",
                    (new_key,),
                ).fetchone()
            finally:
                conn.close()
        if exists:
            return None
        return self.merge_key(old_key, new_key)

    def get_file_sync_map(self, playlist):
        """Map filenames to sync keys they've been synced to.

        Returns dict: {filename: [sync_key_name, ...]}.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT file_path, sync_key FROM sync_files
                   WHERE playlist = ? ORDER BY file_path, sync_key""",
                (playlist,),
            ).fetchall()
        finally:
            conn.close()

        sync_map = {}
        for r in rows:
            sync_map.setdefault(r['file_path'], []).append(r['sync_key'])
        return sync_map

    def get_all_sync_files(self):
        """Return all sync_file records as a list of dicts.

        Each dict has: id, sync_key, file_path, playlist, synced_at.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, sync_key, file_path, playlist, synced_at "
                "FROM sync_files"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_sync_files_by_ids(self, ids):
        """Delete sync_file records by their IDs.

        Returns count of deleted records.
        """
        if not ids:
            return 0
        with self._write_lock:
            conn = self._connect()
            try:
                placeholders = ','.join('?' * len(ids))
                cursor = conn.execute(
                    f"DELETE FROM sync_files WHERE id IN ({placeholders})",
                    list(ids),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()


# Backwards compatibility alias
USBSyncTracker = SyncTracker


class TrackDB:
    """Persistent library track metadata using SQLite.

    Stores title, artist, album, cover art references, and file info for
    every MP3 in the library.  Library MP3s carry only a TXXX:TrackUUID
    tag; all human-readable metadata lives here and is applied on-the-fly
    by TagApplicator during sync/download.

    Follows the AuditLogger/SyncTracker pattern:
    WAL mode, write lock, lockless reads, connection-per-call.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    uuid            TEXT PRIMARY KEY,
                    playlist        TEXT NOT NULL,
                    file_path       TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    artist          TEXT NOT NULL,
                    album           TEXT NOT NULL,
                    cover_art_path  TEXT,
                    cover_art_hash  TEXT,
                    duration_s      REAL,
                    file_size_bytes INTEGER,
                    source_m4a_path TEXT,
                    genre           TEXT,
                    track_number    INTEGER,
                    track_total     INTEGER,
                    disc_number     INTEGER,
                    disc_total      INTEGER,
                    year            TEXT,
                    composer        TEXT,
                    album_artist    TEXT,
                    bpm             INTEGER,
                    comment         TEXT,
                    compilation     INTEGER,
                    grouping        TEXT,
                    lyrics          TEXT,
                    copyright       TEXT,
                    created_at      REAL NOT NULL,
                    updated_at      REAL NOT NULL
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_tracks_playlist
                ON tracks(playlist)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_tracks_file_path
                ON tracks(file_path)""")
            conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            conn.commit()
        finally:
            conn.close()

    # ── Write methods (lock-protected) ────────────────────────────

    def insert_track(self, uuid, playlist, file_path, title, artist, album,
                     cover_art_path=None, cover_art_hash=None,
                     duration_s=None, file_size_bytes=None,
                     source_m4a_path=None, genre=None,
                     track_number=None, track_total=None,
                     disc_number=None, disc_total=None,
                     year=None, composer=None, album_artist=None,
                     bpm=None, comment=None, compilation=None,
                     grouping=None, lyrics=None, copyright_text=None):
        """Insert or replace a track record."""
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO tracks
                       (uuid, playlist, file_path, title, artist, album,
                        cover_art_path, cover_art_hash, duration_s,
                        file_size_bytes, source_m4a_path,
                        genre, track_number, track_total,
                        disc_number, disc_total, year, composer,
                        album_artist, bpm, comment, compilation,
                        grouping, lyrics, copyright,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?)
                       ON CONFLICT(uuid) DO UPDATE SET
                        playlist = excluded.playlist,
                        file_path = excluded.file_path,
                        title = excluded.title,
                        artist = excluded.artist,
                        album = excluded.album,
                        cover_art_path = excluded.cover_art_path,
                        cover_art_hash = excluded.cover_art_hash,
                        duration_s = excluded.duration_s,
                        file_size_bytes = excluded.file_size_bytes,
                        source_m4a_path = excluded.source_m4a_path,
                        genre = excluded.genre,
                        track_number = excluded.track_number,
                        track_total = excluded.track_total,
                        disc_number = excluded.disc_number,
                        disc_total = excluded.disc_total,
                        year = excluded.year,
                        composer = excluded.composer,
                        album_artist = excluded.album_artist,
                        bpm = excluded.bpm,
                        comment = excluded.comment,
                        compilation = excluded.compilation,
                        grouping = excluded.grouping,
                        lyrics = excluded.lyrics,
                        copyright = excluded.copyright,
                        updated_at = excluded.updated_at""",
                    (uuid, playlist, file_path, title, artist, album,
                     cover_art_path, cover_art_hash, duration_s,
                     file_size_bytes, source_m4a_path,
                     genre, track_number, track_total,
                     disc_number, disc_total, year, composer,
                     album_artist, bpm, comment, compilation,
                     grouping, lyrics, copyright_text, now, now),
                )
                conn.commit()
            finally:
                conn.close()

    def update_track_metadata(self, uuid, genre=None, track_number=None,
                              track_total=None, disc_number=None,
                              disc_total=None, year=None, composer=None,
                              album_artist=None, bpm=None, comment=None,
                              compilation=None, grouping=None,
                              lyrics=None, copyright_text=None,
                              title=None, artist=None, album=None):
        """Update metadata columns for an existing track by UUID."""
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """UPDATE tracks SET
                        title = COALESCE(?, title),
                        artist = COALESCE(?, artist),
                        album = COALESCE(?, album),
                        genre = ?, track_number = ?, track_total = ?,
                        disc_number = ?, disc_total = ?, year = ?,
                        composer = ?, album_artist = ?, bpm = ?,
                        comment = ?, compilation = ?, grouping = ?,
                        lyrics = ?, copyright = ?,
                        updated_at = ?
                       WHERE uuid = ?""",
                    (title, artist, album,
                     genre, track_number, track_total,
                     disc_number, disc_total, year,
                     composer, album_artist, bpm,
                     comment, compilation, grouping,
                     lyrics, copyright_text, now, uuid),
                )
                conn.commit()
            finally:
                conn.close()

    def repair_track(self, uuid, **kwargs):
        """Update repair-related fields for a track by UUID.

        Accepts keyword arguments for: file_size_bytes, cover_art_path,
        cover_art_hash, source_m4a_path.  Only provided fields are updated.
        """
        allowed = {'file_size_bytes', 'cover_art_path', 'cover_art_hash',
                    'source_m4a_path'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        now = time.time()
        set_clause = ', '.join(f"{col} = ?" for col in updates)
        set_clause += ', updated_at = ?'
        values = [*list(updates.values()), now, uuid]
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    f"UPDATE tracks SET {set_clause} WHERE uuid = ?",
                    values,
                )
                conn.commit()
            finally:
                conn.close()

    def delete_track(self, uuid):
        """Delete a single track by UUID."""
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM tracks WHERE uuid = ?", (uuid,))
                conn.commit()
            finally:
                conn.close()

    def delete_tracks_by_playlist(self, playlist):
        """Delete all tracks belonging to a playlist."""
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM tracks WHERE playlist = ?", (playlist,))
                conn.commit()
            finally:
                conn.close()

    # ── Read methods (lockless — WAL mode) ────────────────────────

    def get_track(self, uuid):
        """Return a single track as a dict, or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tracks WHERE uuid = ?", (uuid,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_track_by_path(self, file_path):
        """Return a track by its library file_path, or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tracks WHERE file_path = ?", (file_path,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_track_by_source_m4a(self, source_m4a_path):
        """Return a track by its source M4A path, or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tracks WHERE source_m4a_path = ?",
                (source_m4a_path,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_tracks_by_playlist(self, playlist):
        """Return all tracks for a playlist, ordered by title."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE playlist = ? ORDER BY title",
                (playlist,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_playlists(self):
        """Return a sorted list of distinct playlist names."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT playlist FROM tracks ORDER BY playlist"
            ).fetchall()
            return [r['playlist'] for r in rows]
        finally:
            conn.close()

    def get_playlist_stats(self):
        """Return per-playlist aggregate stats.

        Returns list of dicts with keys: playlist, track_count,
        total_size_bytes, cover_with, cover_without.
        """
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT playlist,
                       COUNT(*) AS track_count,
                       COALESCE(SUM(file_size_bytes), 0) AS total_size_bytes,
                       SUM(CASE WHEN cover_art_path IS NOT NULL
                           THEN 1 ELSE 0 END) AS cover_with,
                       SUM(CASE WHEN cover_art_path IS NULL
                           THEN 1 ELSE 0 END) AS cover_without
                FROM tracks
                GROUP BY playlist
                ORDER BY playlist
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_track_count(self):
        """Return the total number of tracks across all playlists."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM tracks").fetchone()
            return row['cnt'] if row else 0
        finally:
            conn.close()

    def get_all_tracks(self):
        """Return all tracks, ordered by playlist then title."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tracks ORDER BY playlist, title"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


class EQConfigManager:
    """Persistent EQ configuration per profile/playlist using SQLite.

    Follows the AuditLogger/SyncTracker pattern:
    WAL mode, write lock, lockless reads, connection-per-call.

    Precedence: playlist-specific override > profile default > none (no EQ).
    """

    def __init__(self, db_path=DEFAULT_DB_FILE):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eq_presets (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile      TEXT NOT NULL,
                    playlist     TEXT,
                    loudnorm     INTEGER NOT NULL DEFAULT 0,
                    bass_boost   INTEGER NOT NULL DEFAULT 0,
                    treble_boost INTEGER NOT NULL DEFAULT 0,
                    compressor   INTEGER NOT NULL DEFAULT 0,
                    updated_at   REAL NOT NULL DEFAULT 0,
                    UNIQUE(profile, playlist)
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_eq_profile
                ON eq_presets(profile)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_eq_profile_playlist
                ON eq_presets(profile, playlist)""")
            conn.commit()
        finally:
            conn.close()

    def get_eq(self, profile: str, playlist: str | None = None) -> EQConfig:
        """Get effective EQ config. Checks playlist override first, then profile default."""
        conn = self._connect()
        try:
            if playlist:
                row = conn.execute(
                    "SELECT loudnorm, bass_boost, treble_boost, compressor "
                    "FROM eq_presets WHERE profile = ? AND playlist = ?",
                    (profile, playlist),
                ).fetchone()
                if row:
                    return EQConfig(
                        loudnorm=bool(row['loudnorm']),
                        bass_boost=bool(row['bass_boost']),
                        treble_boost=bool(row['treble_boost']),
                        compressor=bool(row['compressor']),
                    )
            # Fall back to profile default (playlist IS NULL)
            row = conn.execute(
                "SELECT loudnorm, bass_boost, treble_boost, compressor "
                "FROM eq_presets WHERE profile = ? AND playlist IS NULL",
                (profile,),
            ).fetchone()
            if row:
                return EQConfig(
                    loudnorm=bool(row['loudnorm']),
                    bass_boost=bool(row['bass_boost']),
                    treble_boost=bool(row['treble_boost']),
                    compressor=bool(row['compressor']),
                )
            return EQConfig()  # No EQ configured
        finally:
            conn.close()

    def set_eq(self, profile: str, eq: EQConfig, playlist: str | None = None):
        """Set EQ config for a profile (default) or profile+playlist (override)."""
        with self._write_lock:
            conn = self._connect()
            try:
                now = time.time()
                if playlist:
                    # Playlist override: UPSERT via ON CONFLICT
                    conn.execute(
                        """INSERT INTO eq_presets
                               (profile, playlist, loudnorm, bass_boost,
                                treble_boost, compressor, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(profile, playlist) DO UPDATE SET
                               loudnorm=excluded.loudnorm,
                               bass_boost=excluded.bass_boost,
                               treble_boost=excluded.treble_boost,
                               compressor=excluded.compressor,
                               updated_at=excluded.updated_at""",
                        (profile, playlist, int(eq.loudnorm), int(eq.bass_boost),
                         int(eq.treble_boost), int(eq.compressor), now),
                    )
                else:
                    # Profile default (playlist IS NULL): delete+insert
                    # because SQLite UNIQUE treats NULLs as distinct
                    conn.execute(
                        "DELETE FROM eq_presets "
                        "WHERE profile = ? AND playlist IS NULL",
                        (profile,),
                    )
                    conn.execute(
                        """INSERT INTO eq_presets
                               (profile, playlist, loudnorm, bass_boost,
                                treble_boost, compressor, updated_at)
                           VALUES (?, NULL, ?, ?, ?, ?, ?)""",
                        (profile, int(eq.loudnorm), int(eq.bass_boost),
                         int(eq.treble_boost), int(eq.compressor), now),
                    )
                conn.commit()
            finally:
                conn.close()

    def delete_eq(self, profile: str, playlist: str | None = None):
        """Delete EQ config for a profile default or playlist override."""
        with self._write_lock:
            conn = self._connect()
            try:
                if playlist:
                    conn.execute(
                        "DELETE FROM eq_presets "
                        "WHERE profile = ? AND playlist = ?",
                        (profile, playlist),
                    )
                else:
                    conn.execute(
                        "DELETE FROM eq_presets "
                        "WHERE profile = ? AND playlist IS NULL",
                        (profile,),
                    )
                conn.commit()
            finally:
                conn.close()

    def list_eq(self, profile: str) -> list[dict]:
        """List all EQ configs for a profile (default + all playlist overrides)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT profile, playlist, loudnorm, bass_boost, treble_boost, "
                "compressor, updated_at FROM eq_presets WHERE profile = ? "
                "ORDER BY playlist IS NOT NULL, playlist",
                (profile,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_all(self) -> list[dict]:
        """List all EQ configs across all profiles."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT profile, playlist, loudnorm, bass_boost, treble_boost, "
                "compressor, updated_at FROM eq_presets "
                "ORDER BY profile, playlist IS NOT NULL, playlist",
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════
# Section 3: Configuration Management
# ══════════════════════════════════════════════════════════════════

class PlaylistConfig:
    """Represents a single playlist configuration."""

    def __init__(self, key, url, name):
        self.key = key
        self.url = url
        self.name = name

    def __repr__(self):
        return f"PlaylistConfig(key={self.key}, name={self.name})"


@dataclass
class SyncDestination:
    """A saved sync destination (name + schemed path).

    Paths use a scheme prefix:
      - usb:///Volumes/MY_USB/RZR/Music   → USB drive destination
      - folder:///path/to/dir             → Folder destination
      - web-client://My-USB               → Browser-local sync target
    Legacy plain paths are migrated to folder:// on config load.
    """
    name: str
    path: str  # usb:///Volumes/X/RZR/Music or folder:///path/to/dir
    sync_key: str = None  # optional link to a shared tracking key

    @property
    def type(self) -> str:
        if self.path.startswith('usb://'):
            return 'usb'
        if self.path.startswith('web-client://'):
            return 'web-client'
        return 'folder'

    @property
    def raw_path(self) -> str:
        if self.path.startswith('usb://'):
            return self.path[6:]
        if self.path.startswith('folder://'):
            return self.path[9:]
        if self.path.startswith('web-client://'):
            return self.path[13:]
        return self.path

    @property
    def is_usb(self) -> bool:
        return self.type == 'usb'

    @property
    def is_web_client(self) -> bool:
        return self.type == 'web-client'

    @property
    def effective_key(self) -> str:
        """Sync tracking key: sync_key if linked, else name."""
        return self.sync_key if self.sync_key else self.name

    @property
    def available(self) -> bool:
        if self.is_web_client:
            return True
        return Path(self.raw_path).is_dir()

    def to_api_dict(self) -> dict:
        d = {'name': self.name, 'path': self.path,
             'type': self.type, 'available': self.available,
             'effective_key': self.effective_key}
        if self.sync_key:
            d['sync_key'] = self.sync_key
        return d


class ConfigManager:
    """Manages configuration from config.yaml (YAML format)."""

    def __init__(self, conf_path=DEFAULT_CONFIG_FILE, logger=None,
                 audit_logger=None, audit_source='cli', on_change=None):
        self.conf_path = Path(conf_path)
        self.logger = logger or Logger()
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self._on_change = on_change
        self.playlists = []
        self.destinations = []
        self.settings = {}
        self.output_profiles = {}
        self._raw_output_types = {}

        if self.conf_path.exists():
            try:
                self._load_yaml()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn("PyYAML not available — cannot load config.yaml yet")
                self.settings = {}
                self.output_profiles = {}
                self._raw_output_types = {}
        else:
            try:
                self._create_default()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn(f"Configuration file not found: {self.conf_path}")
                self.settings = {}
                self.output_profiles = {}
                self._raw_output_types = {}

    def _load_yaml(self):
        """Load configuration from YAML file.

        Schema migrations are handled by migrate_config_schema() at startup.
        This method only loads and validates — no inline migrations.
        """
        import yaml

        with open(self.conf_path) as f:
            data = yaml.safe_load(f) or {}

        # Load settings
        self.settings = data.get('settings', {})

        # Load playlists
        for entry in data.get('playlists', []):
            key = entry.get('key', '').strip()
            url = entry.get('url', '').strip()
            name = entry.get('name', '').strip()
            if key and url and name:
                self.playlists.append(PlaylistConfig(key, url, name))
            elif key or url or name:
                self.logger.warn(f"Incomplete playlist entry (need key, url, name): {entry}")

        # Load destinations
        for entry in data.get('destinations', []):
            dname = str(entry.get('name', '')).strip()
            dpath = str(entry.get('path', '')).strip()
            if dname and dpath:
                dsync_key = str(entry.get('sync_key', '')).strip() or None
                self.destinations.append(SyncDestination(dname, dpath, sync_key=dsync_key))
            elif dname or dpath:
                self.logger.warn(f"Incomplete destination entry (need name, path): {entry}")

        # Load output_types
        raw_types = data.get('output_types')
        if raw_types is None:
            raise ValueError(
                "config.yaml: missing 'output_types' section "
                "(run migrate_config_schema() first or delete config.yaml to regenerate)")
        elif isinstance(raw_types, dict) and len(raw_types) == 0:
            raise ValueError(
                "config.yaml: 'output_types' is empty — at least one profile is required")

        # Validate and build OutputProfile instances
        self._raw_output_types = raw_types
        self.output_profiles = {}
        for name, fields in raw_types.items():
            _validate_profile(name, fields)
            self.output_profiles[name] = OutputProfile(
                name=name,
                description=fields["description"],
                id3_title=fields["id3_title"],
                id3_artist=fields["id3_artist"],
                id3_album=fields["id3_album"],
                id3_genre=fields["id3_genre"],
                id3_extra=dict(fields.get("id3_extra", {})),
                filename=fields["filename"],
                directory=fields["directory"],
                id3_versions=list(fields["id3_versions"]),
                artwork_size=fields["artwork_size"],
                usb_dir=fields.get("usb_dir", ""),
            )

        self.logger.info(f"Loaded {len(self.playlists)} playlists and "
                         f"{len(self.output_profiles)} output profiles from {self.conf_path}")

    def _create_default(self):
        """Create a default config.yaml with default profiles and empty playlists."""
        import copy
        self.settings = {
            'output_type': DEFAULT_OUTPUT_TYPE,
            'workers': DEFAULT_WORKERS,
            'quality_preset': DEFAULT_QUALITY_PRESET,
            'server_name': '',
            'log_retention_days': DEFAULT_LOG_RETENTION_DAYS,
        }
        self._raw_output_types = copy.deepcopy(DEFAULT_OUTPUT_PROFILES)
        # Build OutputProfile instances from defaults
        self.output_profiles = {}
        for name, fields in self._raw_output_types.items():
            profile_kwargs = {k: fields[k] for k in _PROFILE_REQUIRED_FIELDS}
            profile_kwargs['usb_dir'] = fields.get('usb_dir', '')
            self.output_profiles[name] = OutputProfile(
                name=name, **profile_kwargs
            )
        self._save()
        self.logger.info(f"Created default configuration: {self.conf_path}")

    def _save(self):
        """Write current configuration to YAML file."""
        import yaml

        # Serialize output_types from raw dict if available, else from profiles
        if self._raw_output_types:
            output_types = self._raw_output_types
        else:
            output_types = {}
            for name, p in self.output_profiles.items():
                fields = {f: getattr(p, f) for f in _PROFILE_REQUIRED_FIELDS}
                fields['usb_dir'] = p.usb_dir
                output_types[name] = fields

        data = {
            'schema_version': CONFIG_SCHEMA_VERSION,
            'settings': self.settings,
            'output_types': output_types,
            'playlists': [
                {'key': p.key, 'url': p.url, 'name': p.name}
                for p in self.playlists
            ],
        }

        if self.destinations:
            dest_list = []
            for d in self.destinations:
                entry = {'name': d.name, 'path': d.path}
                if d.sync_key:
                    entry['sync_key'] = d.sync_key
                dest_list.append(entry)
            data['destinations'] = dest_list

        with open(self.conf_path, 'w') as f:
            f.write("# Music Porter Configuration\n")
            f.write("# CLI flags override these settings when specified.\n\n")
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        if self._on_change:
            self._on_change()

    def get_setting(self, key, default=None):
        """Get a setting value, returning default if not set."""
        return self.settings.get(key, default)

    def update_setting(self, key, value):
        """Update a setting and persist to config.yaml."""
        self.settings[key] = value
        self._save()
        if self.audit_logger:
            self.audit_logger.log(
                'settings_update', f"Updated setting '{key}'",
                'completed', params={'key': key, 'value': value},
                source=self._audit_source)

    def get_playlist_by_key(self, key):
        """Get playlist by key (case-insensitive)."""
        key_lower = key.lower()
        for playlist in self.playlists:
            if playlist.key.lower() == key_lower:
                return playlist
        return None

    def get_playlist_by_index(self, index):
        """Get playlist by index (0-based)."""
        if 0 <= index < len(self.playlists):
            return self.playlists[index]
        return None

    def add_playlist(self, key, url, name):
        """Add a new playlist and persist to config.yaml."""
        if self.get_playlist_by_key(key):
            self.logger.warn(f"Playlist key '{key}' already exists")
            return False

        self.playlists.append(PlaylistConfig(key, url, name))
        self._save()
        self.logger.info(f"Added playlist '{name}' to configuration")
        if self.audit_logger:
            self.audit_logger.log(
                'playlist_add', f"Added playlist '{name}' ({key})",
                'completed', params={'key': key, 'name': name},
                source=self._audit_source)
        return True

    def update_playlist(self, key, url=None, name=None):
        """Update an existing playlist and persist to config.yaml."""
        playlist = self.get_playlist_by_key(key)
        if not playlist:
            self.logger.warn(f"Playlist key '{key}' not found")
            return False
        if url is not None:
            playlist.url = url
        if name is not None:
            playlist.name = name
        self._save()
        self.logger.info(f"Updated playlist '{key}'")
        if self.audit_logger:
            self.audit_logger.log(
                'playlist_update', f"Updated playlist '{key}'",
                'completed', params={'key': key, 'url': url, 'name': name},
                source=self._audit_source)
        return True

    def remove_playlist(self, key):
        """Remove a playlist by key (case-insensitive) and persist to config.yaml."""
        key_lower = key.lower()
        original_len = len(self.playlists)
        self.playlists = [p for p in self.playlists if p.key.lower() != key_lower]
        if len(self.playlists) == original_len:
            self.logger.warn(f"Playlist key '{key}' not found")
            return False
        self._save()
        self.logger.info(f"Removed playlist '{key}' from configuration")
        if self.audit_logger:
            self.audit_logger.log(
                'playlist_delete', f"Removed playlist '{key}'",
                'completed', params={'key': key},
                source=self._audit_source)
        return True

    def ensure_api_key(self):
        """Ensure an API key exists in settings; generate one if missing.

        Returns the API key string.
        """
        import secrets
        key = self.settings.get('api_key')
        if not key:
            key = secrets.token_urlsafe(32)
            self.settings['api_key'] = key
            self._save()
            self.logger.info("Generated new API key for web dashboard")
        return key

    # ── Destination CRUD ──────────────────────────────────────────

    def get_destination(self, name):
        """Get a saved destination by name (case-insensitive). Returns SyncDestination or None."""
        name_lower = name.lower()
        for dest in self.destinations:
            if dest.name.lower() == name_lower:
                return dest
        return None

    def add_destination(self, name, path, sync_key=None):
        """Add a saved sync destination. Returns True on success.

        Path should be a schemed path (usb:// or folder://).
        Plain paths are auto-prefixed with folder://.
        Optional sync_key links this destination to a shared tracking key.
        """
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9_-]+$', name):
            self.logger.error(f"Destination name must be alphanumeric with hyphens/underscores: '{name}'")
            return False
        if self.get_destination(name):
            self.logger.error(f"Destination '{name}' already exists")
            return False

        # Normalize to schemed path
        if (not path.startswith('usb://') and not path.startswith('folder://')
                and not path.startswith('web-client://')):
            path = f'folder://{path}'

        # Validate the raw filesystem path exists (skip for web-client)
        dest = SyncDestination(name, path, sync_key=sync_key)
        if not dest.is_web_client:
            raw = dest.raw_path
            if dest.is_usb:
                # For USB: validate the volume mount exists (subdir may not exist yet)
                volume_path = Path(raw).parts[:3] if IS_MACOS else Path(raw).parts[:1]
                volume_mount = Path(*volume_path) if volume_path else Path(raw)
                if not volume_mount.is_dir():
                    self.logger.error(f"USB volume mount not found: {volume_mount}")
                    return False
            else:
                if not Path(raw).is_dir():
                    self.logger.error(f"Destination path does not exist or is not a directory: {raw}")
                    return False

        self.destinations.append(dest)
        self._save()
        link_msg = f" (linked to '{sync_key}')" if sync_key else ''
        self.logger.info(f"Added sync destination '{name}' → {path}{link_msg}")
        if self.audit_logger:
            params = {'name': name, 'path': path}
            if sync_key:
                params['sync_key'] = sync_key
            self.audit_logger.log(
                'destination_add', f"Added sync destination '{name}'{link_msg}",
                'completed', params=params,
                source=self._audit_source)
        return True

    def remove_destination(self, name):
        """Remove a saved destination by name (case-insensitive). Returns True if found."""
        name_lower = name.lower()
        original_len = len(self.destinations)
        self.destinations = [d for d in self.destinations if d.name.lower() != name_lower]
        if len(self.destinations) == original_len:
            self.logger.warn(f"Destination '{name}' not found")
            return False
        self._save()
        self.logger.info(f"Removed sync destination '{name}'")
        if self.audit_logger:
            self.audit_logger.log(
                'destination_delete', f"Removed sync destination '{name}'",
                'completed', params={'name': name},
                source=self._audit_source)
        return True

    def update_destination_link(self, name, sync_key):
        """Set or clear a destination's sync_key. Returns True if found.

        Pass sync_key=None or '' to unlink.
        """
        dest = self.get_destination(name)
        if not dest:
            self.logger.warn(f"Destination '{name}' not found")
            return False
        old_key = dest.sync_key
        new_key = sync_key.strip() if sync_key else None
        dest.sync_key = new_key
        self._save()
        if new_key:
            self.logger.info(f"Linked destination '{name}' → key '{new_key}'")
        else:
            self.logger.info(f"Unlinked destination '{name}' (was '{old_key}')")
        if self.audit_logger:
            self.audit_logger.log(
                'destination_link',
                f"{'Linked' if new_key else 'Unlinked'} destination '{name}'"
                + (f" → '{new_key}'" if new_key else ''),
                'completed',
                params={'name': name, 'sync_key': new_key, 'old_sync_key': old_key},
                source=self._audit_source)
        return True

    def ensure_destination(self, name, path, sync_key=None):
        """Get or create a destination, auto-linking to sync_key if provided.

        Returns the SyncDestination (existing or newly created), or None on failure.
        """
        existing = self.get_destination(name)
        if existing:
            return existing
        ok = self.add_destination(name, path, sync_key=sync_key)
        return self.get_destination(name) if ok else None

    def rename_sync_key_refs(self, old_key, new_key):
        """Update all destination sync_key references from old_key to new_key.

        Returns count of destinations updated.
        """
        count = 0
        for dest in self.destinations:
            if dest.sync_key == old_key:
                dest.sync_key = new_key
                count += 1
        if count:
            self._save()
        return count

    def rename_destination(self, old_name, new_name):
        """Rename a saved destination. Returns True on success."""
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9_-]+$', new_name):
            self.logger.error(f"Destination name must be alphanumeric with hyphens/underscores: '{new_name}'")
            return False
        if old_name.lower() == new_name.lower():
            self.logger.error("New name must be different from the current name")
            return False
        if self.get_destination(new_name):
            self.logger.error(f"Destination '{new_name}' already exists")
            return False
        dest = self.get_destination(old_name)
        if not dest:
            self.logger.warn(f"Destination '{old_name}' not found")
            return False
        dest.name = new_name
        self._save()
        self.logger.info(f"Renamed destination '{old_name}' to '{new_name}'")
        if self.audit_logger:
            self.audit_logger.log(
                'destination_rename',
                f"Renamed destination '{old_name}' to '{new_name}'",
                'completed',
                params={'old_name': old_name, 'new_name': new_name},
                source=self._audit_source)
        return True


# ══════════════════════════════════════════════════════════════════
# Section 4: Dependency Checking
# ══════════════════════════════════════════════════════════════════

class DependencyChecker:
    """Checks and manages dependencies from requirements.txt."""

    # Maps pip package names to their Python import names
    IMPORT_MAP: ClassVar[dict[str, str]] = {
        'ffmpeg-python': 'ffmpeg',
        'webdriver-manager': 'webdriver_manager',
        'Pillow': 'PIL',
        'PyYAML': 'yaml',
        'Flask': 'flask',
    }

    # Packages that must be checked via subprocess instead of import
    SUBPROCESS_CHECK: ClassVar[set[str]] = {'gamdl'}

    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.venv_python = None
        self.venv_path = None
        self.dep_status = {
            'venv': False,
            'packages': {},
            'ffmpeg': False,
            'playlists': 0
        }
        self._detect_venv()

    def _detect_venv(self):
        """Detect virtual environment Python interpreter."""
        # sys.prefix != sys.base_prefix is Python's own venv detection
        if sys.prefix != sys.base_prefix:
            self.venv_python = sys.executable
            self.venv_path = sys.prefix
            self.dep_status['venv'] = True
            return

        # Not in a venv — check if .venv directory exists for install target
        if IS_WINDOWS:
            venv_path = Path('.venv/Scripts/python.exe')
        else:  # Unix (macOS, Linux)
            venv_path = Path('.venv/bin/python')

        if venv_path.exists():
            self.venv_python = str(venv_path.absolute())
            self.venv_path = str(Path('.venv').absolute())
            self.dep_status['venv'] = True
        else:
            self.venv_python = sys.executable
            self.dep_status['venv'] = False

    def _parse_requirements(self):
        """Parse package names from requirements.txt."""
        packages = []
        requirements_path = Path("requirements.txt")
        if not requirements_path.exists():
            return packages
        for line in requirements_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Extract package name (before any version specifier)
            name = line.split('>=')[0].split('<=')[0].split('==')[0].split('!=')[0].split('~=')[0].strip()
            if name:
                packages.append(name)
        return packages

    def _check_package(self, package_name):
        """Check if a single package is available. Returns True if installed."""
        if package_name in self.SUBPROCESS_CHECK:
            try:
                subprocess.run(
                    [self.venv_python, "-m", package_name, "--version"],
                    capture_output=True, check=True
                )
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False
        else:
            import_name = self.IMPORT_MAP.get(package_name, package_name)
            try:
                __import__(import_name)
                return True
            except ImportError:
                return False

    def check_python_packages(self):
        """Check all packages from requirements.txt, install if any are missing."""
        packages = self._parse_requirements()
        if not packages:
            self.logger.error("requirements.txt not found or empty")
            self._show_package_install_help()
            return False

        any_missing = False
        for pkg in packages:
            installed = self._check_package(pkg)
            self.dep_status['packages'][pkg] = installed
            if not installed:
                any_missing = True

        if any_missing:
            if not self.dep_status['venv']:
                self._create_venv()
                # _create_venv re-execs on success, so reaching here means it failed
                return False

            self.logger.info("Python packages missing. Installing from requirements.txt...")
            try:
                subprocess.check_call([
                    self.venv_python, "-m", "pip", "install", "-r", "requirements.txt"
                ])
                self.logger.ok("Python packages installed successfully from requirements.txt")
                # Re-exec so the fresh process can import newly installed packages
                self.logger.info("Restarting with installed packages...")
                os.execv(self.venv_python, [self.venv_python, *sys.argv])
                return True  # unreachable, but keeps the code path clear
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to install from requirements.txt: {e}")
                self._show_package_install_help()
                return False

        _init_third_party()
        return True

    def check_ffmpeg(self):
        """Check if ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True
            )
            self.dep_status['ffmpeg'] = True
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.dep_status['ffmpeg'] = False
            self._show_ffmpeg_install_help()
            return False

    def _create_venv(self):
        """Create a virtual environment, install packages, and re-exec."""
        venv_dir = Path('.venv')
        self.logger.info("No virtual environment detected. Creating .venv...")

        try:
            subprocess.check_call([sys.executable, '-m', 'venv', str(venv_dir)])
            self.logger.ok("Virtual environment created at .venv/")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to create virtual environment: {e}")
            return

        # Determine venv python path
        if IS_WINDOWS:
            venv_python = str(venv_dir / 'Scripts' / 'python.exe')
        else:
            venv_python = str(venv_dir / 'bin' / 'python')

        # Install packages
        self.logger.info("Installing packages from requirements.txt...")
        try:
            subprocess.check_call([
                venv_python, '-m', 'pip', 'install', '-r', 'requirements.txt'
            ])
            self.logger.ok("Packages installed successfully")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to install packages: {e}")
            return

        # Re-exec under venv python
        self.logger.info("Restarting with virtual environment...")
        os.execv(venv_python, [venv_python, *sys.argv])

    def _show_ffmpeg_install_help(self):
        """Show OS-specific ffmpeg installation instructions."""
        self.logger.error("\n=== FFmpeg Installation Required ===")

        if IS_MACOS:
            self.logger.error("Install via Homebrew:")
            self.logger.error("  brew install ffmpeg")
        elif IS_LINUX:
            self.logger.error("Install via package manager:")
            self.logger.error("  Ubuntu/Debian:  sudo apt-get install ffmpeg")
            self.logger.error("  Fedora/RHEL:    sudo dnf install ffmpeg")
            self.logger.error("  Arch:           sudo pacman -S ffmpeg")
        elif IS_WINDOWS:
            self.logger.error("Install options:")
            self.logger.error("  1. Chocolatey:  choco install ffmpeg")
            self.logger.error("  2. Download from: https://ffmpeg.org/download.html")
            self.logger.error("     Extract and add to PATH")

        self.logger.error("\nFFmpeg is a system dependency and cannot be auto-installed.")
        self.logger.error("Please install it manually and restart the tool.")

    def _show_package_install_help(self):
        """Show OS-specific Python package installation instructions."""
        self.logger.error("\n=== Python Package Installation Required ===")

        if IS_WINDOWS:
            self.logger.error("Create and activate virtual environment:")
            self.logger.error("  python3 -m venv .venv")
            self.logger.error("  .venv\\Scripts\\activate")
        else:  # Unix (macOS, Linux)
            self.logger.error("Create and activate virtual environment:")
            self.logger.error("  python3 -m venv .venv")
            self.logger.error("  source .venv/bin/activate")

    def get_status(self, config=None) -> DependencyCheckResult:
        """Return current dependency status as a result object."""
        packages = self.dep_status.get('packages', {})
        missing = [pkg for pkg, ok in packages.items() if not ok]
        playlists = len(config.playlists) if config else 0
        return DependencyCheckResult(
            venv_active=self.dep_status.get('venv', False),
            venv_path=self.venv_path,
            packages=packages,
            ffmpeg_available=self.dep_status.get('ffmpeg', False),
            all_ok=not missing and self.dep_status.get('ffmpeg', False),
            missing_packages=missing,
            playlists_loaded=playlists,
        )

    def check_all(self, require_ffmpeg=True, require_gamdl=True):
        """Check all dependencies."""
        all_ok = True

        # Check and install Python packages from requirements.txt
        if not self.check_python_packages():
            all_ok = False

        if require_ffmpeg and not self.check_ffmpeg():
            all_ok = False

        return all_ok


# ══════════════════════════════════════════════════════════════════
# Section 5: Tag Management Module
# ══════════════════════════════════════════════════════════════════









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
    tags = m4a.tags or {}

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

    # ── Phase 4: Cross-check sync DB against track DB ─────────────
    if sync_tracker:
        if cancel_event and cancel_event.is_set():
            logger.warn("Audit cancelled by user")
            return stats

        logger.info("=== Phase 3: Verifying sync records against track DB ===")
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
    else:
        logger.info("Phase 4: Skipped (no sync tracker)")

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

    return stats


def read_m4a_cover_art(input_file):
    """
    Read cover art data from an M4A file.
    Returns (cover_data: bytes, mime_type: str) or (None, None) if no art found.
    """
    from mutagen.mp4 import MP4, MP4Cover
    try:
        m4a = MP4(str(input_file))
        covers = m4a.tags.get(M4A_TAG_COVER)
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

    img.thumbnail((max_size, max_size), Image.LANCZOS)

    buf = io.BytesIO()
    if mime_type == APIC_MIME_PNG:
        img.save(buf, format="PNG")
    else:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=90)
        mime_type = APIC_MIME_JPEG

    return buf.getvalue(), mime_type








# ══════════════════════════════════════════════════════════════════
# Section 5b: Service Layer — Protocols, Results, Handlers, Renderers
# ══════════════════════════════════════════════════════════════════

# ── Protocols ─────────────────────────────────────────────────────

@runtime_checkable
class UserPromptHandler(Protocol):
    """Protocol for user interaction callbacks.

    Business logic classes accept an optional UserPromptHandler at
    construction. When no handler is provided, NonInteractivePromptHandler
    is used as a fail-safe default.
    """

    def confirm(self, message: str, default: bool = True) -> bool: ...

    def confirm_destructive(self, message: str) -> bool: ...

    def select_from_list(self, prompt: str, options: list[str],
                         allow_cancel: bool = True) -> int | None: ...

    def get_text_input(self, prompt: str,
                       default: str | None = None) -> str | None: ...

    def wait_for_continue(self, message: str,
                          timeout: float | None = None) -> None: ...


@runtime_checkable
class DisplayHandler(Protocol):
    """Protocol for progress and status display.

    Business logic classes accept an optional DisplayHandler at
    construction. When no handler is provided, NullDisplayHandler
    is used (silently discards all calls).
    """

    def show_progress(self, current: int, total: int,
                      message: str) -> None: ...

    def finish_progress(self) -> None: ...

    def show_status(self, message: str,
                    level: str = "info") -> None: ...

    def show_banner(self, title: str,
                    subtitle: str | None = None) -> None: ...


# ── Handler Implementations ───────────────────────────────────────

class NonInteractivePromptHandler:
    """Fail-safe defaults for non-interactive contexts (Web API, testing).

    confirm() returns the default, confirm_destructive() returns False,
    select_from_list() returns None, get_text_input() returns default,
    wait_for_continue() returns immediately.
    """

    def confirm(self, message: str, default: bool = True) -> bool:
        return default

    def confirm_destructive(self, message: str) -> bool:
        return False

    def select_from_list(self, prompt: str, options: list[str],
                         allow_cancel: bool = True) -> int | None:
        return None

    def get_text_input(self, prompt: str,
                       default: str | None = None) -> str | None:
        return default

    def wait_for_continue(self, message: str,
                          timeout: float | None = None) -> None:
        return


class NullDisplayHandler:
    """Silently discards all display calls.

    Used when no DisplayHandler is provided — operations still log
    to the Logger log file.
    """

    def show_progress(self, current: int, total: int,
                      message: str) -> None:
        pass

    def finish_progress(self) -> None:
        pass

    def show_status(self, message: str,
                    level: str = "info") -> None:
        pass

    def show_banner(self, title: str,
                    subtitle: str | None = None) -> None:
        pass




def _is_cancelled(event):
    """Check if a cancellation event has been signalled."""
    return event is not None and event.is_set()


class _DisplayProgress:
    """Adapter that maps ProgressBar .update()/.close() API to DisplayHandler.

    Business classes create this instead of ProgressBar directly, routing
    all progress display through the injected DisplayHandler.
    """

    def __init__(self, display_handler, total=0, desc="Processing"):
        self._handler = display_handler
        self._total = total
        self._desc = desc
        self._count = 0

    def set_total(self, total):
        """Lazily set the total when it becomes known (e.g. Downloader)."""
        self._total = total

    def update(self, n=1):
        """Advance the progress counter and notify the handler."""
        self._count += n
        self._handler.show_progress(self._count, self._total, self._desc)

    def close(self):
        """Signal progress completion."""
        self._handler.finish_progress()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# ── Result Dataclasses ────────────────────────────────────────────







@dataclass
class ConversionResult:
    """Result of Converter.convert()."""
    success: bool
    input_dir: str
    output_dir: str
    duration: float
    quality_preset: str
    quality_mode: str
    quality_value: str
    workers: int
    total_found: int
    converted: int
    overwritten: int
    skipped: int
    errors: int
    mp3_total: int = 0
    eq_effects: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DownloadResult:
    """Result of Downloader.download()."""
    success: bool
    key: str | None
    album_name: str | None
    duration: float
    playlist_total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncResult:
    """Result of SyncManager.sync_to_destination()."""
    success: bool
    source: str
    destination: str
    dest_key: str
    duration: float
    is_usb: bool = False
    files_found: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncStatusResult:
    """Result of SyncTracker.get_sync_status()."""
    sync_key: str
    last_sync_at: float
    playlists: list = field(default_factory=list)
    total_files: int = 0
    synced_files: int = 0
    new_files: int = 0
    new_playlists: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# Backwards compatibility aliases
USBSyncResult = SyncResult
USBSyncStatusResult = SyncStatusResult



@dataclass
class DeleteResult:
    """Result of DataManager.delete_playlist_data()."""
    success: bool
    playlist_key: str
    source_deleted: bool = False
    library_deleted: bool = False
    config_removed: bool = False
    files_deleted: int = 0
    bytes_freed: int = 0
    errors: list = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineResult:
    """Result of PipelineOrchestrator.run_full_pipeline()."""
    success: bool
    playlist_name: str | None
    playlist_key: str | None
    duration: float
    stages_completed: list = field(default_factory=list)
    stages_failed: list = field(default_factory=list)
    stages_skipped: list = field(default_factory=list)
    download_result: DownloadResult | None = None
    conversion_result: ConversionResult | None = None
    usb_result: USBSyncResult | None = None
    usb_destination: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class AggregateResult:
    """Result of PipelineOrchestrator batch processing."""
    success: bool
    duration: float
    total_playlists: int = 0
    successful_playlists: int = 0
    failed_playlists: int = 0
    playlist_results: list = field(default_factory=list)
    cumulative_stats: dict = field(default_factory=dict)
    usb_destination: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d['playlist_results'] = [
            r.to_dict() if hasattr(r, 'to_dict') else r
            for r in self.playlist_results
        ]
        return d


@dataclass
class DependencyCheckResult:
    """Result of DependencyChecker checks."""
    venv_active: bool
    venv_path: str | None
    packages: dict = field(default_factory=dict)
    ffmpeg_available: bool = False
    all_ok: bool = False
    missing_packages: list = field(default_factory=list)
    playlists_loaded: int = 0

    def to_dict(self) -> dict:
        return asdict(self)




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


class TagApplicator:
    """Applies profile-specific ID3 tags to clean library MP3s on-the-fly.

    Library MP3s contain only a TXXX:TrackUUID identifier.  This class
    reads track metadata from TrackDB and applies profile-driven tags
    (title, artist, album, genre, id3_extra, cover art) either:
    - As a streaming response (build_tagged_stream) for HTTP serving
    - As a file copy (apply_tags_to_file) for physical sync
    """

    # Mapping of ID3v2 frame ID prefixes to mutagen constructors.
    # Populated lazily on first use to avoid import at module level.
    _frame_constructors = None

    def __init__(self, track_db, project_root='.'):
        self.track_db = track_db
        self.project_root = Path(project_root)

    @classmethod
    def _get_frame_constructors(cls):
        """Lazy-init frame constructor mapping."""
        if cls._frame_constructors is None:
            from mutagen.id3 import COMM, TXXX
            cls._frame_constructors = {
                'TXXX': TXXX,
                'COMM': COMM,
            }
        return cls._frame_constructors

    def _resolve_template_vars(self, track_meta, playlist_name):
        """Build template variable dict from track metadata."""
        return {
            'title': track_meta.get('title', ''),
            'artist': track_meta.get('artist', ''),
            'album': track_meta.get('album', ''),
            'genre': track_meta.get('genre') or '',
            'track_number': str(track_meta.get('track_number') or ''),
            'track_total': str(track_meta.get('track_total') or ''),
            'disc_number': str(track_meta.get('disc_number') or ''),
            'disc_total': str(track_meta.get('disc_total') or ''),
            'year': track_meta.get('year') or '',
            'composer': track_meta.get('composer') or '',
            'album_artist': track_meta.get('album_artist') or '',
            'bpm': str(track_meta.get('bpm') or ''),
            'comment': track_meta.get('comment') or '',
            'compilation': '1' if track_meta.get('compilation') else '',
            'grouping': track_meta.get('grouping') or '',
            'lyrics': track_meta.get('lyrics') or '',
            'copyright': track_meta.get('copyright') or '',
            'playlist': playlist_name,
            'playlist_key': track_meta.get('playlist', ''),
        }

    def _build_id3_tags(self, track_meta, profile, playlist_name):
        """Build a mutagen ID3 tag object with profile-specific tags.

        Returns (tags, v2_version, include_v1) tuple.
        """
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TXXX

        tvars = self._resolve_template_vars(track_meta, playlist_name)

        tags = ID3()

        # Primary tag templates
        tags["TIT2"] = TIT2(encoding=3,
                            text=apply_template(profile.id3_title, **tvars))
        tags["TPE1"] = TPE1(encoding=3,
                            text=apply_template(profile.id3_artist, **tvars))
        tags["TALB"] = TALB(encoding=3,
                            text=apply_template(profile.id3_album, **tvars))

        # Genre tag (TCON) — only add if non-empty
        if profile.id3_genre:
            from mutagen.id3 import TCON
            tags["TCON"] = TCON(encoding=3,
                                text=apply_template(profile.id3_genre, **tvars))

        # Extra tags (arbitrary ID3 frames from profile)
        primary_frames = {'TIT2', 'TPE1', 'TALB', 'TCON'}
        for frame_id, value_template in profile.id3_extra.items():
            if frame_id in primary_frames:
                continue  # Primary fields take precedence
            value = apply_template(value_template, **tvars)
            if not value:
                continue  # Empty string = omit frame

            if frame_id.startswith('TXXX:'):
                desc = frame_id[5:]  # Strip "TXXX:" prefix
                tags.add(TXXX(encoding=3, desc=desc, text=[value]))
            elif frame_id == 'COMM':
                constructors = self._get_frame_constructors()
                tags.add(constructors['COMM'](
                    encoding=3, lang='eng', desc='', text=[value]))
            elif frame_id.startswith('T'):
                # Generic text frame (TCON, TPE2, TRCK, TDRC, etc.)
                from mutagen.id3 import Frames
                frame_cls = Frames.get(frame_id)
                if frame_cls:
                    tags[frame_id] = frame_cls(encoding=3, text=value)

        # Cover art
        cover_art_path = track_meta.get('cover_art_path')
        if cover_art_path and profile.artwork_size != -1:
            full_art_path = self.project_root / cover_art_path
            if full_art_path.exists():
                art_data = full_art_path.read_bytes()
                art_mime = (APIC_MIME_PNG if cover_art_path.endswith('.png')
                            else APIC_MIME_JPEG)
                if profile.artwork_size > 0:
                    art_data, art_mime = resize_cover_art_bytes(
                        art_data, profile.artwork_size, art_mime)
                tags.add(APIC(
                    encoding=3,
                    mime=art_mime,
                    type=APIC_TYPE_FRONT_COVER,
                    desc='Cover',
                    data=art_data,
                ))

        # Determine ID3 version settings from profile.id3_versions
        v2_version = 4  # default
        include_v1 = False
        for v in profile.id3_versions:
            if v == 'v2.3':
                v2_version = 3
            elif v == 'v2.4':
                v2_version = 4
            elif v == 'v1':
                include_v1 = True

        return tags, v2_version, include_v1

    def _find_audio_offset(self, mp3_path):
        """Find where audio data starts in an MP3 file (after ID3v2 header).

        Returns the byte offset of the first audio frame.
        """
        with open(mp3_path, 'rb') as f:
            header = f.read(10)
            if len(header) < 10 or header[:3] != b'ID3':
                return 0  # No ID3v2 header — audio starts at byte 0

            # ID3v2 size is stored as a 4-byte syncsafe integer (bytes 6-9)
            size_bytes = header[6:10]
            tag_size = (
                (size_bytes[0] << 21)
                | (size_bytes[1] << 14)
                | (size_bytes[2] << 7)
                | size_bytes[3]
            )
            # Total ID3v2 header = 10-byte header + tag_size
            ID3V2_HEADER_SIZE = 10
            return ID3V2_HEADER_SIZE + tag_size

    def build_tagged_stream(self, mp3_path, track_meta, profile,
                            playlist_name):
        """Build components for streaming a tagged MP3.

        Returns (id3_bytes, audio_offset, total_size):
        - id3_bytes: Complete ID3v2 tag block as bytes
        - audio_offset: Where audio data starts in the clean MP3
        - total_size: Total size of the tagged MP3 stream
        """
        import io

        tags, v2_version, _include_v1 = self._build_id3_tags(
            track_meta, profile, playlist_name)

        # Render the ID3v2 tag to bytes
        tag_buf = io.BytesIO()
        tags.save(tag_buf, v2_version=v2_version, v1=0)
        id3_bytes = tag_buf.getvalue()

        # Find where audio starts in the clean MP3
        audio_offset = self._find_audio_offset(mp3_path)

        # Total size = new tags + raw audio
        file_size = Path(mp3_path).stat().st_size
        audio_size = file_size - audio_offset
        total_size = len(id3_bytes) + audio_size

        return id3_bytes, audio_offset, total_size

    def apply_tags_to_file(self, mp3_path, track_meta, profile,
                           playlist_name, output_path):
        """Write a fully-tagged copy of the MP3 to output_path.

        Used during physical sync to create profile-specific copies.
        """
        tags, v2_version, include_v1 = self._build_id3_tags(
            track_meta, profile, playlist_name)

        audio_offset = self._find_audio_offset(mp3_path)

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        import io
        tag_buf = io.BytesIO()
        tags.save(tag_buf, v2_version=v2_version,
                  v1=1 if include_v1 else 0)
        tag_bytes = tag_buf.getvalue()

        with open(output_path, 'wb') as out:
            out.write(tag_bytes)
            with open(mp3_path, 'rb') as src:
                src.seek(audio_offset)
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)

    def build_output_filename(self, track_meta, profile, playlist_name):
        """Build destination filename using the profile's filename template."""
        tvars = self._resolve_template_vars(track_meta, playlist_name)
        name = apply_template(profile.filename, **tvars)
        return sanitize_filename(name) + '.mp3'

    def build_output_subdir(self, track_meta, profile, playlist_name):
        """Build destination subdirectory using the profile's directory template.

        Returns empty string for flat output.
        """
        if not profile.directory:
            return ''
        tvars = self._resolve_template_vars(track_meta, playlist_name)
        subdir = apply_template(profile.directory, **tvars)
        # Sanitize each path component
        parts = subdir.split('/')
        return '/'.join(sanitize_filename(p) for p in parts if p)


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

        from mutagen.id3 import ID3, TXXX, ID3NoHeaderError
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

            if existing_track and not force:
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

            # Generate UUID first — used for both filename and DB record
            track_uuid = _uuid.uuid4().hex
            output_filename = self._build_output_filename(track_uuid)
            output_file = self._build_output_path(output_path, output_filename)

            # If force re-converting, delete old file + DB entry
            if existing_track and force:
                old_path = Path(existing_track['file_path'])
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
                if self.track_db:
                    self.track_db.delete_track(existing_track['uuid'])

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



# ══════════════════════════════════════════════════════════════════
# Section 7: Download Module
# ══════════════════════════════════════════════════════════════════

class DownloadStatistics:
    """Tracks download operation statistics."""

    def __init__(self):
        self.playlist_total = 0      # Total tracks in playlist
        self.downloaded = 0          # Newly downloaded tracks
        self.skipped = 0             # Already existed
        self.failed = 0              # Failed downloads


class Downloader:
    """Manages downloads from Apple Music using gamdl."""

    def __init__(self, logger=None, venv_python=None, cookie_path=DEFAULT_COOKIES,
                 prompt_handler=None, display_handler=None, cancel_event=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.venv_python = venv_python or sys.executable
        self.cookie_manager = CookieManager(cookie_path, logger=self.logger,
                                            prompt_handler=self.prompt_handler)

    def extract_url_info(self, url):
        """
        Extract key and album name from Apple Music URL.
        Converts 'pop-workout' → ('Pop_Workout', 'Pop Workout')
        """
        import re

        # Extract the playlist name from URL
        match = re.search(r'/playlist/([^/]+)/', url)
        if not match:
            return None, None

        raw_name = match.group(1)

        # Convert to key format: pop-workout → Pop_Workout
        words = raw_name.split('-')
        key = '_'.join(word.capitalize() for word in words)

        # Convert to album name format: pop-workout → Pop Workout
        album_name = ' '.join(word.capitalize() for word in words)

        return key, album_name

    def _clean_line(self, line):
        """Remove carriage returns and clean up gamdl output."""
        return line.replace('\r', '').strip()

    def _count_m4a_files(self, directory):
        """Count M4A files in directory (non-hidden files only)."""
        if not os.path.exists(directory):
            return 0

        path = Path(directory)
        m4a_files = [
            f for f in path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]
        return len(m4a_files)

    def download(self, url, output_dir, key=None, confirm=True, dry_run=False,
                 validate_cookies=True, auto_refresh=False):
        """
        Download playlist from Apple Music using gamdl.
        Returns DownloadResult.
        """
        import re

        # Extract info from URL if key not provided
        if not key:
            key, album_name = self.extract_url_info(url)
            if not key:
                self.logger.error(f"Could not extract playlist info from URL: {url}")
                return DownloadResult(success=False, key=None, album_name=None, duration=0)
        else:
            _, album_name = self.extract_url_info(url)

        output_path = Path(output_dir)
        start_time = time.time()

        self.logger.info(f"Downloading playlist: {key}")
        self.logger.info(f"  Album name: {album_name}")
        self.logger.info(f"  Output: {output_path}")

        # Validate cookies before download
        if validate_cookies and not dry_run:
            status = self.cookie_manager.validate()

            if status.valid:
                self.logger.ok(status.reason)
            else:
                self.logger.error(status.reason)

                # Try auto-refresh if requested
                if auto_refresh:
                    if self.cookie_manager.auto_refresh():
                        # Refresh succeeded, re-validate
                        status = self.cookie_manager.validate()
                        if status.valid:
                            self.logger.ok("Cookie refresh successful, continuing with download")
                        else:
                            self.logger.error("Cookies still invalid after refresh")
                            self.cookie_manager.show_manual_instructions()
                            return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                    else:
                        self.logger.error("Automatic cookie refresh failed")
                        self.cookie_manager.show_manual_instructions()
                        return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                else:
                    self.cookie_manager.show_manual_instructions()

                    # In interactive mode, offer auto-refresh first
                    if confirm:
                        if self.prompt_handler.confirm("Attempt automatic cookie refresh?", default=True):
                            # User wants to try auto-refresh
                            if self.cookie_manager.auto_refresh():
                                # Refresh succeeded, re-validate
                                status = self.cookie_manager.validate()
                                if status.valid:
                                    self.logger.ok("Cookie refresh successful, continuing with download")
                                else:
                                    self.logger.error("Cookies still invalid after refresh")
                                    return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                            else:
                                self.logger.error("Automatic cookie refresh failed")
                                # Ask if they want to continue anyway
                                if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                    self.logger.info("Aborted")
                                    return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                        else:
                            # User declined auto-refresh, ask if they want to continue
                            if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                self.logger.info("Aborted")
                                return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                    else:
                        # In auto/non-interactive mode, fail immediately
                        self.logger.error("Cannot continue without valid cookies")
                        return DownloadResult(success=False, key=key, album_name=album_name, duration=0)

        # Confirmation prompt (unless auto mode)
        if confirm:
            if not self.prompt_handler.confirm(f"Download {key}?", default=False):
                self.logger.info(f"Skipping download for {key}")
                return DownloadResult(success=False, key=key, album_name=album_name, duration=0)

        if dry_run:
            self.logger.dry_run(f"Would download: {url}")
            self.logger.dry_run(f"  → Output: {output_path}")
            return DownloadResult(success=True, key=key, album_name=album_name, duration=0)

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Run gamdl
        self.logger.info("Starting download from Apple Music...")
        if url:
            url_display = url[:80] + "..." if len(url) > 80 else url
            self.logger.info(f"URL: {url_display}")

        gamdl_data = Path(DEFAULT_DATA_DIR) / "gamdl"
        gamdl_data.mkdir(parents=True, exist_ok=True)
        temp_path = gamdl_data / "temp"
        temp_path.mkdir(exist_ok=True)
        config_path = gamdl_data / "config.json"

        cmd = [
            self.venv_python, "-m", "gamdl",
            "--log-level", "INFO",  # Show download progress, suppress DEBUG
            "--cookies-path", str(self.cookie_manager.cookie_path),
            "--config-path", str(config_path),
            "--temp-path", str(temp_path),
            "-o", str(output_path) + "/",
            url
        ]

        stats = DownloadStatistics()

        # Count files BEFORE download
        files_before = self._count_m4a_files(output_path)

        try:
            self.logger.info(f"Running: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Parse output line by line
            progress = _DisplayProgress(
                self.display_handler, total=0, desc="Downloading",
            )
            verbose = self.logger.verbose
            unrecognized_lines = []

            try:
                for line in process.stdout:
                    if _is_cancelled(self.cancel_event):
                        process.terminate()
                        self.logger.warn("Download cancelled by user")
                        break
                    # Clean carriage returns to prevent screen scrolling
                    cleaned = self._clean_line(line)

                    # Skip empty lines
                    if not cleaned:
                        continue

                    # Filter out download progress bars (still noisy)
                    if cleaned.startswith('[download]'):
                        continue

                    try:
                        # Extract total track count
                        if '[Track' in cleaned and '/' in cleaned:
                            match = re.search(r'\[Track (\d+)/(\d+)\]', cleaned)
                            if match:
                                _current_track = int(match.group(1))
                                total_tracks = int(match.group(2))
                                if stats.playlist_total == 0:
                                    stats.playlist_total = total_tracks
                                    progress.set_total(total_tracks)

                        # Track downloads and show real-time feedback
                        # Note: gamdl emits "Downloading" for EVERY track (even skips),
                        # so we advance the bar here (exactly once per track).
                        if '[INFO' in cleaned and 'Downloading "' in cleaned:
                            # Extract track name
                            match = re.search(r'Downloading "([^"]+)"', cleaned)
                            if match:
                                track_name = match.group(1)
                                msg = f"Downloading: {track_name}"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)
                                progress.update(1)

                        # Track skips and show feedback
                        # Don't update progress here — already counted on the
                        # "Downloading" line that gamdl emits before the skip.
                        elif '[WARNING' in cleaned and 'Skipping "' in cleaned and 'Media file already exists' in cleaned:
                            # Extract track name
                            match = re.search(r'Skipping "([^"]+)"', cleaned)
                            if match:
                                track_name = match.group(1)
                                msg = f"Skipping (already exists): {track_name}"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)

                        # Track errors
                        elif 'Finished with' in cleaned and 'error' in cleaned:
                            error_match = re.search(r'Finished with (\d+) error', cleaned)
                            if error_match:
                                stats.failed = int(error_match.group(1))

                        # Collect unrecognized output
                        else:
                            unrecognized_lines.append(cleaned)
                            if '[ERROR' in cleaned or '[CRITICAL' in cleaned:
                                self.logger.error(f"gamdl: {cleaned}")
                            else:
                                self.logger.file_info(f"gamdl: {cleaned}")

                    except Exception as parse_error:
                        # If parsing fails for a line, log and continue without crashing
                        self.logger.file_info(f"Output parse error: {parse_error}")
            finally:
                progress.close()

            process.wait()

            # Count files AFTER download
            files_after = self._count_m4a_files(output_path)

            # Calculate accurate statistics from filesystem
            stats.downloaded = files_after - files_before  # New files
            stats.skipped = files_before  # Existing files

            duration = time.time() - start_time
            if process.returncode == 0:
                self.logger.ok(f"Download complete: {key}")
                return DownloadResult(
                    success=True, key=key, album_name=album_name,
                    duration=duration, playlist_total=stats.playlist_total,
                    downloaded=stats.downloaded, skipped=stats.skipped,
                    failed=stats.failed)
            else:
                self.logger.error(f"Download failed with exit code {process.returncode}")
                if unrecognized_lines:
                    tail = unrecognized_lines[-10:]
                    self.logger.error("gamdl output:")
                    for err_line in tail:
                        self.logger.error(f"  {err_line}")
                return DownloadResult(
                    success=False, key=key, album_name=album_name,
                    duration=duration, playlist_total=stats.playlist_total,
                    downloaded=stats.downloaded, skipped=stats.skipped,
                    failed=stats.failed)

        except Exception as e:
            self.logger.error(f"Failed to download {key}: {e}")
            duration = time.time() - start_time
            return DownloadResult(
                success=False, key=key, album_name=album_name,
                duration=duration, playlist_total=stats.playlist_total,
                downloaded=stats.downloaded, skipped=stats.skipped,
                failed=stats.failed)


# ══════════════════════════════════════════════════════════════════
# Section 7.5: Cookie Management Module
# ══════════════════════════════════════════════════════════════════

class CookieStatus:
    """Cookie validation result."""
    def __init__(self):
        self.valid = False
        self.exists = False
        self.has_required_cookie = False
        self.expiration_timestamp = None
        self.expiration_date = None
        self.days_until_expiration = None
        self.reason = ""  # Human-readable message


class CookieManager:
    """Manages Apple Music cookie validation and refresh."""

    def __init__(self, cookie_path=DEFAULT_COOKIES, logger=None, prompt_handler=None,
                 audit_logger=None, audit_source='cli'):
        self.cookie_path = Path(cookie_path)
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self.required_domain = '.music.apple.com'
        self.required_cookie_name = 'media-user-token'

    def validate(self):
        """Validate cookies.txt and check expiration.

        Returns:
            CookieStatus: Validation result with detailed information
        """
        import http.cookiejar
        from datetime import datetime

        status = CookieStatus()

        # Check if file exists
        if not self.cookie_path.exists():
            status.reason = f"Cookie file not found: {self.cookie_path}"
            return status

        status.exists = True

        try:
            # Load cookies using MozillaCookieJar (Netscape format)
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)

            # Find the required cookie
            target_cookie = None
            for cookie in cookie_jar:
                if (cookie.domain == self.required_domain and
                    cookie.name == self.required_cookie_name):
                    target_cookie = cookie
                    break

            if not target_cookie:
                status.reason = f"Required cookie '{self.required_cookie_name}' not found for domain '{self.required_domain}'"
                return status

            status.has_required_cookie = True

            # Check expiration
            if target_cookie.expires is None:
                # Session cookie - no expiration
                status.valid = True
                status.reason = "Cookie is valid (session cookie, no expiration)"
                return status

            status.expiration_timestamp = target_cookie.expires
            status.expiration_date = datetime.fromtimestamp(target_cookie.expires, tz=UTC)

            # Compare with current time
            now = datetime.now(UTC)
            time_diff = status.expiration_date - now
            status.days_until_expiration = time_diff.total_seconds() / 86400

            if time_diff.total_seconds() > 0:
                # Cookie is valid
                status.valid = True
                days = int(status.days_until_expiration)
                date_str = status.expiration_date.strftime('%Y-%m-%d')
                status.reason = f"Cookies valid until {date_str} ({days} days remaining)"
            else:
                # Cookie expired
                days_ago = int(-status.days_until_expiration)
                date_str = status.expiration_date.strftime('%Y-%m-%d')
                status.reason = f"Cookies expired on {date_str} ({days_ago} days ago)"

            return status

        except Exception as e:
            status.reason = f"Failed to validate cookies: {e}"
            return status

    def show_manual_instructions(self):
        """Display step-by-step manual cookie refresh guide."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("Apple Music Cookie Refresh Required")
        self.logger.info("=" * 60)
        self.logger.info("\nYour Apple Music authentication has expired. Follow these steps:\n")
        self.logger.info("1. Open Chrome/Firefox and go to: https://music.apple.com")
        self.logger.info("2. Log in to your Apple Music account")
        self.logger.info("3. Install browser extension:")
        self.logger.info("   - Chrome: 'Get cookies.txt LOCALLY' extension")
        self.logger.info("   - Firefox: 'cookies.txt' extension")
        self.logger.info("4. Click extension icon → Export cookies.txt")
        self.logger.info(f"5. Save as: {self.cookie_path.absolute()}")
        self.logger.info("6. Re-run this command\n")
        self.logger.info("Alternative: Try automatic refresh with --auto-refresh-cookies flag")
        self.logger.info("(opens browser automatically, no password prompts required)")
        self.logger.info("=" * 60 + "\n")

    def _detect_default_browser(self):
        """
        Detect the OS default browser.
        Returns browser name: 'chrome', 'firefox', 'safari', 'edge', or None
        """

        try:
            if IS_MACOS:
                # macOS: Use LaunchServices to get default browser
                result = subprocess.run(
                    ['defaults', 'read', 'com.apple.LaunchServices/com.apple.launchservices.secure', 'LSHandlers'],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()

                # Check for browser identifiers in output
                if 'chrome' in output or 'google' in output:
                    return 'chrome'
                elif 'firefox' in output:
                    return 'firefox'
                elif 'safari' in output or 'webkit' in output:
                    return 'safari'
                elif 'edge' in output or 'msedge' in output:
                    return 'edge'

            elif IS_LINUX:
                # Linux: Check xdg-settings
                result = subprocess.run(
                    ['xdg-settings', 'get', 'default-web-browser'],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()

                if 'chrome' in output or 'chromium' in output:
                    return 'chrome'
                elif 'firefox' in output:
                    return 'firefox'
                elif 'edge' in output:
                    return 'edge'

            elif IS_WINDOWS:
                # Windows: Check registry
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice')
                    prog_id = winreg.QueryValueEx(key, 'ProgId')[0].lower()
                    winreg.CloseKey(key)

                    if 'chrome' in prog_id:
                        return 'chrome'
                    elif 'firefox' in prog_id:
                        return 'firefox'
                    elif 'edge' in prog_id or 'msedge' in prog_id:
                        return 'edge'
                except Exception:
                    pass

        except Exception as e:
            self.logger.info(f"Could not detect default browser: {e}")

        return None

    def _detect_installed_browsers(self):
        """
        Detect which browsers are installed on the system.
        Returns list of browser names: ['chrome', 'firefox', 'safari', 'edge']
        """

        browsers = []

        if IS_MACOS:
            # Check for browser apps in /Applications
            browser_paths = {
                'chrome': '/Applications/Google Chrome.app',
                'firefox': '/Applications/Firefox.app',
                'safari': '/Applications/Safari.app',
                'edge': '/Applications/Microsoft Edge.app'
            }

            for name, path in browser_paths.items():
                if Path(path).exists():
                    browsers.append(name)

        elif IS_LINUX:
            # Check for browser binaries
            browser_cmds = ['google-chrome', 'chromium', 'firefox', 'microsoft-edge']

            for cmd in browser_cmds:
                if shutil.which(cmd):
                    if 'chrome' in cmd or 'chromium' in cmd:
                        if 'chrome' not in browsers:
                            browsers.append('chrome')
                    elif 'firefox' in cmd:
                        browsers.append('firefox')
                    elif 'edge' in cmd:
                        browsers.append('edge')

        elif IS_WINDOWS:
            # Check for browser executables
            browser_paths = {
                'chrome': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'firefox': r'C:\Program Files\Mozilla Firefox\firefox.exe',
                'edge': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
            }

            for name, path in browser_paths.items():
                if Path(path).exists():
                    browsers.append(name)

        return browsers

    def _prompt_browser_selection(self, available_browsers, default_browser):
        """
        Prompt user to select which browser to use.
        Returns list of browsers to try (in order), or None if cancelled.
        """
        if len(available_browsers) == 1:
            # Only one browser available, use it automatically
            return available_browsers

        # Build options: each browser + "Try all browsers"
        options = [
            f"{b.capitalize()}{' (default)' if b == default_browser else ''}"
            for b in available_browsers
        ]
        options.append("Try all browsers")

        selection = self.prompt_handler.select_from_list(
            "Select browser for cookie extraction", options, allow_cancel=True)

        if selection is None:
            return None

        # Last option = "Try all browsers"
        if selection == len(available_browsers):
            self.logger.info("Will try all browsers if needed")
            return available_browsers

        selected = available_browsers[selection]
        self.logger.info(f"Using: {selected.capitalize()}")
        return [selected]

    def _extract_with_selenium(self, browser=None):
        """
        Extract cookies using Selenium WebDriver.
        Tries default browser first, then falls back to others.
        browser: None = interactive prompt, 'auto' = try all detected,
                 'chrome'/'firefox'/'safari'/'edge' = specific browser.
        Returns cookie_jar on success, None on failure.
        """


        # Detect browsers
        default_browser = self._detect_default_browser()
        installed_browsers = self._detect_installed_browsers()

        # Build priority list: default first, then others
        browser_priority = []
        if default_browser and default_browser in installed_browsers:
            browser_priority.append(default_browser)
            self.logger.info(f"Detected default browser: {default_browser.capitalize()}")

        for b in installed_browsers:
            if b not in browser_priority:
                browser_priority.append(b)

        if not browser_priority:
            self.logger.error("No supported browsers found (Chrome, Firefox, Safari, or Edge)")
            return None

        # Determine which browsers to try
        interactive = browser is None
        if browser is None:
            # CLI interactive mode — prompt user
            selected_browsers = self._prompt_browser_selection(browser_priority, default_browser)
            if not selected_browsers:
                self.logger.info("Browser selection cancelled")
                return None
        elif browser == 'auto':
            # Non-interactive: try all detected browsers
            selected_browsers = browser_priority
            self.logger.info(f"Auto mode: will try {', '.join(b.capitalize() for b in selected_browsers)}")
        else:
            # Non-interactive: specific browser requested
            if browser not in installed_browsers:
                self.logger.error(f"Browser '{browser}' is not installed or not supported")
                return None
            selected_browsers = [browser]
            self.logger.info(f"Using specified browser: {browser.capitalize()}")

        # Try each selected browser
        # Non-interactive mode launches visible so the user can log in if needed
        headless = interactive  # CLI tries headless first; web UI goes visible
        for browser_name in selected_browsers:
            self.logger.info(f"Attempting to use {browser_name.capitalize()}...")

            try:
                driver = self._launch_browser(browser_name, headless=headless)
                if driver:
                    cookies = self._extract_cookies_from_driver(
                        driver, browser_name, interactive=interactive)
                    if cookies:
                        return cookies

            except Exception as e:
                self.logger.info(f"{browser_name.capitalize()} failed: {e}")
                continue

        self.logger.error("All browsers failed. Please ensure browser is up to date.")
        return None

    def _find_cached_driver(self, driver_name):
        """Search webdriver-manager cache for a previously downloaded driver binary.

        Returns the path to the most recent cached binary, or None.
        """
        wdm_dir = Path.home() / '.wdm' / 'drivers' / driver_name
        if not wdm_dir.exists():
            return None

        # Find all driver binaries (exclude .zip files)
        binary_name = driver_name + '.exe' if IS_WINDOWS else driver_name
        matches = sorted(
            [p for p in wdm_dir.rglob(binary_name) if p.is_file() and p.suffix != '.zip'],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            self.logger.info(f"Found cached driver: {matches[0]}")
            return str(matches[0])
        return None

    def _launch_browser(self, browser_name, headless=True):
        """Launch browser with Selenium. Returns driver or None."""

        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.edge.service import Service as EdgeService
        from selenium.webdriver.firefox.service import Service as FirefoxService

        try:
            # Try to import webdriver-manager
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.firefox import GeckoDriverManager
                from webdriver_manager.microsoft import EdgeChromiumDriverManager
                use_manager = True
            except ImportError:
                self.logger.info("webdriver-manager not installed, using system drivers")
                use_manager = False

            driver = None

            def _try_with_fallbacks(manager_fn, cached_fn, direct_fn):
                """Try webdriver-manager → cached driver → system driver."""
                if use_manager:
                    try:
                        return manager_fn()
                    except Exception as mgr_err:
                        self.logger.info(f"webdriver-manager failed ({mgr_err}), trying cached driver")
                # Try cached driver from previous webdriver-manager run
                try:
                    result = cached_fn()
                    if result:
                        return result
                except Exception:
                    pass
                self.logger.info("No cached driver found, trying system driver")
                return direct_fn()

            if browser_name == 'chrome':
                from selenium.webdriver.chrome.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")

                def _cached_chrome():
                    path = self._find_cached_driver('chromedriver')
                    if path:
                        return webdriver.Chrome(service=ChromeService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options),
                    _cached_chrome,
                    lambda: webdriver.Chrome(options=options),
                )

            elif browser_name == 'firefox':
                from selenium.webdriver.firefox.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless")

                def _cached_firefox():
                    path = self._find_cached_driver('geckodriver')
                    if path:
                        return webdriver.Firefox(service=FirefoxService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options),
                    _cached_firefox,
                    lambda: webdriver.Firefox(options=options),
                )

            elif browser_name == 'edge':
                from selenium.webdriver.edge.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

                def _cached_edge():
                    path = self._find_cached_driver('msedgedriver')
                    if path:
                        return webdriver.Edge(service=EdgeService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options),
                    _cached_edge,
                    lambda: webdriver.Edge(options=options),
                )

            elif browser_name == 'safari':
                # Safari doesn't support headless mode and doesn't need webdriver-manager
                if headless:
                    self.logger.info("Safari doesn't support headless mode, launching visible browser")
                driver = webdriver.Safari()

            return driver

        except WebDriverException as e:
            self.logger.info(f"Failed to launch {browser_name}: {e}")
            return None
        except Exception as e:
            self.logger.info(f"Unexpected error launching {browser_name}: {e}")
            return None

    def _extract_cookies_from_driver(self, driver, browser_name, interactive=True):
        """Extract cookies from Selenium driver. Returns cookie_jar or None.

        interactive: True = prompt via prompt_handler after login (CLI mode),
                     False = poll for login automatically (web UI mode).
        """
        import http.cookiejar
        import time


        LOGIN_POLL_INTERVAL = 3   # seconds between login checks
        LOGIN_TIMEOUT = 300       # 5 minutes max wait

        try:
            # Navigate to Apple Music
            self.logger.info("Navigating to music.apple.com...")
            driver.get("https://music.apple.com")
            time.sleep(3)  # Wait for page load

            # Check if logged in
            is_logged_in = self._check_login_status(driver)

            if not is_logged_in:
                self.logger.warn("Not logged in to Apple Music")

                if interactive:
                    # CLI mode: quit headless, relaunch visible, wait for user
                    driver.quit()
                    self.logger.info(f"Launching visible {browser_name.capitalize()} for login...")
                    driver = self._launch_browser(browser_name, headless=False)
                    if not driver:
                        return None

                    driver.get("https://music.apple.com")

                    self.logger.info("\n" + "=" * 60)
                    self.logger.info("Please log in to Apple Music")
                    self.logger.info("=" * 60)
                    self.logger.info(f"1. A {browser_name.capitalize()} window has opened")
                    self.logger.info("2. Log in to your Apple Music account")
                    self.logger.info("3. Once logged in, press Enter here to continue")
                    self.logger.info("=" * 60 + "\n")

                    self.prompt_handler.wait_for_continue("Press Enter after logging in...")
                    time.sleep(2)  # Let cookies settle
                else:
                    # Web UI mode: browser is already visible, poll for login
                    self.logger.info("=" * 60)
                    self.logger.info("Please log in to Apple Music in the browser window")
                    self.logger.info(f"Waiting up to {LOGIN_TIMEOUT // 60} minutes...")
                    self.logger.info("=" * 60)

                    elapsed = 0
                    while elapsed < LOGIN_TIMEOUT:
                        time.sleep(LOGIN_POLL_INTERVAL)
                        elapsed += LOGIN_POLL_INTERVAL
                        if self._check_login_status(driver):
                            self.logger.ok("Login detected!")
                            time.sleep(2)  # Let cookies settle
                            break
                    else:
                        self.logger.error("Login timed out. Please try again.")
                        driver.quit()
                        return None

            # Extract cookies
            selenium_cookies = driver.get_cookies()
            self.logger.info(f"Extracted {len(selenium_cookies)} cookies from {browser_name.capitalize()}")

            # Convert to http.cookiejar format
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            target_cookie_found = False

            for sc in selenium_cookies:
                # Only process cookies for music.apple.com domain
                domain = sc.get('domain', '')
                if 'music.apple.com' not in domain:
                    continue

                # Create http.cookiejar.Cookie object
                cookie = http.cookiejar.Cookie(
                    version=0,
                    name=sc['name'],
                    value=sc['value'],
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=True,
                    domain_initial_dot=domain.startswith('.'),
                    path=sc.get('path', '/'),
                    path_specified=True,
                    secure=sc.get('secure', False),
                    expires=sc.get('expiry'),  # Unix timestamp or None
                    discard=False,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False
                )
                cookie_jar.set_cookie(cookie)

                if sc['name'] == self.required_cookie_name:
                    target_cookie_found = True

            driver.quit()

            if not target_cookie_found:
                self.logger.error(f"Cookie '{self.required_cookie_name}' not found after extraction")
                return None

            music_cookies = [c for c in cookie_jar if 'music.apple.com' in c.domain]
            self.logger.ok(f"Successfully extracted {len(music_cookies)} Apple Music cookies")
            return cookie_jar

        except Exception as e:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.logger.error(f"Cookie extraction failed: {e}")
            return None

    def _check_login_status(self, driver):
        """Check if user is logged in to Apple Music. Returns True if logged in."""
        from selenium.webdriver.common.by import By

        try:
            # Strategy: Look for sign-in button. If found, user is NOT logged in.
            # This is more reliable than looking for profile elements which vary
            sign_in_buttons = driver.find_elements(By.XPATH,
                "//a[contains(@href, 'signin') or contains(@href, 'sign-in') or contains(text(), 'Sign In')]")

            if sign_in_buttons:
                return False  # Sign-in button found = not logged in

            # Additional check: Look for account/profile indicators
            account_indicators = driver.find_elements(By.XPATH,
                "//button[contains(@aria-label, 'Account') or contains(@aria-label, 'account')]")

            if account_indicators:
                return True  # Account button found = logged in

            # Default: assume not logged in to be safe
            return False

        except Exception as e:
            self.logger.info(f"Login check uncertain: {e}")
            return False  # Assume not logged in on error

    def auto_refresh(self, backup=True, browser=None):
        """
        Automatically refresh cookies using Selenium.
        Creates backup before overwriting if backup=True.
        browser: None = interactive prompt (CLI), 'auto' = try all browsers,
                 'chrome'/'firefox'/'safari'/'edge' = specific browser.
        Returns True if successful, False otherwise.
        """
        self.logger.info("Attempting automatic cookie refresh...")

        # Extract cookies using Selenium
        cookie_jar = self._extract_with_selenium(browser=browser)

        if not cookie_jar:
            self.logger.error("Automatic cookie refresh failed")
            if self.audit_logger:
                self.audit_logger.log(
                    'cookie_refresh', 'Cookie auto-refresh failed',
                    'failed', source=self._audit_source)
            return False

        # Create backup if requested and file exists
        if backup and self.cookie_path.exists():
            backup_path = Path(str(self.cookie_path) + '.backup')
            shutil.copy2(self.cookie_path, backup_path)
            self.logger.ok(f"Backup created: {backup_path}")

        # Save cookies in Netscape format
        try:
            cookie_jar.save(ignore_discard=True, ignore_expires=False)
            self.logger.ok(f"Cookies saved to {self.cookie_path}")

            # Validate the new cookies
            status = self.validate()
            if status.valid:
                self.logger.ok(status.reason)
                if self.audit_logger:
                    self.audit_logger.log(
                        'cookie_refresh', 'Cookie auto-refresh succeeded',
                        'completed', source=self._audit_source)
                return True
            else:
                self.logger.error(f"Saved cookies are not valid: {status.reason}")
                if self.audit_logger:
                    self.audit_logger.log(
                        'cookie_refresh', 'Cookie refresh: saved cookies invalid',
                        'failed', source=self._audit_source)
                return False

        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")
            if self.audit_logger:
                self.audit_logger.log(
                    'cookie_refresh', f'Cookie refresh error: {e}',
                    'failed', source=self._audit_source)
            return False

    def clean_cookies(self):
        """Remove non-Apple cookies from cookies.txt file.

        Filters the cookie file to only retain cookies whose domain
        contains 'apple.com'. Creates a backup before modifying.

        Returns:
            tuple: (success: bool, kept: int, removed: int)
        """
        if not self.cookie_path.exists():
            return (False, 0, 0)

        try:
            import http.cookiejar
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)

            all_cookies = list(cookie_jar)
            apple_cookies = [c for c in all_cookies if APPLE_COOKIE_DOMAIN in c.domain]
            removed_count = len(all_cookies) - len(apple_cookies)

            if removed_count == 0:
                return (True, len(apple_cookies), 0)

            # Create backup before modifying
            backup_path = Path(str(self.cookie_path) + '.backup')
            shutil.copy2(self.cookie_path, backup_path)

            # Clear and re-add only Apple cookies
            cookie_jar.clear()
            for cookie in apple_cookies:
                cookie_jar.set_cookie(cookie)

            cookie_jar.save(ignore_discard=True, ignore_expires=False)
            return (True, len(apple_cookies), removed_count)

        except Exception as e:
            self.logger.error(f"Cookie cleanup failed: {e}")
            return (False, 0, 0)


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

    def select_destination(self, config=None, output_profile=None):
        """Interactive destination picker showing USB drives, saved destinations, and custom path.

        Returns SyncDestination or None if cancelled.
        """
        options = []
        option_dests = []  # Parallel list: SyncDestination or None (for custom)

        # 1. Auto-detected USB drives
        usb_drives = self.find_usb_drives()
        usb_dir = output_profile.usb_dir if output_profile else DEFAULT_USB_DIR
        saved_names = {d.name.lower() for d in config.destinations} if config else set()
        for vol in usb_drives:
            base = self._get_usb_base_path(vol)
            full_path = str(base / usb_dir) if usb_dir else str(base)
            # Skip if already saved as a destination
            if vol.lower() in saved_names:
                continue
            options.append(f"[USB] {vol} ({full_path})")
            option_dests.append(
                SyncDestination(vol, f'usb://{full_path}'))

        # 2. Saved destinations from config
        if config and config.destinations:
            for dest in config.destinations:
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
            dest_key = self._sanitize_dest_name(p.name)
            dest = SyncDestination(dest_key, f'folder://{custom_path}')
            if config and not config.get_destination(dest_key):
                config.add_destination(dest_key, dest.path)
            return dest

        # Auto-save USB selections
        if dest.is_usb and config and not config.get_destination(dest.name):
            config.add_destination(dest.name, dest.path)

        return dest

    @staticmethod
    def _sanitize_dest_name(name):
        """Sanitize a directory name into a valid destination name (alphanumeric, hyphens, underscores)."""
        import re as _re
        sanitized = _re.sub(r'[^a-zA-Z0-9_-]', '-', name)
        sanitized = _re.sub(r'-+', '-', sanitized).strip('-')
        return sanitized or 'custom-dest'

    def sync_to_destination(self, source_dir, dest_path, dest_key,
                            dry_run=False, tag_applicator=None,
                            profile=None, playlist_name=None):
        """Sync files to any destination with incremental copy logic.

        Args:
            source_dir: Source directory containing MP3 files
            dest_path: Schemed path (usb:// or folder://) or raw filesystem path
            dest_key: Tracking key name (destination name)
            dry_run: Preview changes without copying
            tag_applicator: Optional TagApplicator for profile-based tagging
            profile: Optional OutputProfile (required if tag_applicator is set)
            playlist_name: Display name of playlist (for template variables)

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
                              destination='', dest_key=dest_key or '',
                              duration=0, is_usb=is_usb)

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
                dest_key=dest_key, duration=duration, is_usb=is_usb,
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
                dest_key=dest_key, duration=duration, is_usb=is_usb,
                files_found=stats.files_found, files_copied=stats.files_copied,
                files_skipped=stats.files_skipped,
                files_failed=stats.files_failed)

        # Copy files with incremental check
        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files),
            desc="Syncing files",
        )

        try:
            for src_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Sync cancelled by user")
                    break
                try:
                    track_meta = track_metas[src_file]
                    dst_file = dest_path_map[src_file]

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
                                dest_key, pl_name, record_name)
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
        duration = time.time() - start_time

        # Prompt to eject USB drive (only for USB destinations)
        if is_usb and not dry_run:
            self._prompt_and_eject_usb(dest_key)

        return SyncResult(
            success=stats.files_failed == 0, source=str(source_path),
            destination=str(dest), dest_key=dest_key, duration=duration,
            is_usb=is_usb, files_found=stats.files_found,
            files_copied=stats.files_copied,
            files_skipped=stats.files_skipped,
            files_failed=stats.files_failed)

    def sync_to_usb(self, source_dir, usb_dir=DEFAULT_USB_DIR, dry_run=False, volume=None):
        """Backwards-compatible wrapper: sync files to a USB drive."""
        if volume is None:
            volume = self.select_usb_drive()
        if not volume:
            return SyncResult(success=False, source=str(source_dir),
                              destination='', dest_key='', duration=0, is_usb=True)

        base_path = str(self._get_usb_base_path(volume))
        full_path = str(Path(base_path) / usb_dir) if usb_dir else base_path
        return self.sync_to_destination(
            source_dir, dest_path=f'usb://{full_path}', dest_key=volume,
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

        # Get per-playlist MP3 counts from TrackDB
        db_counts = {}
        if track_db:
            for ps in track_db.get_playlist_stats():
                db_counts[ps['playlist']] = ps['track_count']

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

                # Use DB count if available, otherwise 0
                exported_count = db_counts.get(playlist_name, 0)
                unconverted_count = max(0, m4a_count - exported_count)

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
                 audit_logger=None, audit_source='cli', track_db=None):
        self.logger = logger or Logger()
        self.config = config or ConfigManager(logger=self.logger)
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self.track_db = track_db

    def delete_playlist_data(self, playlist_key, delete_source=True, delete_library=True,
                             remove_config=False, dry_run=False):
        """Delete source M4A and/or library MP3/artwork for a playlist.

        Source files are in library/source/gamdl/<playlist>/ (directory).
        MP3 and artwork files are in flat dirs — identified via TrackDB.

        Returns DeleteResult with stats about what was deleted.
        """
        source_dir = Path(get_source_dir(playlist_key))

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

        # Remove config entry
        if remove_config:
            if self.config.remove_playlist(playlist_key):
                config_removed = True
                self.logger.info(f"  Removed config entry for '{playlist_key}'")
            else:
                self.logger.info(f"  Config entry for '{playlist_key}' not found (may not be configured)")

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
        self.download_stats = None  # DownloadStatistics object

        # Conversion stats
        self.conversion_stats = None

        # Tagging stats
        self.tagging_stats = None

        # Sync stats
        self.sync_success = False
        self.sync_destination = None
        self.sync_stats = None  # USBSyncStatistics object

        # Overall
        self.start_time = time.time()
        self.stages_completed = []
        self.stages_failed = []
        self.stages_skipped = []


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
        self.end_time = None
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
                 sync_tracker=None, track_db=None,
                 eq_config_manager=None, eq_config_override=None,
                 project_root=None):
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
        self.deps = deps or DependencyChecker(self.logger)
        self.config = config or ConfigManager(logger=self.logger)
        self.stats = PipelineStatistics()
        self.quality_preset = quality_preset
        self.cookie_path = cookie_path
        self.workers = workers
        self.project_root = Path(project_root) if project_root else Path('.')

    def run_full_pipeline(self, playlist=None, url=None, auto=False,
                         sync_destination=None,
                         dry_run=False, verbose=False, quality_preset=None,
                         validate_cookies=True, auto_refresh_cookies=False):
        """Execute the complete pipeline: download → convert → sync.

        Args:
            sync_destination: SyncDestination object for post-pipeline sync (optional)
        """
        self.stats.start_time = time.time()
        convert_result = None
        usb_result = None

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

        # ── Stage 2: Convert M4A → clean library MP3 ─────────────────
        self.logger.info("\n=== STAGE 2: Convert M4A → MP3 ===")
        music_dir = str(self.project_root / get_source_dir(self.stats.playlist_key))
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
        else:
            self.stats.stages_failed.append("convert")
            self.logger.error("Conversion stage failed")

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
                dest_key=sync_destination.effective_key, dry_run=dry_run)

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
        # Find playlist by name or index
        playlist = None
        if playlist_arg.isdigit():
            playlist = self.config.get_playlist_by_index(int(playlist_arg) - 1)
        else:
            playlist = self.config.get_playlist_by_key(playlist_arg)

        if not playlist:
            self.logger.error(f"Playlist not found: {playlist_arg}")
            self.stats.stages_failed.append("download")
            return False

        self.stats.playlist_key = playlist.key
        self.stats.playlist_name = playlist.name

        output_dir = get_source_dir(playlist.key)

        downloader = Downloader(self.logger, self.deps.venv_python,
                               cookie_path=self.cookie_path,
                               prompt_handler=self.prompt_handler,
                               display_handler=self.display_handler,
                               cancel_event=self.cancel_event)
        dl_result = downloader.download(
            playlist.url,
            output_dir,
            key=playlist.key,
            confirm=not auto,
            dry_run=dry_run,
            validate_cookies=validate_cookies,
            auto_refresh=auto_refresh_cookies
        )

        if dl_result.success:
            self.stats.download_success = True
            self.stats.download_stats = dl_result
            self.stats.stages_completed.append("download")
            return True
        else:
            # Check if user skipped (no stats and we have playlist info)
            # In this case, allow pipeline to continue
            if dl_result.downloaded == 0 and dl_result.failed == 0 and self.stats.playlist_key:
                self.stats.stages_skipped.append("download")
                return True  # Continue to next stage
            else:
                # Actual failure
                self.stats.stages_failed.append("download")
                return False

    def _ask_save_to_config(self, key, url, album_name):
        """Ask user if they want to save a new playlist to config."""
        if self.prompt_handler.confirm(f"Save '{album_name}' to {DEFAULT_CONFIG_FILE}?", default=False):
            self.config.add_playlist(key, url, album_name)


