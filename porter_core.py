"""
porter_core - Business logic for music-porter

Contains all business logic classes, protocols, result dataclasses,
and supporting utilities. CLI-specific code lives in music-porter.
"""

from __future__ import annotations

import sys
import subprocess
import os
import time
import shutil
from pathlib import Path
from datetime import datetime
import platform
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Protocol, Optional, List, Dict, Any, runtime_checkable


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

VERSION = "2.4.0-service-layer"

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


OUTPUT_PROFILES: dict = {
    "ride-command": OutputProfile(
        name="ride-command",
        description="Polaris Ride Command infotainment system",
        directory_structure="flat",
        filename_format="full",
        id3_version=3,
        strip_id3v1=True,
        title_tag_format="artist_title",
        artwork_size=100,
        quality_preset="lossless",
        pipeline_album="playlist_name",
        pipeline_artist="various",
    ),
    "basic": OutputProfile(
        name="basic",
        description="Standard MP3 with original tags and artwork",
        directory_structure="flat",
        filename_format="full",
        id3_version=4,
        strip_id3v1=True,
        title_tag_format="artist_title",
        artwork_size=0,
        quality_preset="lossless",
        pipeline_album="original",
        pipeline_artist="original",
    ),
}
DEFAULT_OUTPUT_TYPE = "ride-command"

# Valid choices for directory structure and filename format
VALID_DIR_STRUCTURES = ("flat", "nested-artist", "nested-artist-album")
VALID_FILENAME_FORMATS = ("full", "title-only")


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

    def __init__(self, log_dir=DEFAULT_LOG_DIR, verbose=False):
        self.verbose = verbose
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

        if self.conf_path.exists():
            try:
                self._load_yaml()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn("PyYAML not available — cannot load config.yaml yet")
                self.settings = {}
        else:
            try:
                self._create_default()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn(f"Configuration file not found: {self.conf_path}")
                self.settings = {}

    def _load_yaml(self):
        """Load configuration from YAML file."""
        import yaml

        with open(self.conf_path, 'r') as f:
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

        self.logger.info(f"Loaded {len(self.playlists)} playlists from {self.conf_path}")

    def _create_default(self):
        """Create a default config.yaml with empty playlists."""
        self.settings = {
            'output_type': DEFAULT_OUTPUT_TYPE,
            'usb_dir': DEFAULT_USB_DIR,
            'workers': DEFAULT_WORKERS,
        }
        self._save()
        self.logger.info(f"Created default configuration: {self.conf_path}")

    def _save(self):
        """Write current configuration to YAML file."""
        import yaml

        data = {
            'settings': self.settings,
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


# ══════════════════════════════════════════════════════════════════
# Section 4: Dependency Checking
# ══════════════════════════════════════════════════════════════════

class DependencyChecker:
    """Checks and manages dependencies from requirements.txt."""

    # Maps pip package names to their Python import names
    IMPORT_MAP = {
        'ffmpeg-python': 'ffmpeg',
        'webdriver-manager': 'webdriver_manager',
        'Pillow': 'PIL',
        'PyYAML': 'yaml',
        'Flask': 'flask',
    }

    # Packages that must be checked via subprocess instead of import
    SUBPROCESS_CHECK = {'gamdl'}

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
                os.execv(self.venv_python, [self.venv_python] + sys.argv)
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
        os.execv(venv_python, [venv_python] + sys.argv)

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

    def display_summary(self, config=None):
        """Display formatted dependency summary."""
        print("\n  ── Dependencies ──")

        # Virtual environment
        if self.dep_status['venv']:
            venv_display = self.venv_path.replace(str(Path.home()), '~') if self.venv_path else 'active'
            print(f"  Python:   ✓ venv ({venv_display})")
            self.logger.file_info(f"Python: venv ({self.venv_path})")
        else:
            print(f"  Python:   ⚠ No virtual environment")
            self.logger.file_info("Python: No virtual environment")

        # Python packages
        packages = self.dep_status['packages']
        if packages:
            installed = [pkg for pkg, ok in packages.items() if ok]
            missing = [pkg for pkg, ok in packages.items() if not ok]
            if not missing:
                pkg_list = ', '.join(installed)
                print(f"  Packages: ✓ {pkg_list}")
                self.logger.file_info(f"Packages: {pkg_list} installed")
            else:
                print(f"  Packages: ⚠ Missing: {', '.join(missing)}")
                self.logger.file_info(f"Packages: Missing {', '.join(missing)}")

        # System dependencies
        if self.dep_status['ffmpeg']:
            print(f"  System:   ✓ ffmpeg")
            self.logger.file_info("System: ffmpeg available")
        else:
            print(f"  System:   ⚠ ffmpeg not found")
            self.logger.file_info("System: ffmpeg not found")

        # Playlists (if config provided)
        if config:
            count = len(config.playlists)
            self.dep_status['playlists'] = count
            print(f"  Config:   ✓ {count} playlist{'s' if count != 1 else ''} loaded")
            self.logger.file_info(f"Config: {count} playlists loaded from {DEFAULT_CONFIG_FILE}")

        print()  # Blank line after summary

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
    from PIL import Image
    import io

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

    def show_status(self, message: str,
                    level: str = "info") -> None:
        pass

    def show_banner(self, title: str,
                    subtitle: str | None = None) -> None:
        pass


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
                 prompt_handler=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
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
            return False

        mp3_files = list(directory.rglob("*.mp3"))

        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        self.logger.info(f"Found {len(mp3_files)} MP3 file(s)")
        self.logger.info(f"New Album:  {new_album or '—'}")
        self.logger.info(f"New Artist: {new_artist or '—'}")

        start_time = time.time()
        updated = 0
        skipped = 0
        errors = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Tagging",
            logger=self.logger, disable=dry_run,
        )

        try:
            for filepath in mp3_files:
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
                        self.logger.debug(f"Tags BEFORE update:")
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
        self._print_update_summary(directory, duration, updated, skipped, errors)
        return errors == 0

    def _print_update_summary(self, directory, duration, updated, skipped, errors):
        """Print formatted summary after tag updates."""
        total_tag_updates = self.stats.title_updated + self.stats.album_updated + self.stats.artist_updated
        total_stored = self.stats.title_stored + self.stats.artist_stored + self.stats.album_stored

        print()
        print("=" * 60)
        print("  TAG UPDATE SUMMARY")
        print("=" * 60)
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Directory:               '{directory}'")
        print(f"  Duration:                {duration:.1f}s")
        print("─" * 60)
        print("  FILES")
        print("─" * 60)
        print(f"  Files processed:         {updated + skipped}")
        print(f"  Files updated:           {updated}")
        print(f"  Files skipped:           {skipped}")
        print(f"  Errors:                  {errors}")
        print("─" * 60)
        print("  TAG UPDATES")
        print("─" * 60)
        print(f"  Title updated:           {self.stats.title_updated}")
        print(f"  Album updated:           {self.stats.album_updated}")
        print(f"  Artist updated:          {self.stats.artist_updated}")
        print(f"  Total tag updates:       {total_tag_updates}")
        print("─" * 60)
        print("  ORIGINAL TAG PROTECTION")
        print("─" * 60)
        print(f"  OriginalTitle stored:    {self.stats.title_stored}")
        print(f"  OriginalArtist stored:   {self.stats.artist_stored}")
        print(f"  OriginalAlbum stored:    {self.stats.album_stored}")
        print(f"  Total stored:            {total_stored}")
        print("─" * 60)
        status_emoji = "✅" if errors == 0 else "❌"
        status_text = "Completed successfully" if errors == 0 else "Completed with errors"
        print(f"  Status:                  {status_emoji} {status_text}")
        print("=" * 60)

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
            return False

        mp3_files = list(directory.rglob("*.mp3"))

        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        self.logger.info(f"Found {len(mp3_files)} MP3 file(s)")
        self.logger.info(f"Restoring Album:  {restore_album}")
        self.logger.info(f"Restoring Title:  {restore_title}")
        self.logger.info(f"Restoring Artist: {restore_artist}")

        start_time = time.time()
        count = 0
        restored = 0
        skipped = 0
        errors = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Restoring",
            logger=self.logger, disable=dry_run,
        )

        try:
            for filepath in mp3_files:
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
                        self.logger.debug(f"Preserved originals:")
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
        self._print_restore_summary(directory, duration, restored, skipped, errors)
        return errors == 0

    def _print_restore_summary(self, directory, duration, restored, skipped, errors):
        """Print formatted summary after tag restoration."""
        total_restored = self.stats.title_restored + self.stats.album_restored + self.stats.artist_restored

        print()
        print("=" * 60)
        print("  TAG RESTORATION SUMMARY")
        print("=" * 60)
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Directory:               '{directory}'")
        print(f"  Duration:                {duration:.1f}s")
        print("─" * 60)
        print("  FILES")
        print("─" * 60)
        print(f"  Files processed:         {restored + skipped}")
        print(f"  Files restored:          {restored}")
        print(f"  Files skipped:           {skipped}")
        print(f"  Errors:                  {errors}")
        print("─" * 60)
        print("  TAG RESTORATIONS")
        print("─" * 60)
        print(f"  Title restored:          {self.stats.title_restored}")
        print(f"  Artist restored:         {self.stats.artist_restored}")
        print(f"  Album restored:          {self.stats.album_restored}")
        print(f"  Total restored:          {total_restored}")
        print("─" * 60)
        status_emoji = "✅" if errors == 0 else "❌"
        status_text = "Completed successfully" if errors == 0 else "Completed with errors"
        print(f"  Status:                  {status_emoji} {status_text}")
        print("=" * 60)

    def reset_tags_from_source(self, input_dir, output_dir, dry_run=False, verbose=False):
        """
        Recursively walk input_dir for .m4a files. For each one, read the
        original Title, Artist, and Album tags directly from the source,
        find the matching MP3 in output_dir, reset all three TXXX:Original*
        protection tags from the source values, rewrite TIT2/TPE1/TALB,
        refresh the title to 'Artist - Title' format, and save.

        ⚠️ WARNING: This permanently overwrites TXXX:Original* frames!
        """
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TXXX, ID3NoHeaderError

        start_time = time.time()

        input_path = Path(input_dir)
        output_path = Path(output_dir)

        if not input_path.is_dir():
            self.logger.error(f"Input directory not found: {input_path}")
            return False

        if not output_path.is_dir():
            self.logger.error(f"Output directory not found: {output_path}")
            return False

        # Find all M4A files
        m4a_files = [
            f for f in input_path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]

        if not m4a_files:
            self.logger.info(f"No .m4a files found in '{input_path}'")
            return True

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
                return False

        for input_file in m4a_files:
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
                    self.logger.debug(f"Source .m4a tags:")
                    self.logger.debug(f"  → Title:  '{title}'")
                    self.logger.debug(f"  → Artist: '{artist}'")
                    self.logger.debug(f"  → Album:  '{album}'")
                    self.logger.debug(f"Matched MP3: '{mp3_path}'")

                if dry_run:
                    self.logger.dry_run(f"Would reset MP3 tags from source:")
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
                    self.logger.debug(f"Tags AFTER reset:")
                    self.logger.debug(f"  → Title:          '{str(tags['TIT2'])}'")
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

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  RESET TAGS SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Input directory:         '{input_dir}'")
        print(f"  Output directory:        '{output_dir}'")
        print(f"  Duration:                {duration:.1f}s")
        print(f"{'─' * 60}")
        print(f"  FILES")
        print(f"{'─' * 60}")
        print(f"  Total .m4a found:        {total}")
        print(f"  MP3s updated:            {updated}")
        print(f"  Skipped (no MP3 match):  {skipped}")
        print(f"  Errors:                  {errors}")
        print(f"{'─' * 60}")
        print(f"  TAGGING")
        print(f"{'─' * 60}")
        print(f"  Original tags reset:     {tags_reset}")
        print(f"  Original tags rewritten: {updated * 3}")
        print(f"{'─' * 60}")
        if errors > 0:
            print(f"  Status:                  ⚠️  Completed with errors")
        elif updated == 0:
            print(f"  Status:                  ℹ️  No MP3s updated")
        else:
            print(f"  Status:                  ✅ Completed successfully")
        print(f"{'=' * 60}")

        return errors == 0

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

    def __init__(self, logger=None, quality_preset='lossless', workers=None, embed_cover_art=True, output_profile=None):
        self.logger = logger or Logger()
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

    def _build_output_path(self, base_path: Path, filename: str, artist: str = None, album: str = None) -> Path:
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
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TXXX, ID3NoHeaderError
        import hashlib

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
                self.logger.debug(f"Source tags:")
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
                        self.logger.dry_run(f"  → Cover art:  (none found in source)")
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
                raise Exception(f"FFmpeg conversion failed: {error_msg}")

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
                        self.logger.debug(f"  → Cover art: (none found in source)")

            # Save using profile-driven ID3 version and v1 settings
            tags.save(str(output_file),
                      v2_version=self.output_profile.id3_version,
                      v1=0 if self.output_profile.strip_id3v1 else 1)

            if verbose:
                self.logger.debug(f"Tags AFTER conversion (copied from source):")
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
            return False

        # Find all M4A files recursively
        m4a_files = [
            f for f in input_path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]

        if not m4a_files:
            self.logger.info(f"No .m4a files found in '{input_dir}'")
            return True

        self.stats.total_found = len(m4a_files)
        self.logger.info(f"Found {self.stats.total_found} .m4a file(s) (recursive)")
        self.logger.info(f"Output directory: '{output_dir}' ({display_name(self.output_profile.directory_structure)})")

        if force:
            self.logger.info("Force mode enabled — existing files will be overwritten")

        if not dry_run:
            output_path.mkdir(parents=True, exist_ok=True)

        # Determine effective worker count
        effective_workers = min(self.workers, self.stats.total_found)

        progress = ProgressBar(
            total=self.stats.total_found, desc="Converting",
            logger=self.logger, disable=dry_run,
        )

        try:
            if effective_workers > 1:
                self.logger.info(f"Using {effective_workers} parallel workers")

                with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                    futures = {
                        executor.submit(
                            self._convert_single_file,
                            input_file, input_path, output_path,
                            force, dry_run, verbose, progress
                        ): input_file
                        for input_file in m4a_files
                    }

                    for future in as_completed(futures):
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
                    self._convert_single_file(
                        input_file, input_path, output_path,
                        force, dry_run, verbose, progress
                    )
        finally:
            progress.close()

        duration = time.time() - start_time
        self._print_summary(input_dir, output_dir, duration)

        return self.stats.errors == 0

    def _print_summary(self, input_dir, output_dir, duration):
        """Print conversion summary statistics."""
        # Format quality settings for display
        quality_desc = f"{self.quality_settings['mode'].upper()}"
        if self.quality_settings['mode'] == 'vbr':
            quality_desc += f" quality {self.quality_settings['value']}"
        else:
            quality_desc += f" {self.quality_settings['value']}kbps"

        print(f"\n{'=' * 60}")
        print(f"  CONVERSION SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Input directory:         '{input_dir}'")
        print(f"  Output directory:        '{output_dir}'")
        print(f"  Duration:                {duration:.1f}s")
        if self.workers > 1:
            print(f"  Workers:                 {self.workers}")
        print(f"{'─' * 60}")
        print(f"  QUALITY SETTINGS")
        print(f"{'─' * 60}")
        print(f"  Preset:                  {self.quality_preset}")
        print(f"  Mode:                    {quality_desc}")
        print(f"{'─' * 60}")
        print(f"  FILES")
        print(f"{'─' * 60}")
        print(f"  Total found:             {self.stats.total_found}")
        print(f"  Converted:               {self.stats.converted}")
        print(f"  Overwritten:             {self.stats.overwritten}")
        print(f"  Skipped (exists):        {self.stats.skipped}")
        print(f"  Errors:                  {self.stats.errors}")
        print(f"{'─' * 60}")
        print(f"  TAGGING")
        print(f"{'─' * 60}")
        print(f"  Tags copied from source: Title, Artist, Album")
        print(f"{'─' * 60}")
        if self.stats.errors > 0:
            print(f"  Status:                  ⚠️  Completed with errors")
        elif self.stats.skipped == self.stats.total_found:
            print(f"  Status:                  ℹ️  Nothing to do — all files already exist")
        else:
            print(f"  Status:                  ✅ Completed successfully")
        print(f"{'=' * 60}")


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
                 prompt_handler=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
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
        Returns (success, key, album_name, download_stats)
        """
        import re

        # Extract info from URL if key not provided
        if not key:
            key, album_name = self.extract_url_info(url)
            if not key:
                self.logger.error(f"Could not extract playlist info from URL: {url}")
                return False, None, None, None
        else:
            _, album_name = self.extract_url_info(url)

        output_path = Path(output_dir)

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
                            return False, None, None, None
                    else:
                        self.logger.error("Automatic cookie refresh failed")
                        self.cookie_manager.show_manual_instructions()
                        return False, None, None, None
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
                                    return False, None, None, None
                            else:
                                self.logger.error("Automatic cookie refresh failed")
                                # Ask if they want to continue anyway
                                if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                    self.logger.info("Aborted")
                                    return False, None, None, None
                        else:
                            # User declined auto-refresh, ask if they want to continue
                            if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                self.logger.info("Aborted")
                                return False, None, None, None
                    else:
                        # In auto/non-interactive mode, fail immediately
                        self.logger.error("Cannot continue without valid cookies")
                        return False, None, None, None

        # Confirmation prompt (unless auto mode)
        if confirm:
            if not self.prompt_handler.confirm(f"Download {key}?", default=False):
                self.logger.info(f"Skipping download for {key}")
                return False, key, album_name, None

        if dry_run:
            self.logger.dry_run(f"Would download: {url}")
            self.logger.dry_run(f"  → Output: {output_path}")
            stats = DownloadStatistics()
            stats.playlist_total = 0
            stats.downloaded = 0
            stats.skipped = 0
            return True, key, album_name, stats

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Run gamdl
        self.logger.info(f"Starting download from Apple Music...")
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
            progress = ProgressBar(
                total=0, desc="Downloading",
                logger=self.logger, disable=dry_run,
            )
            verbose = self.logger.verbose

            try:
                for line in process.stdout:
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
                                current_track = int(match.group(1))
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

            if process.returncode == 0:
                self.logger.ok(f"Download complete: {key}")
                return True, key, album_name, stats
            else:
                self.logger.error(f"Download failed with exit code {process.returncode}")
                return False, key, album_name, stats

        except Exception as e:
            self.logger.error(f"Failed to download {key}: {e}")
            return False, key, album_name, stats


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
        from datetime import datetime, timezone

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
            status.expiration_date = datetime.fromtimestamp(target_cookie.expires, tz=timezone.utc)

            # Compare with current time
            now = datetime.now(timezone.utc)
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
        import http.cookiejar
        import time

        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, WebDriverException

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
            [p for p in wdm_dir.rglob(binary_name) if p.is_file() and not p.suffix == '.zip'],
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
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.firefox.service import Service as FirefoxService
        from selenium.webdriver.edge.service import Service as EdgeService
        from selenium.webdriver.safari.service import Service as SafariService
        from selenium.common.exceptions import WebDriverException
        import time

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
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import TimeoutException

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
        from selenium.common.exceptions import NoSuchElementException

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

    def __init__(self, logger=None, excluded_volumes=None, prompt_handler=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
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
        Returns (success boolean, USBSyncStatistics).

        Args:
            volume: Pre-selected volume name. Skips interactive selection if provided.
        """
        start_time = time.time()
        stats = USBSyncStatistics()
        source_path = Path(source_dir)

        if not source_path.exists():
            self.logger.error(f"Source directory does not exist: {source_path}")
            return False, stats

        # Collect all .mp3 files to process
        mp3_files = []
        if source_path.is_file():
            if source_path.suffix == '.mp3':
                mp3_files.append(source_path)
        else:
            for root, dirs, files in os.walk(source_path):
                for file in files:
                    if file.endswith('.mp3'):
                        mp3_files.append(Path(root) / file)

        stats.files_found = len(mp3_files)
        self.logger.info(f"Files to process: {stats.files_found}")

        # Select USB drive (skip interactive prompt if volume pre-selected)
        if volume is None:
            volume = self.select_usb_drive()
        if not volume:
            return False, stats

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
            self._print_usb_summary(str(source_path), str(dest), stats, duration)
            return True, stats

        # Create destination directory
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to create destination directory: {e}")
            stats.files_failed = stats.files_found
            duration = time.time() - start_time
            self._print_usb_summary(str(source_path), str(dest), stats, duration)
            return False, stats

        # Copy files with incremental check
        progress = ProgressBar(
            total=len(mp3_files), desc="Syncing to USB",
            logger=self.logger, disable=dry_run,
        )

        try:
            for src_file in mp3_files:
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
        self._print_usb_summary(str(source_path), str(dest), stats, duration)

        # Prompt to eject USB drive after successful copy
        if not dry_run:
            self._prompt_and_eject_usb(volume)
            # Note: eject operation is non-critical, doesn't affect return status

        # Success if no failures (skipped files are OK)
        return stats.files_failed == 0, stats

    def _print_usb_summary(self, source, destination, stats, duration):
        """Print formatted summary after USB sync."""
        print()
        print("=" * 60)
        print("  USB SYNC SUMMARY")
        print("=" * 60)
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Source:                  '{source}'")
        print(f"  Destination:             '{destination}'")
        print(f"  Duration:                {duration:.1f}s")
        print("─" * 60)
        print("  FILES")
        print("─" * 60)
        print(f"  Files found:             {stats.files_found}")
        print(f"  Files copied:            {stats.files_copied}")
        print(f"  Files skipped:           {stats.files_skipped}")
        print(f"  Files failed:            {stats.files_failed}")
        print("─" * 60)
        status_emoji = "✅" if stats.files_failed == 0 else "❌"
        status_text = "Completed successfully" if stats.files_failed == 0 else "Completed with errors"
        print(f"  Status:                  {status_emoji} {status_text}")
        print("=" * 60)

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
            bool: True if successful
        """
        # Print library stats first (unless skipped)
        if not no_library:
            music_stats = self.scan_music_library(
                music_dir=music_dir,
                export_profile=export_profile,
            )
            if music_stats and music_stats.total_files > 0:
                self._print_music_library_stats(music_stats)

        start_time = time.time()

        # Check if directory exists
        export_path = Path(export_dir)
        if not export_path.exists():
            print()
            print("╔" + "═" * 60 + "╗")
            print("║" + "PLAYLIST SUMMARY".center(60) + "║")
            print("╚" + "═" * 60 + "╝")
            print()
            print("  ℹ️  Export directory not found")
            print(f"  Path: '{export_dir}'")
            print()
            print("  Suggested next steps:")
            print("    • Run: ./music-porter pipeline --auto")
            print("    • Or specify custom directory: --export-dir /path/to/export")
            print()
            return True  # Not an error, just no data

        # Scan playlists
        playlist_dirs = self._scan_playlists(export_path)

        if not playlist_dirs:
            print()
            print("╔" + "═" * 60 + "╗")
            print("║" + "PLAYLIST SUMMARY".center(60) + "║")
            print("╚" + "═" * 60 + "╝")
            print()
            print(f"  Directory:               '{export_dir}'")
            print(f"  Total playlists:         0")
            print(f"  Total MP3 files:         0")
            print()
            print("  ℹ️  Library is empty")
            print()
            print("  Suggested next steps:")
            print("    • Run: ./music-porter pipeline --auto")
            print("    • Or download a playlist: ./music-porter download --playlist 1")
            print()
            return True  # Not an error

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

        # Display results
        if quick:
            self._print_quick_summary(export_dir)
        elif detailed:
            self._print_detailed_summary(export_dir)
        else:
            self._print_summary(export_dir)

        return True

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
                    for key in tags.keys():
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


    def _print_summary(self, export_dir):
        """Print default balanced summary."""
        print()
        print("╔" + "═" * 60 + "╗")
        print("║" + "PLAYLIST SUMMARY".center(60) + "║")
        print("╚" + "═" * 60 + "╝")
        print()
        print(f"  Directory:               '{export_dir}'")

        # Format scan date
        scan_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"  Scan date:               {scan_date}")
        print(f"  Scan duration:           {self.stats.scan_duration:.1f}s")
        print()

        # Aggregate statistics
        print("─" * 60)
        print("  AGGREGATE STATISTICS")
        print("─" * 60)
        print(f"  Total playlists:         {self.stats.total_playlists}")
        print(f"  Total MP3 files:         {self.stats.total_files}")
        print(f"  Total library size:      {self._format_size(self.stats.total_size_bytes)}")

        if self.stats.total_files > 0:
            avg_size = self.stats.total_size_bytes / self.stats.total_files
            print(f"  Average file size:       {self._format_size(avg_size)}")

        print()

        # Tag integrity
        print("─" * 60)
        print(f"  TAG INTEGRITY")
        print("─" * 60)

        if self.stats.sample_size > 0:
            percentage = (self.stats.files_with_protection_tags / self.stats.sample_size) * 100
            print(f"  Files with protection:   {self.stats.files_with_protection_tags}/{self.stats.sample_size} ({percentage:.0f}%)")

            if self.stats.files_missing_protection_tags == 0:
                print(f"  Status:                  ✅ All files have TXXX protection tags")
            else:
                print(f"  Status:                  ⚠️  Some files missing TXXX protection tags")
        else:
            print("  Status:                  ℹ️  No files checked")

        print()

        # Cover art
        print("─" * 60)
        print(f"  COVER ART")
        print("─" * 60)

        total_cover_checked = self.stats.files_with_cover_art + self.stats.files_without_cover_art
        if total_cover_checked > 0:
            cover_pct = (self.stats.files_with_cover_art / total_cover_checked) * 100
            print(f"  Files with cover art:    {self.stats.files_with_cover_art}/{total_cover_checked} ({cover_pct:.0f}%)")

            if self.stats.files_with_cover_art > 0:
                original_pct = (self.stats.files_with_original_cover_art / self.stats.files_with_cover_art) * 100
                print(f"  Original cover art:      {self.stats.files_with_original_cover_art}/{self.stats.files_with_cover_art} ({original_pct:.0f}%)")

                resized_pct = (self.stats.files_with_resized_cover_art / self.stats.files_with_cover_art) * 100
                print(f"  Modified cover art:      {self.stats.files_with_resized_cover_art}/{self.stats.files_with_cover_art} ({resized_pct:.0f}%)")

            if self.stats.files_without_cover_art == 0:
                print(f"  Status:                  ✅ All files have embedded cover art")
            else:
                print(f"  Status:                  ⚠️  {self.stats.files_without_cover_art} files missing cover art")
                print(f"  Fix:                     ./music-porter cover-art embed <dir>")
        else:
            print("  Status:                  ℹ️  No files checked")

        print()

        # Playlist breakdown
        print("─" * 60)
        print("  PLAYLIST BREAKDOWN")
        print("─" * 60)
        self._print_playlist_table()
        print()

        # Final status
        print("═" * 60)
        print("  Status:                  ✅ Library scan completed")
        print("═" * 60)
        print()

    def _print_quick_summary(self, export_dir):
        """Print minimal aggregate-only summary."""
        print()
        print("╔" + "═" * 60 + "╗")
        print("║" + "PLAYLIST SUMMARY (QUICK)".center(60) + "║")
        print("╚" + "═" * 60 + "╝")
        print()
        print(f"  Directory:               '{export_dir}'")
        print(f"  Total playlists:         {self.stats.total_playlists}")
        print(f"  Total MP3 files:         {self.stats.total_files}")
        print(f"  Total library size:      {self._format_size(self.stats.total_size_bytes)}")
        print(f"  Scan duration:           {self.stats.scan_duration:.1f}s")
        print()

    def _print_detailed_summary(self, export_dir):
        """Print extended summary with detailed breakdowns."""
        # Start with default summary
        self._print_summary(export_dir)

        # Add detailed per-playlist breakdowns
        print("─" * 60)
        print("  DETAILED PLAYLIST INFORMATION")
        print("─" * 60)
        print()

        for playlist in self.stats.playlists:
            print(f"  📁 {playlist.name}")
            print(f"     Files:                {playlist.file_count}")
            print(f"     Total size:           {self._format_size(playlist.total_size_bytes)}")
            print(f"     Average file size:    {playlist.avg_file_size_mb:.1f} MB")

            if playlist.last_modified:
                modified_str = playlist.last_modified.strftime("%b %d, %Y %H:%M")
                print(f"     Last modified:        {modified_str}")

            # Tag integrity for this playlist
            if playlist.sample_files_checked > 0:
                percentage = (playlist.sample_files_with_tags / playlist.sample_files_checked) * 100
                print(f"     Tag integrity:        {playlist.sample_files_with_tags}/{playlist.sample_files_checked} ({percentage:.0f}%)")

            # Cover art for this playlist
            total_cover = playlist.files_with_cover_art + playlist.files_without_cover_art
            if total_cover > 0:
                cover_pct = (playlist.files_with_cover_art / total_cover) * 100
                print(f"     Cover art:            {playlist.files_with_cover_art}/{total_cover} ({cover_pct:.0f}%)")
                if playlist.files_with_cover_art > 0:
                    original_pct = (playlist.files_with_original_cover_art / playlist.files_with_cover_art) * 100
                    print(f"     Original cover art:   {playlist.files_with_original_cover_art}/{playlist.files_with_cover_art} ({original_pct:.0f}%)")
                    if playlist.files_with_resized_cover_art > 0:
                        resized_pct = (playlist.files_with_resized_cover_art / playlist.files_with_cover_art) * 100
                        print(f"     Modified cover art:   {playlist.files_with_resized_cover_art}/{playlist.files_with_cover_art} ({resized_pct:.0f}%)")

            print()

        print("═" * 60)
        print()

    def _print_playlist_table(self):
        """Print formatted table of playlists."""
        if not self.stats.playlists:
            print("  (no playlists found)")
            return

        # Header
        print(f"  {'Playlist':<25} {'Files':>6}  {'Art/Mod':>9}  {'Size':>10}  {'Updated':<10}")
        print("  " + "─" * 62)

        # Sort by name
        sorted_playlists = sorted(self.stats.playlists, key=lambda p: p.name)

        # Rows
        today = datetime.now().date()
        for playlist in sorted_playlists:
            name = playlist.name[:24]  # Truncate long names
            files = str(playlist.file_count)
            art = f"{playlist.files_with_cover_art}/{playlist.files_with_resized_cover_art}"
            size = self._format_size(playlist.total_size_bytes)

            # Highlight Art/Mod if art has been modified but not all match
            if playlist.files_with_resized_cover_art > 0 and playlist.files_with_cover_art != playlist.files_with_resized_cover_art:
                art = f"⚠️{art}"

            if playlist.last_modified:
                # Format as "Feb 17" or "Feb 18"
                updated = playlist.last_modified.strftime("%b %d")
                # Highlight Updated if not today
                if playlist.last_modified.date() != today:
                    updated = f"⚠️{updated}"
            else:
                updated = "⚠️N/A"

            print(f"  {name:<25} {files:>6}  {art:>9}  {size:>10}  {updated:<10}")

        print("  " + "─" * 62)

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

    def _print_music_library_stats(self, music_stats):
        """Print the LIBRARY STATS section for the music/ directory."""
        print()
        print("╔" + "═" * 60 + "╗")
        print("║" + "LIBRARY STATS".center(60) + "║")
        print("╚" + "═" * 60 + "╝")
        print()
        print(f"  Directory:               '{DEFAULT_MUSIC_DIR}/'")
        print(f"  Total playlists:         {music_stats.total_playlists}")
        print(f"  Total M4A files:         {music_stats.total_files}")
        print(f"  Total library size:      {self._format_size(music_stats.total_size_bytes)}")

        if music_stats.total_files > 0:
            pct = (music_stats.total_exported / music_stats.total_files) * 100
            print(f"  Exported:                {music_stats.total_exported}/{music_stats.total_files} ({pct:.0f}%)")
            if music_stats.total_unconverted > 0:
                print(f"  Unconverted:             {music_stats.total_unconverted}")
            else:
                print(f"  Unconverted:             0  ✅")

        print(f"  Scan duration:           {music_stats.scan_duration:.1f}s")
        print()

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

    def __init__(self, logger=None, output_profile=None):
        self.logger = logger or Logger()
        self.output_profile = output_profile or OUTPUT_PROFILES[DEFAULT_OUTPUT_TYPE]

    def embed(self, directory, source_dir=None, force=False, dry_run=False, verbose=False):
        """
        Embed cover art into existing MP3s from matching M4A source files.
        Auto-derives source dir from export/ → music/ if not specified.
        """
        from mutagen.id3 import ID3, APIC, TXXX, ID3NoHeaderError
        import hashlib

        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return False

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
                return False

        source_path = Path(source_dir)
        if not source_path.exists():
            self.logger.error(f"Source directory not found: '{source_dir}'")
            return False

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

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

        progress = ProgressBar(
            total=len(mp3_files), desc="Embedding cover art",
            logger=self.logger, disable=dry_run,
        )

        try:
            for mp3_file in mp3_files:
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

                    apic_keys = [key for key in tags.keys() if key.startswith("APIC")]

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

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  COVER ART EMBED SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Directory:               '{directory}'")
        print(f"  Source:                   '{source_dir}'")
        print(f"{'─' * 60}")
        print(f"  Embedded:                {embedded}")
        print(f"  Skipped (already has):   {skipped}")
        print(f"  No source found:         {no_source}")
        print(f"  Errors:                  {errors}")
        print(f"{'=' * 60}")

        return errors == 0

    def extract(self, directory, output_dir=None, dry_run=False, verbose=False):
        """Extract cover art from MP3 files to image files."""
        from mutagen.id3 import ID3, ID3NoHeaderError

        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return False

        # Default output to same directory
        if output_dir is None:
            out_path = dir_path / "cover-art"
        else:
            out_path = Path(output_dir)

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        if not dry_run:
            out_path.mkdir(parents=True, exist_ok=True)

        extracted = 0
        skipped = 0
        errors = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Extracting cover art",
            logger=self.logger, disable=dry_run,
        )

        try:
            for mp3_file in mp3_files:
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

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  COVER ART EXTRACT SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Source:                  '{directory}'")
        print(f"  Output:                  '{out_path}'")
        print(f"{'─' * 60}")
        print(f"  Extracted:               {extracted}")
        print(f"  Skipped (no art):        {skipped}")
        print(f"  Errors:                  {errors}")
        print(f"{'=' * 60}")

        return errors == 0

    def update(self, directory, image_path, dry_run=False, verbose=False):
        """Replace cover art on all MP3s in a directory from a single image file."""
        from mutagen.id3 import ID3, APIC, ID3NoHeaderError

        dir_path = Path(directory)
        img_path = Path(image_path)

        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return False

        if not img_path.exists():
            self.logger.error(f"Image file not found: '{image_path}'")
            return False

        # Detect MIME type from extension
        ext = img_path.suffix.lower()
        if ext in ('.jpg', '.jpeg'):
            mime_type = APIC_MIME_JPEG
        elif ext == '.png':
            mime_type = APIC_MIME_PNG
        else:
            self.logger.error(f"Unsupported image format: '{ext}' (use .jpg or .png)")
            return False

        cover_data = img_path.read_bytes()
        self.logger.info(f"Image: {img_path.name} ({len(cover_data) / 1024:.1f} KB, {mime_type})")

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        updated = 0
        errors = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Updating cover art",
            logger=self.logger, disable=dry_run,
        )

        try:
            for mp3_file in mp3_files:
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

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  COVER ART UPDATE SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Directory:               '{directory}'")
        print(f"  Image:                   '{image_path}'")
        print(f"{'─' * 60}")
        print(f"  Updated:                 {updated}")
        print(f"  Errors:                  {errors}")
        print(f"{'=' * 60}")

        return errors == 0

    def strip(self, directory, dry_run=False, verbose=False):
        """Remove cover art from all MP3s in a directory."""
        from mutagen.id3 import ID3, ID3NoHeaderError

        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return False

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        stripped = 0
        skipped = 0
        errors = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Stripping cover art",
            logger=self.logger, disable=dry_run,
        )

        try:
            for mp3_file in mp3_files:
                try:
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        skipped += 1
                        progress.update(1)
                        continue

                    # Find and remove APIC frames
                    apic_keys = [key for key in tags.keys() if key.startswith("APIC")]

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

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  COVER ART STRIP SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Directory:               '{directory}'")
        print(f"{'─' * 60}")
        print(f"  Stripped:                {stripped}")
        print(f"  Skipped (no art):        {skipped}")
        print(f"  Errors:                  {errors}")
        print(f"{'=' * 60}")

        return errors == 0

    def resize(self, directory, max_size, dry_run=False, verbose=False):
        """Resize embedded cover art to a maximum dimension, preserving aspect ratio."""
        from PIL import Image
        import io
        from mutagen.id3 import ID3, ID3NoHeaderError

        dir_path = Path(directory)
        if not dir_path.exists():
            self.logger.error(f"Directory not found: '{directory}'")
            return False

        mp3_files = sorted(dir_path.rglob("*.mp3"))
        if not mp3_files:
            self.logger.info(f"No MP3 files found in '{directory}'")
            return True

        resized = 0
        skipped_small = 0
        skipped_no_art = 0
        errors = 0
        total_before = 0
        total_after = 0

        progress = ProgressBar(
            total=len(mp3_files), desc="Resizing cover art",
            logger=self.logger, disable=dry_run,
        )

        try:
            for mp3_file in mp3_files:
                try:
                    try:
                        tags = ID3(str(mp3_file))
                    except ID3NoHeaderError:
                        skipped_no_art += 1
                        progress.update(1)
                        continue

                    # Find APIC frame
                    apic_key = None
                    apic_frame = None
                    for key in tags.keys():
                        if key.startswith("APIC"):
                            apic_key = key
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

        # Format sizes for summary
        def fmt_size(b):
            if b >= 1024 * 1024:
                return f"{b / (1024 * 1024):.1f} MB"
            return f"{b / 1024:.1f} KB"

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  COVER ART RESIZE SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Directory:               '{directory}'")
        print(f"  Max dimension:           {max_size}px")
        print(f"{'─' * 60}")
        print(f"  Resized:                 {resized}")
        print(f"  Skipped (already small): {skipped_small}")
        print(f"  Skipped (no art):        {skipped_no_art}")
        print(f"  Errors:                  {errors}")
        if total_before > 0 and not dry_run:
            print(f"{'─' * 60}")
            print(f"  Total cover art:         {fmt_size(total_before)} → {fmt_size(total_after)}")
        elif total_before > 0:
            print(f"{'─' * 60}")
            print(f"  Total cover art:         {fmt_size(total_before)}")
        print(f"{'=' * 60}")

        return errors == 0


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


class PipelineOrchestrator:
    """Coordinates multi-stage workflows: download → convert → tag → USB sync."""

    def __init__(self, logger=None, deps=None, config=None, quality_preset='lossless',
                 cookie_path='cookies.txt', workers=None, embed_cover_art=True,
                 output_profile=None, prompt_handler=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
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

        # ── Stage 1: Determine source ─────────────────────────────────
        if url:
            # Direct URL provided
            self.logger.info("=== STAGE 1: Download from URL ===")
            success = self._download_from_url(url, auto, dry_run, verbose,
                                             validate_cookies, auto_refresh_cookies)
            if not success:
                self._print_pipeline_summary()
                return False

        elif playlist:
            # Playlist key or index provided
            self.logger.info("=== STAGE 1: Download playlist ===")
            success = self._download_playlist(playlist, auto, dry_run, verbose,
                                             validate_cookies, auto_refresh_cookies)
            if not success:
                self._print_pipeline_summary()
                return False

        else:
            self.logger.error("Either --playlist or --url must be specified for pipeline")
            return False

        # ── Stage 2: Convert M4A → MP3 ────────────────────────────────
        self.logger.info("\n=== STAGE 2: Convert M4A → MP3 ===")
        music_dir = f"{DEFAULT_MUSIC_DIR}/{self.stats.playlist_key}"
        export_dir = get_export_dir(self.output_profile.name, self.stats.playlist_key)

        # Use quality_preset parameter if provided, otherwise use instance default
        preset = quality_preset if quality_preset is not None else self.quality_preset
        converter = Converter(self.logger, quality_preset=preset, workers=self.workers,
                              embed_cover_art=self.embed_cover_art,
                              output_profile=self.output_profile)
        success = converter.convert(
            music_dir,
            export_dir,
            force=False,
            dry_run=dry_run,
            verbose=verbose
        )

        if success:
            self.stats.stages_completed.append("convert")
            self.stats.conversion_stats = converter.stats
        else:
            self.stats.stages_failed.append("convert")
            self.logger.error("Conversion stage failed")

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

        tagger = TaggerManager(self.logger, output_profile=self.output_profile)
        success = tagger.update_tags(
            export_dir,
            new_album=new_album,
            new_artist=new_artist,
            dry_run=dry_run,
            verbose=verbose
        )

        if success:
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

        # ── Stage 4: USB sync (optional) ───────────────────────────────
        if copy_to_usb:
            self.logger.info("\n=== STAGE 4: Copy to USB ===")
            usb_manager = USBManager(self.logger, prompt_handler=self.prompt_handler)
            success, usb_stats = usb_manager.sync_to_usb(
                export_dir,
                usb_dir=usb_dir,
                dry_run=dry_run
            )

            if success:
                self.stats.stages_completed.append("usb-sync")
                self.stats.usb_stats = usb_stats
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

        # ── Print final summary ────────────────────────────────────────
        self._print_pipeline_summary()

        return len(self.stats.stages_failed) == 0

    def _download_from_url(self, url, auto, dry_run, verbose,
                           validate_cookies=True, auto_refresh_cookies=False):
        """Download playlist from URL."""
        downloader = Downloader(self.logger, self.deps.venv_python,
                               cookie_path=self.cookie_path,
                               prompt_handler=self.prompt_handler)

        key, album_name = downloader.extract_url_info(url)
        if not key:
            self.logger.error(f"Could not extract playlist info from URL: {url}")
            self.stats.stages_failed.append("download")
            return False

        output_dir = f"{DEFAULT_MUSIC_DIR}/{key}"

        # Ask to save to config BEFORE download (only if not dry-run and not auto)
        if not dry_run and not auto:
            self._ask_save_to_config(key, url, album_name)

        success, key, album_name, download_stats = downloader.download(
            url,
            output_dir,
            key=key,
            confirm=not auto,
            dry_run=dry_run,
            validate_cookies=validate_cookies,
            auto_refresh=auto_refresh_cookies
        )

        if success:
            self.stats.download_success = True
            self.stats.playlist_key = key
            self.stats.playlist_name = album_name
            self.stats.download_stats = download_stats
            self.stats.stages_completed.append("download")

            return True
        else:
            # Check if user skipped (download_stats is None and we have key/album_name)
            # In this case, store the info and allow pipeline to continue
            if download_stats is None and key and album_name:
                self.stats.playlist_key = key
                self.stats.playlist_name = album_name
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
                               prompt_handler=self.prompt_handler)
        success, _, _, download_stats = downloader.download(
            playlist.url,
            output_dir,
            key=playlist.key,
            confirm=not auto,
            dry_run=dry_run,
            validate_cookies=validate_cookies,
            auto_refresh=auto_refresh_cookies
        )

        if success:
            self.stats.download_success = True
            self.stats.download_stats = download_stats
            self.stats.stages_completed.append("download")
            return True
        else:
            # Check if user skipped (download_stats is None and we have playlist info)
            # In this case, allow pipeline to continue
            if download_stats is None and self.stats.playlist_key:
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
                if not any(k.startswith("APIC") for k in tags.keys()):
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
            cam = CoverArtManager(self.logger, output_profile=self.output_profile)
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
                    if any(k.startswith("APIC") for k in tags.keys()):
                        embedded_count += 1
                    else:
                        still_missing += 1
                except (ID3NoHeaderError, Exception):
                    still_missing += 1
            self.stats.cover_art_embedded = embedded_count
            self.stats.cover_art_missing = still_missing
        else:
            self.stats.cover_art_missing = missing

    def _print_pipeline_summary(self):
        """Print comprehensive pipeline summary."""
        duration = time.time() - self.stats.start_time

        print(f"\n{'=' * 70}")
        print(f"  PIPELINE SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Run date:                {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Playlist:                {self.stats.playlist_name or '—'} ({self.stats.playlist_key or '—'})")
        print(f"  Duration:                {duration:.1f}s")

        # Download stage
        if "download" in self.stats.stages_completed or "download" in self.stats.stages_failed or "download" in self.stats.stages_skipped:
            print(f"{'─' * 70}")
            print(f"  DOWNLOAD STAGE")
            print(f"{'─' * 70}")
            if "download" in self.stats.stages_completed and self.stats.download_stats:
                s = self.stats.download_stats
                if s.playlist_total > 0:
                    print(f"  Total tracks in playlist:{s.playlist_total}")
                print(f"  Downloaded (new):        {s.downloaded}")
                print(f"  Skipped (already exist): {s.skipped}")
                if s.failed > 0:
                    print(f"  Failed:                  {s.failed}")
                print(f"  Status:                  ✅ Success")
            elif "download" in self.stats.stages_completed:
                print(f"  Status:                  ✅ Success")
            elif "download" in self.stats.stages_skipped:
                print(f"  Status:                  ⏭️  Skipped")
            else:
                print(f"  Status:                  ❌ Failed")

        # Conversion stage
        if self.stats.conversion_stats:
            print(f"{'─' * 70}")
            print(f"  CONVERSION STAGE")
            print(f"{'─' * 70}")
            s = self.stats.conversion_stats
            print(f"  Files converted:         {s.converted}")
            print(f"  Files overwritten:       {s.overwritten}")
            print(f"  Files skipped:           {s.skipped}")
            print(f"  Conversion errors:       {s.errors}")

        # Tagging stage
        if self.stats.tagging_stats:
            print(f"{'─' * 70}")
            print(f"  TAGGING STAGE")
            print(f"{'─' * 70}")
            s = self.stats.tagging_stats
            if self.stats.tagging_album:
                print(f"  Album set to:            {self.stats.tagging_album}")
            if self.stats.tagging_artist:
                print(f"  Artist set to:           {self.stats.tagging_artist}")
            print(f"  Title updated:           {s.title_updated}")
            print(f"  Album updated:           {s.album_updated}")
            print(f"  Artist updated:          {s.artist_updated}")
            print(f"  OriginalTitle stored:    {s.title_stored}")
            print(f"  OriginalArtist stored:   {s.artist_stored}")
            print(f"  OriginalAlbum stored:    {s.album_stored}")
            if self.stats.cover_art_embedded > 0 or self.stats.cover_art_missing > 0:
                print(f"  Cover art embedded:      {self.stats.cover_art_embedded}")
                print(f"  Cover art missing:       {self.stats.cover_art_missing}")

        # USB sync stage
        if self.stats.usb_success or "usb-sync" in self.stats.stages_failed:
            print(f"{'─' * 70}")
            print(f"  USB SYNC STAGE")
            print(f"{'─' * 70}")
            if self.stats.usb_success:
                print(f"  Status:                  ✅ Success")
                print(f"  USB destination:         {self.stats.usb_destination}")
            else:
                print(f"  Status:                  ❌ Failed")

        # Comprehensive file summary
        # Show if any pipeline stages completed (always show for comprehensive view)
        if len(self.stats.stages_completed) > 0:
            print(f"{'─' * 70}")
            print(f"  COMPREHENSIVE FILES SUMMARY")
            print(f"{'─' * 70}")

            # Download phase
            if self.stats.download_stats:
                d = self.stats.download_stats
                if d.playlist_total > 0:
                    print(f"  Playlist tracks:         {d.playlist_total}")
                total_after_download = d.downloaded + d.skipped
                print(f"  M4A files after download:{total_after_download} "
                      f"({d.downloaded} new, {d.skipped} existing)")

            # Conversion phase
            if self.stats.conversion_stats:
                c = self.stats.conversion_stats
                total_processed = c.converted + c.overwritten + c.skipped
                print(f"  MP3s after conversion:   {total_processed} "
                      f"({c.converted + c.overwritten} converted, {c.skipped} skipped)")

            # Tagging phase
            if self.stats.tagging_stats:
                t = self.stats.tagging_stats
                print(f"  Tags updated:            {t.title_updated}")
                total_original_stored = t.title_stored + t.artist_stored + t.album_stored
                if total_original_stored > 0:
                    print(f"  Original tags stored:    {total_original_stored}")
                if self.stats.cover_art_embedded > 0 or self.stats.cover_art_missing > 0:
                    print(f"  Cover art embedded:      {self.stats.cover_art_embedded}")
                    if self.stats.cover_art_missing > 0:
                        print(f"  Cover art missing:       {self.stats.cover_art_missing}")

            # USB sync
            if self.stats.usb_success and self.stats.conversion_stats:
                files_on_usb = self.stats.conversion_stats.converted + self.stats.conversion_stats.overwritten + self.stats.conversion_stats.skipped
                print(f"  Files copied to USB:     {files_on_usb}")

        # Overall status
        print(f"{'─' * 70}")
        if len(self.stats.stages_failed) == 0:
            print(f"  Status:                  ✅ Completed successfully")
        else:
            print(f"  Status:                  ⚠️  Completed with errors")
            print(f"  Failed stages:           {', '.join(self.stats.stages_failed)}")
        print(f"{'=' * 70}")

    def print_aggregate_summary(self, aggregate_stats):
        """Print comprehensive summary for multiple playlists."""
        aggregate_stats.end_time = time.time()
        duration = aggregate_stats.end_time - aggregate_stats.start_time
        duration_mins = int(duration // 60)
        duration_secs = int(duration % 60)

        print(f"\n{'=' * 70}")
        print(f"  TOTAL SUMMARY - ALL PLAYLISTS")
        print(f"{'=' * 70}")
        print(f"  Playlists processed:     {aggregate_stats.total_playlists}")
        print(f"  Total duration:          {duration:.1f}s ({duration_mins}m {duration_secs}s)")

        if aggregate_stats.failed_playlists == 0:
            print(f"  Overall status:          ✅ All succeeded")
        else:
            print(f"  Overall status:          ⚠️  Some failed")

        # Playlist results table
        print(f"{'─' * 70}")
        print(f"  PLAYLIST RESULTS")
        print(f"{'─' * 70}")
        print(f"  {'Playlist':<24} {'Downloaded':<12} {'Converted':<11} {'Tagged':<8} Status")
        print(f"  {'─' * 70}")

        for result in aggregate_stats.playlist_results:
            # Format download stats
            if result.download_stats:
                dl_str = f"{result.download_stats.downloaded}/{result.download_stats.playlist_total}"
            elif result.failed_stage == "download":
                dl_str = "ERROR"
            else:
                dl_str = "-/-"

            # Format conversion stats
            if result.conversion_stats:
                conv_count = result.conversion_stats.converted + result.conversion_stats.overwritten
                conv_total = conv_count + result.conversion_stats.skipped
                conv_str = f"{conv_count}/{conv_total}"
            elif result.failed_stage in ["download", "convert"]:
                conv_str = "-/-"
            else:
                conv_str = "0/0"

            # Format tag stats
            if result.tagging_stats:
                tag_str = str(result.tagging_stats.title_updated)
            else:
                tag_str = "-"

            # Status
            if result.success:
                status = "✅ Success"
            else:
                status = f"❌ {result.failed_stage or 'Failed'}"

            # Display name (truncate if needed)
            display_name = result.name[:22] if len(result.name) > 22 else result.name

            print(f"  {display_name:<24} {dl_str:<12} {conv_str:<11} {tag_str:<8} {status}")

        # Calculate totals
        totals = aggregate_stats.get_cumulative_stats()

        print(f"  {'─' * 70}")
        total_dl = f"{totals['downloaded']}/{totals['playlist_total']}"
        total_conv = f"{totals['converted'] + totals['overwritten']}/{totals['converted'] + totals['overwritten'] + totals['skipped_conversion']}"
        success_ratio = f"✅ {aggregate_stats.successful_playlists}/{aggregate_stats.total_playlists}"

        print(f"  {'TOTALS':<24} {total_dl:<12} {total_conv:<11} {totals['title_updated']:<8} {success_ratio}")

        # Cumulative statistics
        print(f"{'─' * 70}")
        print(f"  CUMULATIVE STATISTICS")
        print(f"{'─' * 70}")
        print(f"  Total tracks in playlists:    {totals['playlist_total']}")
        print(f"")
        print(f"  Downloads:")
        print(f"    New downloads:              {totals['downloaded']}")
        print(f"    Already existed (skipped):  {totals['skipped_download']}")
        if totals['failed_download'] > 0:
            print(f"    Failed:                     {totals['failed_download']}")
        print(f"")
        print(f"  Conversions:")
        print(f"    Newly converted:            {totals['converted']}")
        if totals['overwritten'] > 0:
            print(f"    Overwritten:                {totals['overwritten']}")
        print(f"    Skipped (already exist):    {totals['skipped_conversion']}")
        if totals['errors_conversion'] > 0:
            print(f"    Errors:                     {totals['errors_conversion']}")
        print(f"")
        print(f"  Tag Operations:")
        print(f"    Titles updated:             {totals['title_updated']}")
        if totals['original_tags_stored'] > 0:
            print(f"    Original tags stored:       {totals['original_tags_stored']}")

        # USB sync
        if aggregate_stats.usb_destination and totals['files_on_usb'] > 0:
            print(f"")
            print(f"  USB Sync:")
            print(f"    Files copied to USB:        {totals['files_on_usb']}")
            print(f"    Destination:                {aggregate_stats.usb_destination}")

        # Final status
        print(f"{'─' * 70}")
        if aggregate_stats.failed_playlists == 0:
            print(f"  STATUS:  ✅ All playlists completed successfully")
        else:
            print(f"  STATUS:  ⚠️  {aggregate_stats.failed_playlists} of {aggregate_stats.total_playlists} playlists failed")

            # List failed playlists
            failed_names = [
                f"{r.name} ({r.failed_stage})"
                for r in aggregate_stats.playlist_results
                if not r.success
            ]
            if failed_names:
                print(f"  Failed:  {', '.join(failed_names)}")

        print(f"{'=' * 70}")


