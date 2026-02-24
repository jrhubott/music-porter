"""
porter_core - Business logic for music-porter

Contains all business logic classes, protocols, result dataclasses,
and supporting utilities. CLI-specific code lives in music-porter.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

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

VERSION = "2.11.0-delete-playlist-data"

DEFAULT_MUSIC_DIR = "music"
DEFAULT_EXPORT_DIR = "export"
DEFAULT_LOG_DIR = "logs"
DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_COOKIES = "cookies.txt"
DEFAULT_USB_DIR = "RZR/Music"

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

# Freshness thresholds for summary display (calendar days)
FRESHNESS_CURRENT_DAYS = 0
FRESHNESS_RECENT_DAYS = 7
FRESHNESS_STALE_DAYS = 30

# Worker pool defaults for parallel conversion
MAX_DEFAULT_WORKERS = 6
DEFAULT_WORKERS = min(os.cpu_count() or 1, MAX_DEFAULT_WORKERS)

# Default cleanup options for ID3 tag operations
DEFAULT_CLEANUP_OPTIONS = {
    "remove_id3v1": True,
    "use_id3v23": True,
    "remove_duplicates": True,
}

# TXXX frame description constants for original tag preservation
TXXX_ORIGINAL_TITLE = "OriginalTitle"
TXXX_ORIGINAL_ARTIST = "OriginalArtist"
TXXX_ORIGINAL_ALBUM = "OriginalAlbum"

# M4A tag key constants
M4A_TAG_TITLE = '\xa9nam'
M4A_TAG_ARTIST = '\xa9ART'
M4A_TAG_ALBUM = '\xa9alb'
M4A_TAG_COVER = 'covr'

# Cover art constants
TXXX_ORIGINAL_COVER_ART_HASH = "OriginalCoverArtHash"
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
    directory_structure: str  # "flat", "nested-artist", "nested-artist-album"
    filename_format: str      # "full", "title-only"
    id3_version: int          # 3 = ID3v2.3, 4 = ID3v2.4
    strip_id3v1: bool         # Remove ID3v1 tags
    title_tag_format: str     # "artist_title" → tag as "Artist - Title"
    artwork_size: int         # >0=resize to max px, 0=original, -1=strip
    quality_preset: str       # "lossless", "high", "medium", "low"
    pipeline_album: str       # "playlist_name" or "original"
    pipeline_artist: str      # "various" or "original"


# Seed defaults — used for auto-migration and _create_default().
# At runtime, OUTPUT_PROFILES is populated from config.yaml via load_output_profiles().
DEFAULT_OUTPUT_PROFILES: dict = {
    "ride-command": {
        "description": "Polaris Ride Command infotainment system",
        "directory_structure": "flat",
        "filename_format": "full",
        "id3_version": 3,
        "strip_id3v1": True,
        "title_tag_format": "artist_title",
        "artwork_size": 100,
        "quality_preset": "lossless",
        "pipeline_album": "playlist_name",
        "pipeline_artist": "various",
    },
    "basic": {
        "description": "Standard MP3 with original tags and artwork",
        "directory_structure": "flat",
        "filename_format": "full",
        "id3_version": 4,
        "strip_id3v1": True,
        "title_tag_format": "artist_title",
        "artwork_size": 0,
        "quality_preset": "lossless",
        "pipeline_album": "original",
        "pipeline_artist": "original",
    },
}

OUTPUT_PROFILES: dict = {}  # Populated at runtime by load_output_profiles()
DEFAULT_OUTPUT_TYPE = "ride-command"

# Valid choices for directory structure and filename format
VALID_DIR_STRUCTURES = ("flat", "nested-artist", "nested-artist-album")
VALID_FILENAME_FORMATS = ("full", "title-only")

# Profile name validation: lowercase alphanumeric with hyphens
VALID_PROFILE_NAME_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')

# Required fields for each profile entry in config.yaml
_PROFILE_REQUIRED_FIELDS = (
    "description", "directory_structure", "filename_format", "id3_version",
    "strip_id3v1", "title_tag_format", "artwork_size", "quality_preset",
    "pipeline_album", "pipeline_artist",
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

    ds = data["directory_structure"]
    if ds not in VALID_DIR_STRUCTURES:
        raise ValueError(
            f"Profile '{name}': 'directory_structure' must be one of "
            f"{VALID_DIR_STRUCTURES}, got '{ds}'")

    ff = data["filename_format"]
    if ff not in VALID_FILENAME_FORMATS:
        raise ValueError(
            f"Profile '{name}': 'filename_format' must be one of "
            f"{VALID_FILENAME_FORMATS}, got '{ff}'")

    iv = data["id3_version"]
    if iv not in (3, 4):
        raise ValueError(
            f"Profile '{name}': 'id3_version' must be 3 or 4, got {iv!r}")

    si = data["strip_id3v1"]
    if not isinstance(si, bool):
        raise ValueError(
            f"Profile '{name}': 'strip_id3v1' must be a boolean, got {si!r}")

    ttf = data["title_tag_format"]
    if ttf != "artist_title":
        raise ValueError(
            f"Profile '{name}': 'title_tag_format' must be 'artist_title', got '{ttf}'")

    asize = data["artwork_size"]
    if not isinstance(asize, int) or asize < -1:
        raise ValueError(
            f"Profile '{name}': 'artwork_size' must be an integer >= -1, got {asize!r}")

    qp = data["quality_preset"]
    if qp not in QUALITY_PRESETS:
        raise ValueError(
            f"Profile '{name}': 'quality_preset' must be one of "
            f"{list(QUALITY_PRESETS.keys())}, got '{qp}'")

    pa = data["pipeline_album"]
    if pa not in ("playlist_name", "original"):
        raise ValueError(
            f"Profile '{name}': 'pipeline_album' must be 'playlist_name' or "
            f"'original', got '{pa}'")

    par = data["pipeline_artist"]
    if par not in ("various", "original"):
        raise ValueError(
            f"Profile '{name}': 'pipeline_artist' must be 'various' or "
            f"'original', got '{par}'")


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


def get_export_dir(profile_name, playlist_key=None):
    """Build profile-scoped export path: export/<profile>/ or export/<profile>/<playlist>/"""
    if playlist_key:
        return f"{DEFAULT_EXPORT_DIR}/{profile_name}/{playlist_key}"
    return f"{DEFAULT_EXPORT_DIR}/{profile_name}"


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
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._active_bars = []

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = self.log_dir / f"{timestamp}.log"

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
            with open(self.log_file, 'a') as f:
                f.write(formatted_with_prefix + '\n')

    def _write_file_only(self, level, message):
        """Write message to log file only (no console output)."""
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_with_prefix = f"[{timestamp}] [{level}] {message}"

            # File only: full format with timestamp and level
            with open(self.log_file, 'a') as f:
                f.write(formatted_with_prefix + '\n')

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


class ConfigManager:
    """Manages configuration from config.yaml (YAML format)."""

    def __init__(self, conf_path=DEFAULT_CONFIG_FILE, logger=None):
        self.conf_path = Path(conf_path)
        self.logger = logger or Logger()
        self.playlists = []
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
        """Load configuration from YAML file."""
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

        # Load output_types — auto-migrate if missing/null
        raw_types = data.get('output_types')
        if raw_types is None:
            # Missing or null — inject seed defaults and save (one-time migration)
            import copy
            raw_types = copy.deepcopy(DEFAULT_OUTPUT_PROFILES)
            self._raw_output_types = raw_types
            self._save()
            self.logger.info("Migrated config.yaml: added output_types with default profiles")
        elif isinstance(raw_types, dict) and len(raw_types) == 0:
            raise ValueError(
                "config.yaml: 'output_types' is empty — at least one profile is required")

        # Validate and build OutputProfile instances
        self._raw_output_types = raw_types
        self.output_profiles = {}
        for name, fields in raw_types.items():
            _validate_profile(name, fields)
            # Build OutputProfile — ignore unknown extra fields (forward compat)
            self.output_profiles[name] = OutputProfile(
                name=name,
                description=fields["description"],
                directory_structure=fields["directory_structure"],
                filename_format=fields["filename_format"],
                id3_version=fields["id3_version"],
                strip_id3v1=fields["strip_id3v1"],
                title_tag_format=fields["title_tag_format"],
                artwork_size=fields["artwork_size"],
                quality_preset=fields["quality_preset"],
                pipeline_album=fields["pipeline_album"],
                pipeline_artist=fields["pipeline_artist"],
            )

        self.logger.info(f"Loaded {len(self.playlists)} playlists and "
                         f"{len(self.output_profiles)} output profiles from {self.conf_path}")

    def _create_default(self):
        """Create a default config.yaml with default profiles and empty playlists."""
        import copy
        self.settings = {
            'output_type': DEFAULT_OUTPUT_TYPE,
            'usb_dir': DEFAULT_USB_DIR,
            'workers': DEFAULT_WORKERS,
        }
        self._raw_output_types = copy.deepcopy(DEFAULT_OUTPUT_PROFILES)
        # Build OutputProfile instances from defaults
        self.output_profiles = {}
        for name, fields in self._raw_output_types.items():
            self.output_profiles[name] = OutputProfile(
                name=name, **{k: fields[k] for k in _PROFILE_REQUIRED_FIELDS}
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
                output_types[name] = {
                    f: getattr(p, f) for f in _PROFILE_REQUIRED_FIELDS
                }

        data = {
            'settings': self.settings,
            'output_types': output_types,
            'playlists': [
                {'key': p.key, 'url': p.url, 'name': p.name}
                for p in self.playlists
            ],
        }

        with open(self.conf_path, 'w') as f:
            f.write("# Music Porter Configuration\n")
            f.write("# CLI flags override these settings when specified.\n\n")
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def get_setting(self, key, default=None):
        """Get a setting value, returning default if not set."""
        return self.settings.get(key, default)

    def update_setting(self, key, value):
        """Update a setting and persist to config.yaml."""
        self.settings[key] = value
        self._save()

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

def _get_txxx(tags, desc_name):
    """
    Safely retrieve a TXXX frame value by its desc attribute.
    Iterates tag values directly by frame type rather than key
    format to avoid mutagen key indexing inconsistencies after
    save/reload cycles.
    """
    from mutagen.id3 import TXXX
    for frame in tags.values():
        if isinstance(frame, TXXX) and frame.desc == desc_name:
            return str(frame.text[0]) if frame.text else ""
    return ""


def _txxx_exists(tags, desc_name):
    """
    Returns True if a TXXX frame with the given desc already exists.
    Iterates tag values directly by frame type rather than key
    format to avoid mutagen key indexing inconsistencies after
    save/reload cycles.
    """
    from mutagen.id3 import TXXX
    for frame in tags.values():
        if isinstance(frame, TXXX) and frame.desc == desc_name:
            return True
    return False


def save_original_tag(tags, tag_key, tag_name, current_value, label, logger=None,
                      verbose=False):
    """
    Save the original value in a TXXX tag only if one does not already
    exist. Uses _txxx_exists() as a hard gate — if the tag is already
    present it will never be written to again regardless of its value.
    This ensures the true original is permanently protected.

    Returns:
        tuple: (value, was_newly_stored)
            - value: The tag value (existing or newly stored)
            - was_newly_stored: True if a new TXXX frame was created,
                                False if frame already existed or was skipped
    """
    from mutagen.id3 import TXXX

    # ── Hard gate: if it already exists, never write to it again ──
    if _txxx_exists(tags, tag_name):
        existing = _get_txxx(tags, tag_name)
        if logger:
            logger.debug(f"Original {label} already saved: '{existing}'. Not overwriting.")
        return (existing, False)

    # Not found — safe to store for the first time
    if current_value:
        tags.add(TXXX(encoding=3, desc=tag_name, text=current_value))
        if logger:
            msg = f"Stored original {label} '{current_value}' in '{tag_name}' tag"
            if verbose:
                logger.info(msg)
            else:
                logger.file_info(msg)
        return (current_value, True)
    else:
        if logger:
            logger.debug(f"No existing {label} tag found. Skipping original {label} save")
        return ("", False)


def _strip_artist_prefix(title, artist):
    """
    If title starts with 'artist - ' strip that prefix and return
    the clean title. Handles the case where a previous run already
    compounded the title.
    """
    prefix = f"{artist} - "
    if title.startswith(prefix):
        return title[len(prefix):]
    return title


def sanitize_filename(name):
    """Remove invalid filename characters."""
    invalid_chars = r'\/:*?"<>|'
    return "".join(c for c in name if c not in invalid_chars)


def read_m4a_tags(input_file):
    """
    Read title, artist, and album tags from an M4A file.
    Returns (title, artist, album) tuple with 'Unknown *' defaults.
    """
    from mutagen.mp4 import MP4
    m4a = MP4(str(input_file))
    title  = str(m4a.tags.get(M4A_TAG_TITLE, ['Unknown Title'])[0])
    artist = str(m4a.tags.get(M4A_TAG_ARTIST, ['Unknown Artist'])[0])
    album  = str(m4a.tags.get(M4A_TAG_ALBUM, ['Unknown Album'])[0])
    return title, artist, album


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


def update_title_tag(tags, logger=None, dry_run=False, verbose=False):
    """
    Update the TIT2 (Title) tag to 'Artist - Title' format.
    Prefers TXXX:OriginalArtist and TXXX:OriginalTitle as source
    values if they exist, otherwise falls back to current TPE1 / TIT2.
    Protects the original TIT2 value in TXXX:OriginalTitle before
    any change is made. Never compounds an already-formatted title.

    Returns True if the title was updated, False otherwise.
    """
    from mutagen.id3 import TIT2

    orig_title  = _get_txxx(tags, TXXX_ORIGINAL_TITLE)
    orig_artist = _get_txxx(tags, TXXX_ORIGINAL_ARTIST)

    current_title  = str(tags["TIT2"]) if "TIT2" in tags else ""
    current_artist = str(tags["TPE1"]) if "TPE1" in tags else ""

    # ── Determine clean source values ─────────────────────────────
    source_artist = orig_artist if orig_artist else current_artist

    if orig_title:
        source_title = _strip_artist_prefix(orig_title, source_artist)
    else:
        source_title = _strip_artist_prefix(current_title, source_artist)

    new_title = f"{source_artist} - {source_title}"

    # ── Guard: skip if already correct ────────────────────────────
    if current_title == new_title:
        if logger:
            if verbose:
                logger.skip(f"Title already correct: '{current_title}'")
            else:
                logger.file_info(f"Title already correct: '{current_title}'")
        return False

    if verbose and logger:
        logger.debug(f"Title source:   '{source_title}' "
                    f"({TXXX_ORIGINAL_TITLE  if orig_title  else 'TIT2'})")
        logger.debug(f"Artist source:  '{source_artist}' "
                    f"({TXXX_ORIGINAL_ARTIST if orig_artist else 'TPE1'})")
        logger.debug(f"New Title:      '{new_title}'")

    if dry_run:
        if logger:
            logger.dry_run(f"Would update Title: '{current_title}' → '{new_title}'")
        return False

    tags["TIT2"] = TIT2(encoding=3, text=new_title)
    if logger:
        msg = f"Title updated: '{current_title}' → '{new_title}'"
        if verbose:
            logger.info(msg)
        else:
            logger.file_info(msg)
    return True


def _apply_cleanup(tags, filepath, cleanup_options):
    """
    Strip all non-essential ID3 frames, keeping only Title, Artist,
    Album, and the three OriginalTitle / OriginalArtist / OriginalAlbum
    TXXX preservation tags. Uses isinstance() check on frame values
    rather than key string matching to reliably identify TXXX frames
    after save/reload cycles.
    """
    from mutagen.id3 import TXXX

    v2_version = 3 if cleanup_options.get("use_id3v23") else 4
    v1         = 0 if cleanup_options.get("remove_id3v1") else 1

    allowed_frames     = {"TIT2", "TPE1", "TALB", "APIC"}
    allowed_txxx_descs = {TXXX_ORIGINAL_TITLE, TXXX_ORIGINAL_ARTIST, TXXX_ORIGINAL_ALBUM,
                          TXXX_ORIGINAL_COVER_ART_HASH}

    for key in list(tags.keys()):
        frame = tags[key]
        if isinstance(frame, TXXX):
            if frame.desc in allowed_txxx_descs:
                continue
            del tags[key]
        else:
            base = key.split(":")[0]
            if base not in allowed_frames:
                del tags[key]

    # ── Remove duplicate frames ────────────────────────────────────
    if cleanup_options.get("remove_duplicates"):
        seen = {}
        for key in list(tags.keys()):
            frame = tags[key]

            # Special handling for TXXX frames: track by description, not base key
            if isinstance(frame, TXXX):
                # Use full TXXX:desc as the unique identifier
                unique_key = f"TXXX:{frame.desc}"
                if unique_key in seen:
                    del tags[key]
                else:
                    seen[unique_key] = True
            else:
                # For all other frame types, use base key as before
                base = key.split(":")[0]
                if base in seen:
                    del tags[key]
                else:
                    seen[base] = True

    tags.save(filepath, v2_version=v2_version, v1=v1)


class TagStatistics:
    """Tracks tagging operation statistics."""

    def __init__(self):
        self.title_updated = 0
        self.album_updated = 0      # NEW: Track album tag updates
        self.artist_updated = 0     # NEW: Track artist tag updates
        self.title_stored = 0
        self.artist_stored = 0
        self.album_stored = 0
        self.title_protected = 0
        self.artist_protected = 0
        self.album_protected = 0
        self.title_restored = 0
        self.artist_restored = 0
        self.album_restored = 0
        self.title_missing = 0
        self.artist_missing = 0
        self.album_missing = 0



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


class LegacyDisplayHandler:
    """Backward-compatible DisplayHandler that reproduces original print() behavior.

    During the service layer migration, this was available for classes not yet
    migrated to the DisplayHandler protocol. Now that migration is complete,
    CLIDisplayHandler is the recommended handler for CLI use. This class
    remains for backward compatibility.
    """

    def __init__(self, logger=None):
        self._logger = logger
        self._bar = None

    def show_progress(self, current, total, message):
        if self._bar is None or self._bar.total != total:
            if self._bar is not None:
                self._bar.close()
            self._bar = ProgressBar(total=total, desc=message, logger=self._logger)
        self._bar.update(1)

    def finish_progress(self):
        if self._bar is not None:
            self._bar.close()
            self._bar = None

    def show_status(self, message, level="info"):
        print(message)

    def show_banner(self, title, subtitle=None):
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        if subtitle:
            print(f"  {subtitle}")
        print(f"{'=' * 60}\n")


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
class TagUpdateResult:
    """Result of TaggerManager.update_tags()."""
    success: bool
    directory: str
    duration: float
    files_processed: int
    files_updated: int
    files_skipped: int
    errors: int
    title_updated: int = 0
    album_updated: int = 0
    artist_updated: int = 0
    title_stored: int = 0
    artist_stored: int = 0
    album_stored: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TagRestoreResult:
    """Result of TaggerManager.restore_tags()."""
    success: bool
    directory: str
    duration: float
    files_processed: int
    files_restored: int
    files_skipped: int
    errors: int
    title_restored: int = 0
    artist_restored: int = 0
    album_restored: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TagResetResult:
    """Result of TaggerManager.reset_tags_from_source()."""
    success: bool
    input_dir: str
    output_dir: str
    duration: float
    files_matched: int
    files_reset: int
    files_skipped: int
    errors: int
    tags_reset: int = 0
    tags_rewritten: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


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
class USBSyncResult:
    """Result of USBManager.sync_to_usb()."""
    success: bool
    source: str
    destination: str
    volume_name: str
    duration: float
    files_found: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LibrarySummaryResult:
    """Result of SummaryManager.generate_summary()."""
    success: bool
    export_dir: str
    scan_duration: float
    mode: str  # "quick", "default", "detailed"
    total_playlists: int = 0
    total_files: int = 0
    total_size_bytes: int = 0
    avg_file_size: float = 0.0
    files_with_protection_tags: int = 0
    files_missing_protection_tags: int = 0
    sample_size: int = 0
    files_with_cover_art: int = 0
    files_without_cover_art: int = 0
    files_with_original_cover_art: int = 0
    files_with_resized_cover_art: int = 0
    playlist_summaries: list = field(default_factory=list)
    music_library_stats: Any = None  # MusicLibraryStats or None

    def to_dict(self) -> dict:
        d = asdict(self)
        # PlaylistSummary objects need manual conversion
        d['playlist_summaries'] = [
            {
                'name': p.name, 'path': p.path,
                'file_count': p.file_count,
                'total_size_bytes': p.total_size_bytes,
                'avg_file_size_mb': p.avg_file_size_mb,
                'files_with_cover_art': p.files_with_cover_art,
                'files_without_cover_art': p.files_without_cover_art,
            } if hasattr(p, 'name') else p
            for p in self.playlist_summaries
        ]
        return d


@dataclass
class CoverArtResult:
    """Result of CoverArtManager action methods."""
    success: bool
    action: str  # "embed", "extract", "update", "strip", "resize"
    directory: str
    duration: float
    files_processed: int = 0
    files_modified: int = 0
    files_skipped: int = 0
    errors: int = 0
    source_dir: str | None = None
    image_path: str | None = None
    no_source: int = 0
    max_size: int | None = None
    total_before: int = 0
    total_after: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeleteResult:
    """Result of DataManager.delete_playlist_data()."""
    success: bool
    playlist_key: str
    source_deleted: bool = False
    export_deleted: bool = False
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
    tag_result: TagUpdateResult | None = None
    cover_art_result: CoverArtResult | None = None
    usb_result: USBSyncResult | None = None
    # Pipeline-specific stats carried over from PipelineStatistics
    tagging_album: str | None = None
    tagging_artist: str | None = None
    cover_art_embedded: int = 0
    cover_art_missing: int = 0
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



class TaggerManager:
    """Manages MP3 tag operations (update, restore, reset)."""

    def __init__(self, logger=None, cleanup_options=None, output_profile=None,
                 prompt_handler=None, display_handler=None, cancel_event=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]
        if output_profile is not None:
            self.cleanup_options = {
                "remove_id3v1": output_profile.strip_id3v1,
                "use_id3v23": output_profile.id3_version == 3,
                "remove_duplicates": True,
            }
        else:
            self.cleanup_options = cleanup_options or DEFAULT_CLEANUP_OPTIONS
        self.stats = TagStatistics()

    def update_tags(self, directory, new_album=None, new_artist=None,
                   dry_run=False, verbose=False):
        """
        Recursively update album and/or artist tags for all MP3s under a
        directory. Originals are stored in TXXX:OriginalAlbum /
        OriginalArtist / OriginalTitle BEFORE any tag is modified.
        """
        from mutagen.id3 import ID3, TALB, TPE1, ID3NoHeaderError

        directory = Path(directory)
        if not directory.is_dir():
            self.logger.error(f"Directory not found: {directory}")
            return TagUpdateResult(success=False, directory=str(directory),
                                   duration=0, files_processed=0, files_updated=0,
                                   files_skipped=0, errors=1)

        mp3_files = list(directory.rglob("*.mp3"))

        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return TagUpdateResult(success=True, directory=str(directory),
                                   duration=0, files_processed=0, files_updated=0,
                                   files_skipped=0, errors=0)

        self.logger.info(f"Found {len(mp3_files)} MP3 file(s)")
        self.logger.info(f"New Album:  {new_album or '—'}")
        self.logger.info(f"New Artist: {new_artist or '—'}")

        start_time = time.time()
        updated = 0
        skipped = 0
        errors = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Tagging",
        )

        try:
            for filepath in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Tag update cancelled by user")
                    break
                filename = filepath.relative_to(directory)

                try:
                    try:
                        tags = ID3(str(filepath))
                    except ID3NoHeaderError:
                        self.logger.warn(f"No ID3 tags found in '{filename}'. Skipping.")
                        skipped += 1
                        progress.update(1)
                        continue

                    current_album  = str(tags["TALB"]) if "TALB" in tags else ""
                    current_artist = str(tags["TPE1"]) if "TPE1" in tags else ""
                    current_title  = str(tags["TIT2"]) if "TIT2" in tags else ""

                    if verbose:
                        self.logger.debug("Tags BEFORE update:")
                        self.logger.debug(f"  → Title:  '{current_title}'")
                        self.logger.debug(f"  → Artist: '{current_artist}'")
                        self.logger.debug(f"  → Album:  '{current_album}'")

                    if dry_run:
                        if new_album:
                            self.logger.dry_run(f"Album:  '{current_album}' → '{new_album}'")
                        if new_artist:
                            self.logger.dry_run(f"Artist: '{current_artist}' → '{new_artist}'")
                        update_title_tag(tags, self.logger, dry_run=True, verbose=verbose)
                        continue

                    # ── Store ALL originals BEFORE any tag is modified ──
                    file_changed = False

                    if new_album:
                        _, was_stored = save_original_tag(
                            tags, "TXXX:OriginalAlbum", TXXX_ORIGINAL_ALBUM,
                            current_album, "album", self.logger, verbose=verbose)
                        if was_stored:
                            self.stats.album_stored += 1
                        else:
                            self.stats.album_protected += 1

                    if new_artist:
                        _, was_stored = save_original_tag(
                            tags, "TXXX:OriginalArtist", TXXX_ORIGINAL_ARTIST,
                            current_artist, "artist", self.logger, verbose=verbose)
                        if was_stored:
                            self.stats.artist_stored += 1
                        else:
                            self.stats.artist_protected += 1

                    # ── Store OriginalTitle BEFORE update_title_tag() runs ──
                    source_artist = _get_txxx(tags, TXXX_ORIGINAL_ARTIST) or current_artist
                    clean_title   = _strip_artist_prefix(current_title, source_artist)
                    _, was_stored = save_original_tag(
                        tags, "TXXX:OriginalTitle", TXXX_ORIGINAL_TITLE,
                        clean_title, "title", self.logger, verbose=verbose)
                    if was_stored:
                        self.stats.title_stored += 1
                    else:
                        self.stats.title_protected += 1

                    # ── Now apply new tag values ───────────────────────────
                    if new_album:
                        if current_album != new_album:
                            file_changed = True
                            self.stats.album_updated += 1  # Track album updates
                        tags["TALB"] = TALB(encoding=3, text=new_album)

                    if new_artist:
                        if current_artist != new_artist:
                            file_changed = True
                            self.stats.artist_updated += 1  # Track artist updates
                        tags["TPE1"] = TPE1(encoding=3, text=new_artist)

                    # ── Refresh Title to 'Artist - Title' format ──────────
                    if update_title_tag(tags, self.logger, dry_run=dry_run, verbose=verbose):
                        self.stats.title_updated += 1
                        file_changed = True

                    _apply_cleanup(tags, str(filepath), self.cleanup_options)

                    if file_changed:
                        updated += 1
                        msg = f"[{updated}/{len(mp3_files)}] Tags updated: {filename}"
                    else:
                        skipped += 1
                        msg = f"[{skipped}/{len(mp3_files)}] Skipping (no changes): {filename}"
                    if not verbose:
                        self.logger.file_info(msg)
                    else:
                        self.logger.info(msg)
                    progress.update(1)

                except Exception as e:
                    self.logger.error(f"Failed to update '{filename}': {e}")
                    errors += 1
                    progress.update(1)
        finally:
            progress.close()

        duration = time.time() - start_time
        return TagUpdateResult(
            success=errors == 0,
            directory=str(directory),
            duration=duration,
            files_processed=updated + skipped,
            files_updated=updated,
            files_skipped=skipped,
            errors=errors,
            title_updated=self.stats.title_updated,
            album_updated=self.stats.album_updated,
            artist_updated=self.stats.artist_updated,
            title_stored=self.stats.title_stored,
            artist_stored=self.stats.artist_stored,
            album_stored=self.stats.album_stored,
        )

    def restore_tags(self, directory, restore_album=False, restore_title=False,
                    restore_artist=False, dry_run=False, verbose=False):
        """
        Recursively restore original tags for all MP3s under a directory
        by reading values from TXXX:OriginalTitle / OriginalArtist /
        OriginalAlbum tags.
        """
        from mutagen.id3 import ID3, TALB, TIT2, TPE1, ID3NoHeaderError

        directory = Path(directory)
        if not directory.is_dir():
            self.logger.error(f"Directory not found: {directory}")
            return TagRestoreResult(success=False, directory=str(directory),
                                    duration=0, files_processed=0, files_restored=0,
                                    files_skipped=0, errors=1)

        mp3_files = list(directory.rglob("*.mp3"))

        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return TagRestoreResult(success=True, directory=str(directory),
                                    duration=0, files_processed=0, files_restored=0,
                                    files_skipped=0, errors=0)

        self.logger.info(f"Found {len(mp3_files)} MP3 file(s)")
        self.logger.info(f"Restoring Album:  {restore_album}")
        self.logger.info(f"Restoring Title:  {restore_title}")
        self.logger.info(f"Restoring Artist: {restore_artist}")

        start_time = time.time()
        count = 0
        restored = 0
        skipped = 0
        errors = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Restoring",
        )

        try:
            for filepath in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Tag restore cancelled by user")
                    break
                count += 1
                filename = filepath.relative_to(directory)

                try:
                    try:
                        tags = ID3(str(filepath))
                    except ID3NoHeaderError:
                        self.logger.warn(f"No ID3 tags found in '{filename}'. Skipping.")
                        skipped += 1
                        progress.update(1)
                        continue

                    orig_title  = _get_txxx(tags, TXXX_ORIGINAL_TITLE)
                    orig_artist = _get_txxx(tags, TXXX_ORIGINAL_ARTIST)
                    orig_album  = _get_txxx(tags, TXXX_ORIGINAL_ALBUM)

                    if verbose:
                        self.logger.debug("Preserved originals:")
                        self.logger.debug(f"  → OriginalTitle:  '{orig_title}'")
                        self.logger.debug(f"  → OriginalArtist: '{orig_artist}'")
                        self.logger.debug(f"  → OriginalAlbum:  '{orig_album}'")

                    file_restored = False

                    if restore_title:
                        if orig_title:
                            if dry_run:
                                self.logger.dry_run(f"Would restore Title: → '{orig_title}'")
                            else:
                                tags["TIT2"] = TIT2(encoding=3, text=orig_title)
                                msg = f"Title restored → '{orig_title}'"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)
                                self.stats.title_restored += 1
                                file_restored = True
                        else:
                            if verbose:
                                self.logger.skip(f"No OriginalTitle for '{filename}'")
                            else:
                                self.logger.file_info(f"No OriginalTitle for '{filename}'")
                            self.stats.title_missing += 1

                    if restore_artist:
                        if orig_artist:
                            if dry_run:
                                self.logger.dry_run(f"Would restore Artist: → '{orig_artist}'")
                            else:
                                tags["TPE1"] = TPE1(encoding=3, text=orig_artist)
                                msg = f"Artist restored → '{orig_artist}'"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)
                                self.stats.artist_restored += 1
                                file_restored = True
                        else:
                            if verbose:
                                self.logger.skip(f"No OriginalArtist for '{filename}'")
                            else:
                                self.logger.file_info(f"No OriginalArtist for '{filename}'")
                            self.stats.artist_missing += 1

                    if restore_album:
                        if orig_album:
                            if dry_run:
                                self.logger.dry_run(f"Would restore Album: → '{orig_album}'")
                            else:
                                tags["TALB"] = TALB(encoding=3, text=orig_album)
                                msg = f"Album restored → '{orig_album}'"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)
                                self.stats.album_restored += 1
                                file_restored = True
                        else:
                            if verbose:
                                self.logger.skip(f"No OriginalAlbum for '{filename}'")
                            else:
                                self.logger.file_info(f"No OriginalAlbum for '{filename}'")
                            self.stats.album_missing += 1

                    if not dry_run and file_restored:
                        _apply_cleanup(tags, str(filepath), self.cleanup_options)
                        restored += 1
                        msg = f"[{restored}/{len(mp3_files)}] Tags restored: {filename}"
                    elif not file_restored:
                        skipped += 1
                        msg = f"[{skipped}/{len(mp3_files)}] Skipping (nothing to restore): {filename}"
                    else:
                        msg = None
                    if msg:
                        if not verbose:
                            self.logger.file_info(msg)
                        else:
                            self.logger.info(msg)
                    progress.update(1)

                except Exception as e:
                    self.logger.error(f"Failed to restore '{filename}': {e}")
                    errors += 1
                    progress.update(1)
        finally:
            progress.close()

        duration = time.time() - start_time
        return TagRestoreResult(
            success=errors == 0,
            directory=str(directory),
            duration=duration,
            files_processed=restored + skipped,
            files_restored=restored,
            files_skipped=skipped,
            errors=errors,
            title_restored=self.stats.title_restored,
            artist_restored=self.stats.artist_restored,
            album_restored=self.stats.album_restored,
        )

    def reset_tags_from_source(self, input_dir, output_dir, dry_run=False, verbose=False):
        """
        Recursively walk input_dir for .m4a files. For each one, read the
        original Title, Artist, and Album tags directly from the source,
        find the matching MP3 in output_dir, reset all three TXXX:Original*
        protection tags from the source values, rewrite TIT2/TPE1/TALB,
        refresh the title to 'Artist - Title' format, and save.

        ⚠️ WARNING: This permanently overwrites TXXX:Original* frames!
        """
        from mutagen.id3 import ID3, TALB, TIT2, TPE1, TXXX, ID3NoHeaderError

        start_time = time.time()

        input_path = Path(input_dir)
        output_path = Path(output_dir)

        if not input_path.is_dir():
            self.logger.error(f"Input directory not found: {input_path}")
            return TagResetResult(success=False, input_dir=str(input_path),
                                  output_dir=str(output_path), duration=0,
                                  files_matched=0, files_reset=0, files_skipped=0, errors=1)

        if not output_path.is_dir():
            self.logger.error(f"Output directory not found: {output_path}")
            return TagResetResult(success=False, input_dir=str(input_path),
                                  output_dir=str(output_path), duration=0,
                                  files_matched=0, files_reset=0, files_skipped=0, errors=1)

        # Find all M4A files
        m4a_files = [
            f for f in input_path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]

        if not m4a_files:
            self.logger.info(f"No .m4a files found in '{input_path}'")
            return TagResetResult(success=True, input_dir=str(input_path),
                                  output_dir=str(output_path), duration=0,
                                  files_matched=0, files_reset=0, files_skipped=0, errors=0)

        total = len(m4a_files)
        count = 0
        updated = 0
        skipped = 0
        errors = 0
        tags_reset = 0

        self.logger.info(f"Found {total} .m4a source file(s)")

        # Confirmation prompt (unless dry-run)
        if not dry_run:
            msg = (f"WARNING: --reset-tags will permanently overwrite all "
                   f"TXXX:Original* protection tags in '{output_path}' "
                   f"with values read fresh from '{input_path}'. "
                   f"This cannot be undone.")
            if not self.prompt_handler.confirm_destructive(msg):
                self.logger.info("Cancelled. No files were modified.")
                return TagResetResult(success=False, input_dir=str(input_path),
                                      output_dir=str(output_path), duration=0,
                                      files_matched=0, files_reset=0, files_skipped=0, errors=0)

        for input_file in m4a_files:
            if _is_cancelled(self.cancel_event):
                self.logger.warn("Tag reset cancelled by user")
                break
            count += 1
            display_name = input_file.relative_to(input_path)

            self.logger.info(f"[{count}/{total}] Resetting tags from source: {display_name}")

            try:
                # Read M4A tags
                title, artist, album = read_m4a_tags(input_file)

                # Find matching MP3 using profile-aware filename and path
                safe_title = self._sanitize_filename(title)
                safe_artist = self._sanitize_filename(artist)
                safe_album = self._sanitize_filename(album)
                fmt = self.output_profile.filename_format
                if fmt == "title-only":
                    mp3_filename = f"{safe_title}.mp3"
                else:
                    mp3_filename = f"{safe_artist} - {safe_title}.mp3"
                structure = self.output_profile.directory_structure
                if structure == "nested-artist":
                    mp3_path = output_path / safe_artist / mp3_filename
                elif structure == "nested-artist-album":
                    mp3_path = output_path / safe_artist / safe_album / mp3_filename
                else:
                    mp3_path = output_path / mp3_filename

                if not mp3_path.exists():
                    self.logger.skip(f"No matching MP3 found: '{mp3_filename}'")
                    skipped += 1
                    continue

                if verbose:
                    self.logger.debug("Source .m4a tags:")
                    self.logger.debug(f"  → Title:  '{title}'")
                    self.logger.debug(f"  → Artist: '{artist}'")
                    self.logger.debug(f"  → Album:  '{album}'")
                    self.logger.debug(f"Matched MP3: '{mp3_path}'")

                if dry_run:
                    self.logger.dry_run("Would reset MP3 tags from source:")
                    self.logger.dry_run(f"  → TIT2 / OriginalTitle:  '{title}'")
                    self.logger.dry_run(f"  → TPE1 / OriginalArtist: '{artist}'")
                    self.logger.dry_run(f"  → TALB / OriginalAlbum:  '{album}'")
                    self.logger.dry_run(f"  → Title would become:    '{artist} - {title}'")
                    continue

                # Load MP3 tags
                try:
                    tags = ID3(str(mp3_path))
                except ID3NoHeaderError:
                    tags = ID3()

                # ── Hard reset: remove existing Original* TXXX frames ──
                # This clears the hard gate so save_original_tag() can
                # write fresh values from the source .m4a
                for key in list(tags.keys()):
                    frame = tags[key]
                    if isinstance(frame, TXXX) and frame.desc in {
                        TXXX_ORIGINAL_TITLE, TXXX_ORIGINAL_ARTIST, TXXX_ORIGINAL_ALBUM
                    }:
                        del tags[key]
                        tags_reset += 1

                # ── Write fresh base tags from source .m4a ────────────
                tags["TIT2"] = TIT2(encoding=3, text=title)
                tags["TPE1"] = TPE1(encoding=3, text=artist)
                tags["TALB"] = TALB(encoding=3, text=album)

                # ── Store fresh originals — gate is clear after reset ──
                save_original_tag(tags, "TXXX:OriginalTitle", TXXX_ORIGINAL_TITLE,
                                title, "title", self.logger, verbose=verbose)
                save_original_tag(tags, "TXXX:OriginalArtist", TXXX_ORIGINAL_ARTIST,
                                artist, "artist", self.logger, verbose=verbose)
                save_original_tag(tags, "TXXX:OriginalAlbum", TXXX_ORIGINAL_ALBUM,
                                album, "album", self.logger, verbose=verbose)

                # ── Refresh Title to 'Artist - Title' format ──────────
                update_title_tag(tags, self.logger, dry_run=dry_run, verbose=verbose)

                _apply_cleanup(tags, str(mp3_path), self.cleanup_options)

                if verbose:
                    self.logger.debug("Tags AFTER reset:")
                    self.logger.debug(f"  → Title:          '{tags['TIT2']!s}'")
                    self.logger.debug(f"  → Artist:         '{artist}'")
                    self.logger.debug(f"  → Album:          '{album}'")
                    self.logger.debug(f"  → OriginalTitle:  '{title}'")
                    self.logger.debug(f"  → OriginalArtist: '{artist}'")
                    self.logger.debug(f"  → OriginalAlbum:  '{album}'")

                self.logger.ok(f"Tags reset from source → '{mp3_filename}'")
                updated += 1

            except Exception as e:
                self.logger.error(f"Failed to reset tags for '{display_name}': {e}")
                errors += 1

        duration = time.time() - start_time

        return TagResetResult(
            success=errors == 0,
            input_dir=str(input_dir),
            output_dir=str(output_dir),
            duration=duration,
            files_matched=total,
            files_reset=updated,
            files_skipped=skipped,
            errors=errors,
            tags_reset=tags_reset,
            tags_rewritten=updated * 3,
        )

    def _sanitize_filename(self, name):
        """Remove invalid filename characters."""
        return sanitize_filename(name)


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
    """Manages M4A to MP3 conversion with tag preservation."""

    def __init__(self, logger=None, quality_preset='lossless', workers=None, embed_cover_art=True,
                 output_profile=None, display_handler=None, cancel_event=None):
        self.logger = logger or Logger()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.stats = ConversionStatistics()
        self.quality_preset = quality_preset
        self.quality_settings = self._get_quality_settings(quality_preset)
        self.workers = workers if workers is not None else DEFAULT_WORKERS
        self.embed_cover_art = embed_cover_art
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]

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

    def _build_output_filename(self, artist: str, title: str) -> str:
        """Build output filename based on the active output profile."""
        if self.output_profile.filename_format == "title-only":
            return f"{title}.mp3"
        # Default: artist_title
        return f"{artist} - {title}.mp3"

    def _build_output_path(self, base_path: Path, filename: str, artist: str | None = None, album: str | None = None) -> Path:
        """Build output file path based on the active output profile."""
        structure = self.output_profile.directory_structure
        if structure == "nested-artist":
            safe_artist = artist or "Unknown Artist"
            return base_path / safe_artist / filename
        elif structure == "nested-artist-album":
            safe_artist = artist or "Unknown Artist"
            safe_album = album or "Unknown Album"
            return base_path / safe_artist / safe_album / filename
        # Default: flat
        return base_path / filename

    def _convert_single_file(self, input_file, input_path, output_path, force, dry_run, verbose, progress_bar=None):
        """Convert a single M4A file to MP3. Thread-safe for parallel execution."""
        import hashlib

        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TXXX, ID3NoHeaderError

        display_name = input_file.relative_to(input_path)
        count = self.stats.next_progress()

        try:
            # Read M4A tags
            title, artist, album = read_m4a_tags(input_file)

            # Create output filename based on active output profile
            safe_title = self._sanitize_filename(title)
            safe_artist = self._sanitize_filename(artist)
            safe_album = self._sanitize_filename(album)
            output_filename = self._build_output_filename(safe_artist, safe_title)
            output_file = self._build_output_path(output_path, output_filename, safe_artist, safe_album)
            already_exists = output_file.exists()

            if already_exists and not force:
                self.stats.increment('skipped')
                collision_hint = ""
                if self.output_profile.filename_format != "full":
                    collision_hint = " (possible filename collision — try 'full' format)"
                msg = f"[{count}/{self.stats.total_found}] Skipping (already exists): {output_filename}{collision_hint}"
                if progress_bar and not verbose:
                    self.logger.file_info(msg)
                else:
                    self.logger.info(msg)
                if progress_bar:
                    progress_bar.update(1)
                return

            if verbose:
                self.logger.debug(f"Source file:  '{input_file}'")
                self.logger.debug(f"File size:    {input_file.stat().st_size / 1024:.1f} KB")
                if already_exists and force:
                    self.logger.debug(f"Force flag set — overwriting: '{output_filename}'")
                # Display quality settings
                quality_desc = f"{self.quality_settings['mode'].upper()}"
                if self.quality_settings['mode'] == 'vbr':
                    quality_desc += f" quality {self.quality_settings['value']}"
                else:
                    quality_desc += f" {self.quality_settings['value']}kbps"
                self.logger.debug(f"Quality:      {quality_desc} (preset: {self.quality_preset})")
                self.logger.debug("Source tags:")
                self.logger.debug(f"  → Title:  '{title}'")
                self.logger.debug(f"  → Artist: '{artist}'")
                self.logger.debug(f"  → Album:  '{album}'")

            if dry_run:
                if already_exists and force:
                    self.logger.dry_run(f"Would overwrite: '{output_filename}'")
                else:
                    self.logger.dry_run(f"Would convert:   '{display_name}'")
                output_display = str(output_file.relative_to(output_path)) if self.output_profile.directory_structure != "flat" else output_filename
                self.logger.dry_run(f"  → Output:     '{output_display}'")
                self.logger.dry_run(f"  → Title:      '{title}'")
                self.logger.dry_run(f"  → Artist:     '{artist}'")
                self.logger.dry_run(f"  → Album:      '{album}'")
                artwork_size = self.output_profile.artwork_size
                if self.embed_cover_art and artwork_size != -1:
                    cover_data, cover_mime = read_m4a_cover_art(input_file)
                    if cover_data:
                        art_desc = f"{len(cover_data) / 1024:.1f} KB ({cover_mime})"
                        if artwork_size > 0:
                            art_desc += f", resize to {artwork_size}px"
                        self.logger.dry_run(f"  → Cover art:  {art_desc}")
                    else:
                        self.logger.dry_run("  → Cover art:  (none found in source)")
                else:
                    reason = "stripped by profile" if artwork_size == -1 else "disabled"
                    self.logger.dry_run(f"  → Cover art:  ({reason})")
                return

            # Ensure parent directories exist (needed for nested structures)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Run ffmpeg conversion
            import ffmpeg as _ffmpeg
            try:
                # Build FFmpeg parameters based on quality mode
                ffmpeg_params = {'acodec': 'libmp3lame'}
                if self.quality_settings['mode'] == 'vbr':
                    ffmpeg_params['q:a'] = self.quality_settings['value']
                else:  # cbr for lossless
                    ffmpeg_params['b:a'] = self.quality_settings['value'] + 'k'

                (
                    _ffmpeg
                    .input(str(input_file))
                    .output(str(output_file), **ffmpeg_params)
                    .run(overwrite_output=True, quiet=True)
                )
            except _ffmpeg.Error as e:
                # Re-raise as generic exception to be caught by outer try/except
                error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
                raise Exception(f"FFmpeg conversion failed: {error_msg}") from e

            # Write basic ID3 tags from source M4A (no modifications)
            try:
                tags = ID3(str(output_file))
            except ID3NoHeaderError:
                tags = ID3()

            tags["TIT2"] = TIT2(encoding=3, text=title)
            tags["TPE1"] = TPE1(encoding=3, text=artist)
            tags["TALB"] = TALB(encoding=3, text=album)

            # Embed cover art from source M4A
            artwork_size = self.output_profile.artwork_size
            if self.embed_cover_art and artwork_size != -1:
                cover_data, cover_mime = read_m4a_cover_art(input_file)
                if cover_data:
                    # Hash is always computed from original (pre-resize) data
                    if not _txxx_exists(tags, TXXX_ORIGINAL_COVER_ART_HASH):
                        art_hash = hashlib.sha256(cover_data).hexdigest()[:16]
                        tags.add(TXXX(encoding=3,
                                      desc=TXXX_ORIGINAL_COVER_ART_HASH,
                                      text=[art_hash]))
                    # Resize if profile specifies a max dimension
                    embed_data, embed_mime = cover_data, cover_mime
                    if artwork_size > 0:
                        embed_data, embed_mime = resize_cover_art_bytes(cover_data, artwork_size, cover_mime)
                    tags.add(APIC(
                        encoding=3,
                        mime=embed_mime,
                        type=APIC_TYPE_FRONT_COVER,
                        desc='Cover',
                        data=embed_data,
                    ))
                    if verbose:
                        size_desc = f"{len(embed_data) / 1024:.1f} KB ({embed_mime})"
                        if artwork_size > 0 and len(embed_data) != len(cover_data):
                            size_desc += f" (resized to {artwork_size}px)"
                        self.logger.debug(f"  → Cover art: {size_desc}")
                else:
                    if verbose:
                        self.logger.debug("  → Cover art: (none found in source)")

            # Save using profile-driven ID3 version and v1 settings
            tags.save(str(output_file),
                      v2_version=self.output_profile.id3_version,
                      v1=0 if self.output_profile.strip_id3v1 else 1)

            if verbose:
                self.logger.debug("Tags AFTER conversion (copied from source):")
                self.logger.debug(f"  → Title:  '{title}'")
                self.logger.debug(f"  → Artist: '{artist}'")
                self.logger.debug(f"  → Album:  '{album}'")
                self.logger.debug(f"Output size: {output_file.stat().st_size / 1024:.1f} KB")

            if already_exists and force:
                self.stats.increment('overwritten')
                msg = f"[{count}/{self.stats.total_found}] Overwritten: {output_filename}"
            else:
                self.stats.increment('converted')
                msg = f"[{count}/{self.stats.total_found}] Converted: {output_filename}"
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

    def convert(self, input_dir, output_dir, force=False, dry_run=False, verbose=False):
        """
        Recursively scan input_dir for .m4a files, convert them to MP3
        using ffmpeg, and save all output files flat into output_dir.
        Tags are written immediately after each conversion.
        """
        start_time = time.time()

        input_path = Path(input_dir)
        output_path = Path(output_dir)

        if input_path.resolve() == output_path.resolve():
            self.logger.error("Input and output directories cannot be the same")
            return ConversionResult(
                success=False, input_dir=str(input_dir), output_dir=str(output_dir),
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
                success=True, input_dir=str(input_dir), output_dir=str(output_dir),
                duration=0, quality_preset=self.quality_preset,
                quality_mode=self.quality_settings['mode'],
                quality_value=self.quality_settings['value'],
                workers=self.workers, total_found=0, converted=0,
                overwritten=0, skipped=0, errors=0)

        self.stats.total_found = len(m4a_files)
        self.logger.info(f"Found {self.stats.total_found} .m4a file(s) (recursive)")
        self.logger.info(f"Output directory: '{output_dir}' ({display_name(self.output_profile.directory_structure)})")

        if force:
            self.logger.info("Force mode enabled — existing files will be overwritten")

        if not dry_run:
            output_path.mkdir(parents=True, exist_ok=True)

        # Determine effective worker count
        effective_workers = min(self.workers, self.stats.total_found)

        progress = _DisplayProgress(
            self.display_handler, total=self.stats.total_found, desc="Converting",
        )

        try:
            if effective_workers > 1:
                self.logger.info(f"Using {effective_workers} parallel workers")

                with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                    futures = {}
                    for input_file in m4a_files:
                        if _is_cancelled(self.cancel_event):
                            break
                        futures[executor.submit(
                            self._convert_single_file,
                            input_file, input_path, output_path,
                            force, dry_run, verbose, progress
                        )] = input_file

                    for future in as_completed(futures):
                        if _is_cancelled(self.cancel_event):
                            for f in futures:
                                f.cancel()
                            self.logger.warn("Conversion cancelled by user")
                            break
                        # Exceptions are already handled inside _convert_single_file,
                        # but catch any unexpected errors from the future itself
                        try:
                            future.result()
                        except Exception as e:
                            input_file = futures[future]
                            self.logger.error(f"Unexpected error processing '{input_file.name}': {e}")
                            self.stats.increment('errors')
            else:
                for input_file in m4a_files:
                    if _is_cancelled(self.cancel_event):
                        self.logger.warn("Conversion cancelled by user")
                        break
                    self._convert_single_file(
                        input_file, input_path, output_path,
                        force, dry_run, verbose, progress
                    )
        finally:
            progress.close()

        duration = time.time() - start_time

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

    def __init__(self, logger=None, venv_python=None, cookie_path='cookies.txt',
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

        cmd = [
            self.venv_python, "-m", "gamdl",
            "--log-level", "INFO",  # Show download progress, suppress DEBUG
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

    def __init__(self, cookie_path='cookies.txt', logger=None, prompt_handler=None):
        self.cookie_path = Path(cookie_path)
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
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
                return True
            else:
                self.logger.error(f"Saved cookies are not valid: {status.reason}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")
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
# Section 8: USB Sync Module
# ══════════════════════════════════════════════════════════════════

class USBSyncStatistics:
    """Tracks USB sync operation statistics."""

    def __init__(self):
        self.files_found = 0         # Total files to copy
        self.files_copied = 0        # Successfully copied
        self.files_skipped = 0       # Files skipped (unchanged)
        self.files_failed = 0        # Copy failures


class USBManager:
    """Manages USB drive detection and file copying."""

    def __init__(self, logger=None, excluded_volumes=None, prompt_handler=None,
                 display_handler=None, cancel_event=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.excluded_volumes = excluded_volumes or EXCLUDED_USB_VOLUMES

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

    def sync_to_usb(self, source_dir, usb_dir=DEFAULT_USB_DIR, dry_run=False, volume=None):
        """
        Copy files from source_dir to USB drive with incremental sync.
        Only copies new or modified files, skips unchanged files.
        Returns USBSyncResult.

        Args:
            volume: Pre-selected volume name. Skips interactive selection if provided.
        """
        start_time = time.time()
        stats = USBSyncStatistics()
        source_path = Path(source_dir)

        if not source_path.exists():
            self.logger.error(f"Source directory does not exist: {source_path}")
            return USBSyncResult(success=False, source=str(source_dir),
                                 destination='', volume_name='', duration=0)

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

        # Select USB drive (skip interactive prompt if volume pre-selected)
        if volume is None:
            volume = self.select_usb_drive()
        if not volume:
            return USBSyncResult(success=False, source=str(source_dir),
                                 destination='', volume_name='', duration=0)

        dest = self._get_usb_base_path(volume) / usb_dir

        self.logger.info(f"Syncing {source_path} to {dest}")

        if dry_run:
            self.logger.dry_run(f"Would create directory: {dest}")
            # Simulate incremental check
            for src_file in mp3_files:
                rel_path = src_file.relative_to(source_path) if source_path.is_dir() else src_file.name
                dst_file = dest / rel_path
                if self._should_copy_file(src_file, dst_file):
                    self.logger.dry_run(f"Would copy: {src_file.name}")
                    stats.files_copied += 1
                else:
                    if self.logger.verbose:
                        self.logger.dry_run(f"Would skip (unchanged): {src_file.name}")
                    stats.files_skipped += 1
            self.logger.dry_run("Would prompt to eject USB drive after copy")
            duration = time.time() - start_time

            return USBSyncResult(
                success=True, source=str(source_path), destination=str(dest),
                volume_name=volume, duration=duration, files_found=stats.files_found,
                files_copied=stats.files_copied, files_skipped=stats.files_skipped,
                files_failed=stats.files_failed)

        # Create destination directory
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create destination directory: {e}")
            stats.files_failed = stats.files_found
            duration = time.time() - start_time

            return USBSyncResult(
                success=False, source=str(source_path), destination=str(dest),
                volume_name=volume, duration=duration, files_found=stats.files_found,
                files_copied=stats.files_copied, files_skipped=stats.files_skipped,
                files_failed=stats.files_failed)

        # Copy files with incremental check
        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Syncing to USB",
        )

        try:
            for src_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("USB sync cancelled by user")
                    break
                try:
                    # Preserve directory structure relative to source
                    if source_path.is_dir():
                        rel_path = src_file.relative_to(source_path)
                    else:
                        rel_path = src_file.name
                    dst_file = dest / rel_path

                    # Create parent directory if needed
                    dst_file.parent.mkdir(parents=True, exist_ok=True)

                    # Incremental check
                    if self._should_copy_file(src_file, dst_file):
                        shutil.copy2(src_file, dst_file)  # Preserves timestamps
                        stats.files_copied += 1
                        if self.logger.verbose:
                            self.logger.info(f"Copied: {src_file.name}")
                        else:
                            self.logger.file_info(f"Copied: {src_file.name}")
                    else:
                        stats.files_skipped += 1
                        if self.logger.verbose:
                            self.logger.info(f"Skipped (unchanged): {src_file.name}")
                        else:
                            self.logger.file_info(f"Skipped (unchanged): {src_file.name}")

                except Exception as e:
                    stats.files_failed += 1
                    self.logger.error(f"Failed to copy {src_file.name}: {e}")

                progress.update(1)
        finally:
            progress.close()

        # Log summary
        self.logger.ok("Sync complete")
        duration = time.time() - start_time
        # Prompt to eject USB drive after successful copy
        if not dry_run:
            self._prompt_and_eject_usb(volume)
            # Note: eject operation is non-critical, doesn't affect return status

        # Success if no failures (skipped files are OK)
        return USBSyncResult(
            success=stats.files_failed == 0, source=str(source_path),
            destination=str(dest), volume_name=volume, duration=duration,
            files_found=stats.files_found, files_copied=stats.files_copied,
            files_skipped=stats.files_skipped, files_failed=stats.files_failed)

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


# ══════════════════════════════════════════════════════════════════
# Section 8A: Library Summary Management
# ══════════════════════════════════════════════════════════════════

class PlaylistSummary:
    """Statistics for a single playlist."""

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.file_count = 0
        self.total_size_bytes = 0
        self.avg_file_size_mb = 0.0
        self.last_modified = None  # datetime

        # Tag integrity (from sampling)
        self.sample_files_checked = 0
        self.sample_files_with_tags = 0

        # Cover art stats
        self.files_with_cover_art = 0
        self.files_without_cover_art = 0
        self.files_with_original_cover_art = 0
        self.files_with_resized_cover_art = 0


class MusicLibraryStats:
    """Statistics for the source music/ directory (M4A library)."""

    def __init__(self):
        self.total_playlists = 0
        self.total_files = 0
        self.total_size_bytes = 0
        self.total_exported = 0
        self.total_unconverted = 0
        self.scan_duration = 0.0
        self.playlists = []  # List of dicts: {name, m4a_count, size_bytes, exported_count, unconverted_count}


class LibrarySummaryStatistics:
    """Statistics for the entire export library."""

    def __init__(self):
        # Aggregate stats
        self.total_playlists = 0
        self.total_files = 0
        self.total_size_bytes = 0
        self.scan_duration = 0.0

        # Tag integrity (from sampling)
        self.sample_size = 0
        self.files_with_protection_tags = 0
        self.files_missing_protection_tags = 0

        # Cover art stats
        self.files_with_cover_art = 0
        self.files_without_cover_art = 0
        self.files_with_original_cover_art = 0
        self.files_with_resized_cover_art = 0

        # Per-playlist breakdown
        self.playlists = []  # List of PlaylistSummary objects


class SummaryManager:
    """Generates summary statistics for the export directory."""

    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.stats = LibrarySummaryStatistics()

    def generate_summary(self, export_dir='export/', detailed=False, quick=False,
                         dry_run=False, music_dir=None, export_profile=None,
                         no_library=False):
        """
        Generate and display library stats and playlist summary.

        Args:
            export_dir: Directory to analyze
            detailed: Show detailed statistics
            quick: Show only aggregate statistics
            dry_run: Preview mode (not applicable for summary)
            music_dir: Music source directory for library stats
            export_profile: Profile name for conversion status comparison
            no_library: Skip music directory scan

        Returns:
            LibrarySummaryResult
        """
        # Scan music library stats (unless skipped)
        music_stats = None
        if not no_library:
            music_stats = self.scan_music_library(
                music_dir=music_dir,
                export_profile=export_profile,
            )

        start_time = time.time()

        # Check if directory exists
        export_path = Path(export_dir)
        if not export_path.exists():
            mode = "quick" if quick else ("detailed" if detailed else "default")
            return LibrarySummaryResult(
                success=True, export_dir=str(export_dir), scan_duration=0,
                mode=mode, music_library_stats=music_stats)

        # Scan playlists
        playlist_dirs = self._scan_playlists(export_path)

        if not playlist_dirs:
            mode = "quick" if quick else ("detailed" if detailed else "default")
            return LibrarySummaryResult(
                success=True, export_dir=str(export_dir), scan_duration=0,
                mode=mode, music_library_stats=music_stats)

        # Analyze each playlist
        for playlist_dir in playlist_dirs:
            playlist_summary = self._analyze_playlist(playlist_dir)
            if playlist_summary:
                self.stats.playlists.append(playlist_summary)

        # Calculate aggregate statistics
        self.stats.total_playlists = len(self.stats.playlists)
        self.stats.total_files = sum(p.file_count for p in self.stats.playlists)
        self.stats.total_size_bytes = sum(p.total_size_bytes for p in self.stats.playlists)

        # Check tag integrity (always checks all files)
        self._check_tag_integrity()

        # Record scan duration
        self.stats.scan_duration = time.time() - start_time

        mode = "quick" if quick else ("detailed" if detailed else "default")
        avg_size = (self.stats.total_size_bytes / self.stats.total_files
                    if self.stats.total_files > 0 else 0.0)
        return LibrarySummaryResult(
            success=True,
            export_dir=str(export_dir),
            scan_duration=self.stats.scan_duration,
            mode=mode,
            total_playlists=self.stats.total_playlists,
            total_files=self.stats.total_files,
            total_size_bytes=self.stats.total_size_bytes,
            avg_file_size=avg_size,
            files_with_protection_tags=self.stats.files_with_protection_tags,
            files_missing_protection_tags=self.stats.files_missing_protection_tags,
            sample_size=self.stats.sample_size,
            files_with_cover_art=self.stats.files_with_cover_art,
            files_without_cover_art=self.stats.files_without_cover_art,
            files_with_original_cover_art=self.stats.files_with_original_cover_art,
            files_with_resized_cover_art=self.stats.files_with_resized_cover_art,
            playlist_summaries=[p for p in self.stats.playlists],
            music_library_stats=music_stats,
        )

    def _scan_playlists(self, export_path):
        """Discover playlist directories in export directory."""
        playlist_dirs = []

        try:
            for item in export_path.iterdir():
                # Skip files, only process directories
                if item.is_dir() and not item.name.startswith('.'):
                    playlist_dirs.append(item)
        except PermissionError as e:
            self.logger.warn(f"Permission denied accessing export directory: {e}")
        except Exception as e:
            self.logger.warn(f"Error scanning export directory: {e}")

        # Sort by name for consistent output
        return sorted(playlist_dirs, key=lambda p: p.name)

    def _analyze_playlist(self, playlist_dir):
        """Analyze statistics for a single playlist directory."""
        try:
            mp3_files = list(playlist_dir.rglob("*.mp3"))

            if not mp3_files:
                return None  # Skip empty playlists

            summary = PlaylistSummary(playlist_dir.name, str(playlist_dir))
            summary.file_count = len(mp3_files)

            # Calculate total size and find most recent modification
            total_size = 0
            latest_mtime = 0

            for mp3_file in mp3_files:
                try:
                    stat = mp3_file.stat()
                    total_size += stat.st_size
                    if stat.st_mtime > latest_mtime:
                        latest_mtime = stat.st_mtime
                except Exception as e:
                    self.logger.debug(f"Error reading stats for {mp3_file}: {e}")

            summary.total_size_bytes = total_size
            if summary.file_count > 0:
                summary.avg_file_size_mb = (total_size / summary.file_count) / (1024 * 1024)

            if latest_mtime > 0:
                summary.last_modified = datetime.fromtimestamp(latest_mtime)

            return summary

        except PermissionError as e:
            self.logger.warn(f"Permission denied accessing playlist '{playlist_dir.name}': {e}")
            return None
        except Exception as e:
            self.logger.warn(f"Error analyzing playlist '{playlist_dir.name}': {e}")
            return None

    def _check_tag_integrity(self):
        """Check all files for TXXX protection tags and cover art."""
        import hashlib

        from mutagen.id3 import ID3, ID3NoHeaderError

        for playlist in self.stats.playlists:
            playlist_path = Path(playlist.path)
            mp3_files = list(playlist_path.rglob("*.mp3"))

            # Check all files in this playlist
            for mp3_file in mp3_files:
                playlist.sample_files_checked += 1

                try:
                    tags = ID3(mp3_file)

                    # Check for TXXX protection frames
                    has_original_title = _txxx_exists(tags, TXXX_ORIGINAL_TITLE)
                    has_original_artist = _txxx_exists(tags, TXXX_ORIGINAL_ARTIST)
                    has_original_album = _txxx_exists(tags, TXXX_ORIGINAL_ALBUM)

                    if has_original_title and has_original_artist and has_original_album:
                        playlist.sample_files_with_tags += 1
                        self.stats.files_with_protection_tags += 1
                    else:
                        self.stats.files_missing_protection_tags += 1

                    # Check for cover art (APIC frame)
                    apic_frame = None
                    for key in tags:
                        if key.startswith("APIC"):
                            apic_frame = tags[key]
                            break

                    if apic_frame is not None:
                        playlist.files_with_cover_art += 1
                        self.stats.files_with_cover_art += 1

                        # Check if cover art is original or resized
                        original_hash = _get_txxx(tags, TXXX_ORIGINAL_COVER_ART_HASH)
                        if original_hash:
                            current_hash = hashlib.sha256(apic_frame.data).hexdigest()[:16]
                            if current_hash == original_hash:
                                playlist.files_with_original_cover_art += 1
                                self.stats.files_with_original_cover_art += 1
                            else:
                                playlist.files_with_resized_cover_art += 1
                                self.stats.files_with_resized_cover_art += 1
                    else:
                        playlist.files_without_cover_art += 1
                        self.stats.files_without_cover_art += 1

                except ID3NoHeaderError:
                    self.logger.debug(f"No ID3 tags found in {mp3_file}")
                    self.stats.files_missing_protection_tags += 1
                    playlist.files_without_cover_art += 1
                    self.stats.files_without_cover_art += 1
                except Exception as e:
                    self.logger.debug(f"Error reading tags from {mp3_file}: {e}")
                    self.stats.files_missing_protection_tags += 1
                    playlist.files_without_cover_art += 1
                    self.stats.files_without_cover_art += 1

        # Calculate aggregate sample size
        self.stats.sample_size = sum(p.sample_files_checked for p in self.stats.playlists)


    def scan_music_library(self, music_dir=None, export_profile=None):
        """
        Scan the music/ directory for source M4A library stats.

        Args:
            music_dir: Path to music directory (default: DEFAULT_MUSIC_DIR)
            export_profile: Profile name to check export status against

        Returns:
            MusicLibraryStats or None if directory doesn't exist
        """
        music_dir = music_dir or DEFAULT_MUSIC_DIR
        music_path = Path(music_dir)

        if not music_path.exists():
            return None

        stats = MusicLibraryStats()
        start_time = time.time()

        try:
            for item in sorted(music_path.iterdir(), key=lambda p: p.name):
                if not item.is_dir() or item.name.startswith('.'):
                    continue

                playlist_name = item.name
                m4a_count = 0
                size_bytes = 0

                # Walk recursively — music/ has nested Artist/Album/Track.m4a structure
                for root, _dirs, files in os.walk(item):
                    for f in files:
                        if f.lower().endswith('.m4a'):
                            m4a_count += 1
                            try:
                                size_bytes += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass

                if m4a_count == 0:
                    continue

                # Check export status
                exported_count = 0
                if export_profile:
                    export_path = Path(get_export_dir(export_profile, playlist_name))
                    if export_path.exists():
                        exported_count = len(list(export_path.rglob('*.mp3')))

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
            self.logger.warn(f"Permission denied accessing music directory: {e}")
        except Exception as e:
            self.logger.warn(f"Error scanning music directory: {e}")

        stats.total_playlists = len(stats.playlists)
        stats.scan_duration = time.time() - start_time

        return stats

    def _format_size(self, bytes_size):
        """Format bytes to human-readable size."""
        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


# ══════════════════════════════════════════════════════════════════
# Section 8B: Cover Art Management
# ══════════════════════════════════════════════════════════════════

class CoverArtManager:
    """Manages cover art operations: embed, extract, update, strip."""

    def __init__(self, logger=None, output_profile=None, display_handler=None,
                 cancel_event=None):
        self.logger = logger or Logger()
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event

    def embed(self, directory, source_dir=None, force=False, dry_run=False, verbose=False):
        """
        Embed cover art into existing MP3s from matching M4A source files.
        Auto-derives source dir from export/ → music/ if not specified.
        """
        import hashlib

        from mutagen.id3 import APIC, ID3, TXXX, ID3NoHeaderError

        start_time = time.time()
        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return CoverArtResult(success=False, action="embed", directory=str(directory), duration=0, errors=1)

        # Auto-derive source directory
        if source_dir is None:
            # export/profile/PlaylistName → music/PlaylistName
            # Strip export base + optional profile subdirectory
            dir_str = str(dir_path)
            if dir_str.startswith(DEFAULT_EXPORT_DIR + "/"):
                remainder = dir_str[len(DEFAULT_EXPORT_DIR) + 1:]  # "profile/Playlist" or "Playlist"
                # Check if next segment is a known profile name
                parts = remainder.split("/", 1)
                if len(parts) == 2 and parts[0] in OUTPUT_PROFILES:
                    # export/profile/Playlist → music/Playlist
                    source_dir = f"{DEFAULT_MUSIC_DIR}/{parts[1]}"
                else:
                    # export/Playlist (legacy flat layout)
                    source_dir = f"{DEFAULT_MUSIC_DIR}/{remainder}"
            else:
                self.logger.error("Cannot auto-derive source directory. Use --source to specify.")
                return CoverArtResult(success=False, action="embed", directory=str(directory),
                                      duration=time.time() - start_time, errors=1)

        source_path = Path(source_dir)
        if not source_path.exists():
            self.logger.error(f"Source directory not found: '{source_dir}'")
            return CoverArtResult(success=False, action="embed", directory=str(directory),
                                  duration=time.time() - start_time, errors=1,
                                  source_dir=str(source_dir))

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return CoverArtResult(success=True, action="embed", directory=str(directory),
                                  duration=time.time() - start_time,
                                  source_dir=str(source_dir))

        # Build lookup of M4A files by profile-aware filename
        m4a_lookup = {}
        for m4a_file in source_path.rglob("*.m4a"):
            if m4a_file.name.startswith('._'):
                continue
            try:
                title, artist, _ = read_m4a_tags(m4a_file)
                safe_artist = sanitize_filename(artist)
                safe_title = sanitize_filename(title)
                fmt = self.output_profile.filename_format
                if fmt == "title-only":
                    key = f"{safe_title}.mp3"
                else:
                    key = f"{safe_artist} - {safe_title}.mp3"
                m4a_lookup[key] = m4a_file
            except Exception:
                continue

        self.logger.info(f"Found {len(mp3_files)} MP3 files, {len(m4a_lookup)} M4A sources")

        embedded = 0
        skipped = 0
        errors = 0
        no_source = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Embedding cover art",
        )

        try:
            for mp3_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Cover art embed cancelled by user")
                    break
                try:
                    # Find matching M4A source
                    m4a_file = m4a_lookup.get(mp3_file.name)
                    if not m4a_file:
                        no_source += 1
                        if verbose:
                            self.logger.debug(f"No M4A source for: {mp3_file.name}")
                        progress.update(1)
                        continue

                    # Read cover art from M4A
                    cover_data, cover_mime = read_m4a_cover_art(m4a_file)
                    if not cover_data:
                        skipped += 1
                        if verbose:
                            self.logger.debug(f"No cover art in source: {m4a_file.name}")
                        progress.update(1)
                        continue

                    # Check if MP3 already has cover art
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        tags = ID3()

                    apic_keys = [key for key in tags if key.startswith("APIC")]

                    if apic_keys:
                        if not force:
                            skipped += 1
                            if verbose:
                                self.logger.debug(f"Already has cover art: {mp3_file.name}")
                            progress.update(1)
                            continue

                        # Force mode: check if current art already matches original
                        original_hash = _get_txxx(tags, TXXX_ORIGINAL_COVER_ART_HASH)
                        if original_hash:
                            current_hash = hashlib.sha256(tags[apic_keys[0]].data).hexdigest()[:16]
                            if current_hash == original_hash:
                                skipped += 1
                                if verbose:
                                    self.logger.debug(f"Already has original cover art: {mp3_file.name}")
                                progress.update(1)
                                continue

                    if dry_run:
                        action = "Would re-embed" if apic_keys else "Would embed"
                        self.logger.dry_run(f"{action} cover art: {mp3_file.name} ({len(cover_data) / 1024:.1f} KB)")
                        progress.update(1)
                        continue

                    # Remove existing APIC frames before embedding
                    for key in apic_keys:
                        del tags[key]

                    # Embed cover art
                    tags.add(APIC(
                        encoding=3,
                        mime=cover_mime,
                        type=APIC_TYPE_FRONT_COVER,
                        desc='Cover',
                        data=cover_data,
                    ))

                    # Store hash with hard-gate protection
                    if not _txxx_exists(tags, TXXX_ORIGINAL_COVER_ART_HASH):
                        art_hash = hashlib.sha256(cover_data).hexdigest()[:16]
                        tags.add(TXXX(encoding=3,
                                      desc=TXXX_ORIGINAL_COVER_ART_HASH,
                                      text=[art_hash]))

                    tags.save(str(mp3_file), v2_version=3, v1=0)
                    embedded += 1

                    if verbose:
                        self.logger.info(f"Embedded: {mp3_file.name} ({len(cover_data) / 1024:.1f} KB)")

                    progress.update(1)

                except Exception as e:
                    errors += 1
                    self.logger.error(f"Failed to embed art for '{mp3_file.name}': {e}")
                    progress.update(1)
        finally:
            progress.close()

        return CoverArtResult(
            success=errors == 0, action="embed", directory=str(directory),
            duration=time.time() - start_time,
            files_processed=len(mp3_files), files_modified=embedded,
            files_skipped=skipped, errors=errors,
            source_dir=str(source_dir), no_source=no_source)

    def extract(self, directory, output_dir=None, dry_run=False, verbose=False):
        """Extract cover art from MP3 files to image files."""
        from mutagen.id3 import ID3, ID3NoHeaderError

        start_time = time.time()
        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return CoverArtResult(success=False, action="extract", directory=str(directory), duration=0, errors=1)

        # Default output to same directory
        if output_dir is None:
            out_path = dir_path / "cover-art"
        else:
            out_path = Path(output_dir)

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return CoverArtResult(success=True, action="extract", directory=str(directory),
                                  duration=time.time() - start_time)

        if not dry_run:
            out_path.mkdir(parents=True, exist_ok=True)

        extracted = 0
        skipped = 0
        errors = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Extracting cover art",
        )

        try:
            for mp3_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Cover art extract cancelled by user")
                    break
                try:
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        skipped += 1
                        progress.update(1)
                        continue

                    # Find APIC frame
                    apic_frame = None
                    for key, frame in tags.items():
                        if key.startswith("APIC"):
                            apic_frame = frame
                            break

                    if not apic_frame:
                        skipped += 1
                        if verbose:
                            self.logger.debug(f"No cover art: {mp3_file.name}")
                        progress.update(1)
                        continue

                    # Determine file extension
                    ext = ".jpg" if apic_frame.mime == APIC_MIME_JPEG else ".png"
                    stem = mp3_file.stem
                    out_file = out_path / f"{stem}{ext}"

                    if dry_run:
                        self.logger.dry_run(f"Would extract: {out_file.name} ({len(apic_frame.data) / 1024:.1f} KB)")
                        progress.update(1)
                        continue

                    out_file.write_bytes(apic_frame.data)
                    extracted += 1

                    if verbose:
                        self.logger.info(f"Extracted: {out_file.name} ({len(apic_frame.data) / 1024:.1f} KB)")

                    progress.update(1)

                except Exception as e:
                    errors += 1
                    self.logger.error(f"Failed to extract art from '{mp3_file.name}': {e}")
                    progress.update(1)
        finally:
            progress.close()

        return CoverArtResult(
            success=errors == 0, action="extract", directory=str(directory),
            duration=time.time() - start_time,
            files_processed=len(mp3_files), files_modified=extracted,
            files_skipped=skipped, errors=errors)

    def update(self, directory, image_path, dry_run=False, verbose=False):
        """Replace cover art on all MP3s in a directory from a single image file."""
        from mutagen.id3 import APIC, ID3, ID3NoHeaderError

        start_time = time.time()
        dir_path = Path(directory)
        img_path = Path(image_path)

        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return CoverArtResult(success=False, action="update", directory=str(directory),
                                  duration=0, errors=1, image_path=str(image_path))

        if not img_path.exists():
            self.logger.error(f"Image file not found: '{image_path}'")
            return CoverArtResult(success=False, action="update", directory=str(directory),
                                  duration=0, errors=1, image_path=str(image_path))

        # Detect MIME type from extension
        ext = img_path.suffix.lower()
        if ext in ('.jpg', '.jpeg'):
            mime_type = APIC_MIME_JPEG
        elif ext == '.png':
            mime_type = APIC_MIME_PNG
        else:
            self.logger.error(f"Unsupported image format: '{ext}' (use .jpg or .png)")
            return CoverArtResult(success=False, action="update", directory=str(directory),
                                  duration=time.time() - start_time, errors=1,
                                  image_path=str(image_path))

        cover_data = img_path.read_bytes()
        self.logger.info(f"Image: {img_path.name} ({len(cover_data) / 1024:.1f} KB, {mime_type})")

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return CoverArtResult(success=True, action="update", directory=str(directory),
                                  duration=time.time() - start_time, image_path=str(image_path))

        updated = 0
        errors = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Updating cover art",
        )

        try:
            for mp3_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Cover art update cancelled by user")
                    break
                try:
                    if dry_run:
                        self.logger.dry_run(f"Would update cover art: {mp3_file.name}")
                        progress.update(1)
                        continue

                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        tags = ID3()

                    # Remove existing APIC frames
                    for key in list(tags.keys()):
                        if key.startswith("APIC"):
                            del tags[key]

                    # Add new cover art
                    tags.add(APIC(
                        encoding=3,
                        mime=mime_type,
                        type=APIC_TYPE_FRONT_COVER,
                        desc='Cover',
                        data=cover_data,
                    ))

                    tags.save(str(mp3_file), v2_version=3, v1=0)
                    updated += 1

                    if verbose:
                        self.logger.info(f"Updated: {mp3_file.name}")

                    progress.update(1)

                except Exception as e:
                    errors += 1
                    self.logger.error(f"Failed to update art for '{mp3_file.name}': {e}")
                    progress.update(1)
        finally:
            progress.close()

        return CoverArtResult(
            success=errors == 0, action="update", directory=str(directory),
            duration=time.time() - start_time,
            files_processed=len(mp3_files), files_modified=updated,
            errors=errors, image_path=str(image_path))

    def strip(self, directory, dry_run=False, verbose=False):
        """Remove cover art from all MP3s in a directory."""
        from mutagen.id3 import ID3, ID3NoHeaderError

        start_time = time.time()
        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return CoverArtResult(
                success=False, action="strip", directory=str(directory),
                duration=time.time() - start_time,
                files_processed=0, files_modified=0, files_skipped=0, errors=1)

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return CoverArtResult(
                success=True, action="strip", directory=str(directory),
                duration=time.time() - start_time,
                files_processed=0, files_modified=0, files_skipped=0, errors=0)

        stripped = 0
        skipped = 0
        errors = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Stripping cover art",
        )

        try:
            for mp3_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Cover art strip cancelled by user")
                    break
                try:
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        skipped += 1
                        progress.update(1)
                        continue

                    # Find and remove APIC frames
                    apic_keys = [key for key in tags if key.startswith("APIC")]

                    if not apic_keys:
                        skipped += 1
                        if verbose:
                            self.logger.debug(f"No cover art to strip: {mp3_file.name}")
                        progress.update(1)
                        continue

                    if dry_run:
                        self.logger.dry_run(f"Would strip cover art: {mp3_file.name}")
                        progress.update(1)
                        continue

                    for key in apic_keys:
                        del tags[key]

                    tags.save(str(mp3_file), v2_version=3, v1=0)
                    stripped += 1

                    if verbose:
                        self.logger.info(f"Stripped: {mp3_file.name}")

                    progress.update(1)

                except Exception as e:
                    errors += 1
                    self.logger.error(f"Failed to strip art from '{mp3_file.name}': {e}")
                    progress.update(1)
        finally:
            progress.close()

        return CoverArtResult(
            success=errors == 0, action="strip", directory=str(directory),
            duration=time.time() - start_time,
            files_processed=stripped + skipped + errors,
            files_modified=stripped, files_skipped=skipped, errors=errors)

    def resize(self, directory, max_size, dry_run=False, verbose=False):
        """Resize embedded cover art to a maximum dimension, preserving aspect ratio."""
        import io

        from mutagen.id3 import ID3, ID3NoHeaderError
        from PIL import Image

        start_time = time.time()
        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return CoverArtResult(
                success=False, action="resize", directory=str(directory),
                duration=time.time() - start_time,
                files_processed=0, files_modified=0, files_skipped=0, errors=1)

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return CoverArtResult(
                success=True, action="resize", directory=str(directory),
                duration=time.time() - start_time,
                files_processed=0, files_modified=0, files_skipped=0, errors=0)

        resized = 0
        skipped_small = 0
        skipped_no_art = 0
        errors = 0
        total_before = 0
        total_after = 0

        progress = _DisplayProgress(
            self.display_handler, total=len(mp3_files), desc="Resizing cover art",
        )

        try:
            for mp3_file in mp3_files:
                if _is_cancelled(self.cancel_event):
                    self.logger.warn("Cover art resize cancelled by user")
                    break
                try:
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        skipped_no_art += 1
                        progress.update(1)
                        continue

                    # Find APIC frame
                    apic_frame = None
                    for key in tags:
                        if key.startswith("APIC"):
                            apic_frame = tags[key]
                            break

                    if apic_frame is None:
                        skipped_no_art += 1
                        if verbose:
                            self.logger.debug(f"No cover art: {mp3_file.name}")
                        progress.update(1)
                        continue

                    original_size = len(apic_frame.data)
                    total_before += original_size

                    # Open image and check dimensions
                    img = Image.open(io.BytesIO(apic_frame.data))
                    width, height = img.size

                    if width <= max_size and height <= max_size:
                        skipped_small += 1
                        total_after += original_size
                        if verbose:
                            self.logger.debug(f"Already small enough ({width}x{height}): {mp3_file.name}")
                        progress.update(1)
                        continue

                    if dry_run:
                        # Estimate new dimensions
                        ratio = min(max_size / width, max_size / height)
                        new_w = int(width * ratio)
                        new_h = int(height * ratio)
                        self.logger.dry_run(
                            f"Would resize: {mp3_file.name} "
                            f"({width}x{height} → {new_w}x{new_h}, "
                            f"{original_size / 1024:.0f} KB)"
                        )
                        progress.update(1)
                        continue

                    # Resize using shared helper
                    new_data, mime = resize_cover_art_bytes(
                        apic_frame.data, max_size, apic_frame.mime
                    )
                    new_size = len(new_data)
                    total_after += new_size

                    # Compute new dimensions for logging
                    new_img = Image.open(io.BytesIO(new_data))
                    new_w, new_h = new_img.size

                    # Replace APIC frame data
                    apic_frame.data = new_data
                    apic_frame.mime = mime
                    tags.save(str(mp3_file), v2_version=3, v1=0)
                    resized += 1

                    if verbose:
                        self.logger.info(
                            f"Resized: {mp3_file.name} "
                            f"({width}x{height} → {new_w}x{new_h}, "
                            f"{original_size / 1024:.0f} KB → {new_size / 1024:.0f} KB)"
                        )

                    progress.update(1)

                except Exception as e:
                    errors += 1
                    self.logger.error(f"Failed to resize art in '{mp3_file.name}': {e}")
                    progress.update(1)
        finally:
            progress.close()

        return CoverArtResult(
            success=errors == 0, action="resize", directory=str(directory),
            duration=time.time() - start_time,
            files_processed=resized + skipped_small + skipped_no_art + errors,
            files_modified=resized, files_skipped=skipped_small + skipped_no_art,
            errors=errors)


# ══════════════════════════════════════════════════════════════════
# Section 8b: Data Management (Deletion)
# ══════════════════════════════════════════════════════════════════

class DataManager:
    """Manages playlist data lifecycle (deletion, cleanup)."""

    def __init__(self, logger=None, config=None, prompt_handler=None, output_profile=None):
        self.logger = logger or Logger()
        self.config = config or ConfigManager(logger=self.logger)
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]

    def delete_playlist_data(self, playlist_key, delete_source=True, delete_export=True,
                             remove_config=False, dry_run=False):
        """Delete source M4A and/or export MP3 directories for a playlist.

        Returns DeleteResult with stats about what was deleted.
        """
        source_dir = Path(DEFAULT_MUSIC_DIR) / playlist_key
        export_dir = Path(get_export_dir(self.output_profile.name, playlist_key))

        errors = []
        files_deleted = 0
        bytes_freed = 0
        source_deleted = False
        export_deleted = False
        config_removed = False

        # Count files and sizes for each directory
        source_files = 0
        source_bytes = 0
        export_files = 0
        export_bytes = 0

        if delete_source and source_dir.exists():
            for f in source_dir.rglob('*'):
                if f.is_file():
                    source_files += 1
                    source_bytes += f.stat().st_size
        if delete_export and export_dir.exists():
            for f in export_dir.rglob('*'):
                if f.is_file():
                    export_files += 1
                    export_bytes += f.stat().st_size

        total_files = source_files + export_files
        total_bytes = source_bytes + export_bytes

        if total_files == 0 and not remove_config:
            self.logger.info(f"Nothing to delete for '{playlist_key}'")
            return DeleteResult(success=True, playlist_key=playlist_key, dry_run=dry_run)

        # Build summary for confirmation
        parts = []
        if source_files > 0:
            parts.append(f"{source_files} source files ({_format_bytes(source_bytes)})")
        if export_files > 0:
            parts.append(f"{export_files} export files ({_format_bytes(export_bytes)})")
        if remove_config:
            parts.append("config entry")

        summary = f"Delete {', '.join(parts)} for '{playlist_key}'?"
        self.logger.info(f"\n  {summary}")

        if dry_run:
            if delete_source and source_dir.exists():
                self.logger.info(f"  [DRY-RUN] Would delete: {source_dir}/ ({source_files} files, {_format_bytes(source_bytes)})")
            if delete_export and export_dir.exists():
                self.logger.info(f"  [DRY-RUN] Would delete: {export_dir}/ ({export_files} files, {_format_bytes(export_bytes)})")
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

        # Delete export directory
        if delete_export and export_dir.exists():
            try:
                shutil.rmtree(export_dir)
                export_deleted = True
                files_deleted += export_files
                bytes_freed += export_bytes
                self.logger.info(f"  Deleted export: {export_dir}/ ({export_files} files, {_format_bytes(export_bytes)})")
            except OSError as e:
                errors.append(f"Failed to delete {export_dir}: {e}")
                self.logger.error(errors[-1])

        # Remove config entry
        if remove_config:
            if self.config.remove_playlist(playlist_key):
                config_removed = True
                self.logger.info(f"  Removed config entry for '{playlist_key}'")
            else:
                self.logger.info(f"  Config entry for '{playlist_key}' not found (may not be configured)")

        return DeleteResult(
            success=len(errors) == 0,
            playlist_key=playlist_key,
            source_deleted=source_deleted,
            export_deleted=export_deleted,
            config_removed=config_removed,
            files_deleted=files_deleted,
            bytes_freed=bytes_freed,
            errors=errors)


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
        self.tagging_album = None
        self.tagging_artist = None

        # Cover art stats
        self.cover_art_embedded = 0
        self.cover_art_missing = 0

        # USB sync stats
        self.usb_success = False
        self.usb_destination = None
        self.usb_stats = None  # USBSyncStatistics object

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
        self.failed_stage = None  # "download", "convert", "tag", "usb-sync"
        self.download_stats = None  # DownloadStatistics
        self.conversion_stats = None  # ConversionStatistics
        self.tagging_stats = None  # TagStatistics
        self.usb_success = False
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
        result.usb_success = orchestrator_stats.usb_success
        result.duration = time.time() - orchestrator_stats.start_time

        self.playlist_results.append(result)
        self.total_playlists += 1
        if result.success:
            self.successful_playlists += 1
        else:
            self.failed_playlists += 1

        if orchestrator_stats.usb_destination:
            self.usb_destination = orchestrator_stats.usb_destination

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

            if result.tagging_stats:
                totals['title_updated'] += result.tagging_stats.title_updated
                totals['original_tags_stored'] += (
                    result.tagging_stats.title_stored +
                    result.tagging_stats.artist_stored +
                    result.tagging_stats.album_stored
                )

            if result.usb_success and result.conversion_stats:
                totals['files_on_usb'] += (
                    result.conversion_stats.converted +
                    result.conversion_stats.overwritten +
                    result.conversion_stats.skipped
                )

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
    """Coordinates multi-stage workflows: download → convert → tag → USB sync."""

    def __init__(self, logger=None, deps=None, config=None, quality_preset='lossless',
                 cookie_path='cookies.txt', workers=None, embed_cover_art=True,
                 output_profile=None, prompt_handler=None, display_handler=None,
                 cancel_event=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.deps = deps or DependencyChecker(self.logger)
        self.config = config or ConfigManager(logger=self.logger)
        self.stats = PipelineStatistics()
        self.quality_preset = quality_preset
        self.cookie_path = cookie_path
        self.workers = workers
        self.embed_cover_art = embed_cover_art
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]

    def run_full_pipeline(self, playlist=None, url=None, auto=False,
                         copy_to_usb=False, usb_dir=DEFAULT_USB_DIR,
                         dry_run=False, verbose=False, quality_preset=None,
                         validate_cookies=True, auto_refresh_cookies=False):
        """
        Execute the complete pipeline: download → convert → tag → USB sync.
        """
        self.stats.start_time = time.time()
        convert_result = None
        tag_result = None
        usb_result = None

        # ── Stage 1: Determine source ─────────────────────────────────
        if url:
            # Direct URL provided
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
            # Playlist key or index provided
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
            self.logger.error("Either --playlist or --url must be specified for pipeline")
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

        # ── Stage 2: Convert M4A → MP3 ────────────────────────────────
        self.logger.info("\n=== STAGE 2: Convert M4A → MP3 ===")
        music_dir = f"{DEFAULT_MUSIC_DIR}/{self.stats.playlist_key}"
        export_dir = get_export_dir(self.output_profile.name, self.stats.playlist_key)

        # Use quality_preset parameter if provided, otherwise use instance default
        preset = quality_preset if quality_preset is not None else self.quality_preset
        converter = Converter(self.logger, quality_preset=preset, workers=self.workers,
                              embed_cover_art=self.embed_cover_art,
                              output_profile=self.output_profile,
                              display_handler=self.display_handler,
                              cancel_event=self.cancel_event)
        convert_result = converter.convert(
            music_dir,
            export_dir,
            force=False,
            dry_run=dry_run,
            verbose=verbose
        )

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

        # ── Stage 3: Update tags ───────────────────────────────────────
        self.logger.info("\n=== STAGE 3: Update tags ===")

        # Determine album/artist from profile settings
        if self.output_profile.pipeline_album == "playlist_name":
            new_album = self.stats.playlist_name
        else:  # "original"
            new_album = None

        if self.output_profile.pipeline_artist == "various":
            new_artist = "Various"
        else:  # "original"
            new_artist = None

        tagger = TaggerManager(self.logger, output_profile=self.output_profile,
                               display_handler=self.display_handler,
                               cancel_event=self.cancel_event)
        tag_result = tagger.update_tags(
            export_dir,
            new_album=new_album,
            new_artist=new_artist,
            dry_run=dry_run,
            verbose=verbose
        )

        if tag_result.success:
            self.stats.stages_completed.append("tag")
            self.stats.tagging_stats = tagger.stats
            self.stats.tagging_album = new_album
            self.stats.tagging_artist = new_artist
        else:
            self.stats.stages_failed.append("tag")
            self.logger.error("Tagging stage failed")

        # ── Stage 3b: Cover art check ────────────────────────────────
        if self.embed_cover_art and self.output_profile.artwork_size != -1:
            self._check_and_embed_cover_art(export_dir, auto, dry_run, verbose)

        # ── Cancellation check before Stage 4 ────────────────────────
        if _is_cancelled(self.cancel_event):
            self.logger.warn("Pipeline cancelled by user")
            duration = time.time() - self.stats.start_time
            return PipelineResult(
                success=False, playlist_name=self.stats.playlist_name,
                playlist_key=self.stats.playlist_key, duration=duration,
                stages_completed=list(self.stats.stages_completed),
                stages_failed=["cancelled"],
                stages_skipped=list(self.stats.stages_skipped))

        # ── Stage 4: USB sync (optional) ───────────────────────────────
        if copy_to_usb:
            self.logger.info("\n=== STAGE 4: Copy to USB ===")
            usb_manager = USBManager(self.logger, prompt_handler=self.prompt_handler,
                                     display_handler=self.display_handler,
                                     cancel_event=self.cancel_event)
            usb_result = usb_manager.sync_to_usb(
                export_dir,
                usb_dir=usb_dir,
                dry_run=dry_run
            )

            if usb_result.success:
                self.stats.stages_completed.append("usb-sync")
                self.stats.usb_stats = {"files_copied": usb_result.files_copied, "files_skipped": usb_result.files_skipped}
                self.stats.usb_success = True
                if IS_MACOS:
                    usb_placeholder = f"/Volumes/[drive]/{usb_dir}"
                elif IS_LINUX:
                    usb_placeholder = f"/media/$USER/[drive]/{usb_dir}"
                else:
                    usb_placeholder = f"[drive]:/{usb_dir}"
                self.stats.usb_destination = usb_placeholder
            else:
                self.stats.stages_failed.append("usb-sync")
                self.logger.error("USB sync stage failed")

        duration = time.time() - self.stats.start_time
        return PipelineResult(
            success=len(self.stats.stages_failed) == 0,
            playlist_name=self.stats.playlist_name,
            playlist_key=self.stats.playlist_key,
            duration=duration,
            stages_completed=list(self.stats.stages_completed),
            stages_failed=list(self.stats.stages_failed),
            stages_skipped=list(self.stats.stages_skipped),
            download_result=self.stats.download_stats,
            conversion_result=convert_result,
            tag_result=tag_result,
            usb_result=usb_result,
            tagging_album=self.stats.tagging_album,
            tagging_artist=self.stats.tagging_artist,
            cover_art_embedded=self.stats.cover_art_embedded,
            cover_art_missing=self.stats.cover_art_missing,
            usb_destination=self.stats.usb_destination,
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

        output_dir = f"{DEFAULT_MUSIC_DIR}/{key}"

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

        output_dir = f"{DEFAULT_MUSIC_DIR}/{playlist.key}"

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

    def _check_and_embed_cover_art(self, export_dir, auto, dry_run, verbose):
        """Check for missing cover art and embed if needed."""
        from mutagen.id3 import ID3, ID3NoHeaderError

        export_path = Path(export_dir)
        if not export_path.exists():
            return

        mp3_files = list(export_path.rglob("*.mp3"))
        if not mp3_files:
            return

        # Scan for missing cover art
        missing = 0
        for mp3_file in mp3_files:
            try:
                tags = ID3(str(mp3_file))
                if not any(k.startswith("APIC") for k in tags):
                    missing += 1
            except (ID3NoHeaderError, Exception):
                missing += 1

        total = len(mp3_files)

        if missing == 0:
            self.stats.cover_art_embedded = total
            return
        playlist_name = export_path.name

        if dry_run:
            self.logger.dry_run(
                f"{playlist_name}: {missing}/{total} files missing cover art — would embed from source"
            )
            self.stats.cover_art_missing = missing
            return

        should_embed = False
        if auto:
            self.logger.info(f"\n  {playlist_name}: {missing}/{total} files missing cover art — auto-embedding")
            should_embed = True
        else:
            self.logger.info(f"\n  {playlist_name}: {missing}/{total} files missing cover art")
            should_embed = self.prompt_handler.confirm(
                "Embed cover art from source files?", default=True)

        if should_embed:
            cam = CoverArtManager(self.logger, output_profile=self.output_profile,
                                  display_handler=self.display_handler,
                                  cancel_event=self.cancel_event)
            cam.embed(export_dir, dry_run=False, verbose=verbose)
            # Resize newly-embedded art if profile specifies a max dimension
            artwork_size = self.output_profile.artwork_size
            if artwork_size > 0:
                cam.resize(export_dir, artwork_size, dry_run=False, verbose=verbose)
            # Re-scan to get accurate counts
            embedded_count = 0
            still_missing = 0
            for mp3_file in mp3_files:
                try:
                    tags = ID3(str(mp3_file))
                    if any(k.startswith("APIC") for k in tags):
                        embedded_count += 1
                    else:
                        still_missing += 1
                except (ID3NoHeaderError, Exception):
                    still_missing += 1
            self.stats.cover_art_embedded = embedded_count
            self.stats.cover_art_missing = still_missing
        else:
            self.stats.cover_art_missing = missing


