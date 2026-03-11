"""
core.config - ConfigManager, DependencyChecker, profile loading, and validation.

NonInteractivePromptHandler, NullDisplayHandler included here as lightweight
handler implementations.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import yaml

from core.constants import (
    _PROFILE_REQUIRED_FIELDS,
    CONFIG_SCHEMA_VERSION,
    DEFAULT_CONFIG_FILE,
    DEFAULT_LOG_RETENTION_DAYS,
    DEFAULT_OUTPUT_PROFILES,
    DEFAULT_OUTPUT_TYPE,
    DEFAULT_PROFILES_FILE,
    DEFAULT_QUALITY_PRESET,
    DEFAULT_WORKERS,
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    OUTPUT_PROFILES,
    VALID_ID3_VERSIONS,
    VALID_PROFILE_NAME_RE,
)
from core.logging import Logger
from core.models import DependencyCheckResult, OutputProfile
from core.utils import _init_third_party

_profiles_file_mtime: float = 0.0


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


def detect_source_type(url):
    """Detect playlist source type from URL.

    Returns 'apple_music' or 'youtube_music'.
    Raises ValueError for unrecognised URLs.
    """
    if 'music.apple.com' in url:
        return 'apple_music'
    if 'music.youtube.com' in url or 'youtube.com/playlist' in url:
        return 'youtube_music'
    raise ValueError(
        f"Unrecognised playlist URL. Expected music.apple.com or music.youtube.com — got: {url}"
    )


_KNOWN_SETTINGS_KEYS = {
    'output_type', 'workers', 'quality_preset',
    'api_key', 'server_name', 'log_retention_days', 'scheduler',
    'audit_retention_days', 'task_history_retention_days',
    'removed_tracks_retention_days',
}
def validate_config(conf_path=DEFAULT_CONFIG_FILE):
    """Validate config.yaml independently and return a structured report.

    Returns a list of (level, message) tuples where level is "ok", "warning",
    or "error". Does not modify any state or raise exceptions.
    """

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

    Re-reads profiles.yaml from disk if the file has been modified since last
    load — no server restart needed to pick up profile edits.
    Raises ValueError if settings.output_type references a nonexistent profile.
    """
    global _profiles_file_mtime

    # Check if profiles.yaml changed on disk since last load
    profiles_path = Path(DEFAULT_PROFILES_FILE)
    try:
        current_mtime = profiles_path.stat().st_mtime
    except OSError:
        current_mtime = 0.0

    if current_mtime != _profiles_file_mtime:
        # File was created, modified, or replaced — reload into config
        config._load_profiles(profiles_path)
        _profiles_file_mtime = current_mtime

    OUTPUT_PROFILES.clear()
    for name, profile in config.output_profiles.items():
        OUTPUT_PROFILES[name] = profile

    # Validate that settings.output_type references an existing profile
    selected = config.get_setting('output_type', DEFAULT_OUTPUT_TYPE)
    if selected not in OUTPUT_PROFILES:
        available = ", ".join(OUTPUT_PROFILES.keys())
        raise ValueError(
            f"settings.output_type '{selected}' not found in output profiles. "
            f"Available profiles: {available}")


DISPLAY_NAMES = {
    "full": "Artist - Title",
}

class ConfigManager:
    """Manages configuration from config.yaml (YAML format)."""

    def __init__(self, conf_path=DEFAULT_CONFIG_FILE, logger=None,
                 audit_logger=None, audit_source='cli', on_change=None):
        self.conf_path = Path(conf_path)
        self.logger = logger or Logger()
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self._on_change = on_change
        self.settings = {}
        self.output_profiles = {}

        if self.conf_path.exists():
            try:
                self._load_yaml()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn("PyYAML not available — cannot load config.yaml yet")
                self.settings = {}
                self.output_profiles = {}
        else:
            try:
                self._create_default()
            except ImportError:
                # PyYAML not yet installed (first run before DependencyChecker)
                self.logger.warn(f"Configuration file not found: {self.conf_path}")
                self.settings = {}
                self.output_profiles = {}

    def _load_yaml(self):
        """Load configuration from YAML file.

        Schema migrations are handled by migrate_config_schema() at startup.
        This method only loads and validates — no inline migrations.
        """

        with open(self.conf_path) as f:
            data = yaml.safe_load(f) or {}

        self.settings = data.get('settings', {})
        profiles_path = self.conf_path.parent / "profiles.yaml"
        self._load_profiles(profiles_path)

    def _load_profiles(self, profiles_path):
        """Load and validate output profiles from profiles.yaml.

        Falls back to DEFAULT_OUTPUT_PROFILES with a warning if the file is missing.
        Raises ValueError on invalid profile content.
        """
        import copy


        if not profiles_path.exists():
            self.logger.warn(
                f"profiles.yaml not found at {profiles_path}; "
                "using built-in default profiles")
            raw_types = copy.deepcopy(DEFAULT_OUTPUT_PROFILES)
        else:
            with open(profiles_path) as pf:
                data = yaml.safe_load(pf) or {}
            raw_types = data.get('output') or {}

        if not isinstance(raw_types, dict) or len(raw_types) == 0:
            raise ValueError(
                f"{profiles_path}: 'output' section is missing or empty")

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

        self.logger.info(
            f"Loaded {len(self.output_profiles)} output profiles from {profiles_path}")

    def _create_default(self):
        """Create a default config.yaml. Profiles are loaded from profiles.yaml."""
        self.settings = {
            'output_type': DEFAULT_OUTPUT_TYPE,
            'workers': DEFAULT_WORKERS,
            'quality_preset': DEFAULT_QUALITY_PRESET,
            'server_name': '',
            'log_retention_days': DEFAULT_LOG_RETENTION_DAYS,
        }
        self._save()
        profiles_path = self.conf_path.parent / "profiles.yaml"
        self._load_profiles(profiles_path)
        self.logger.info(f"Created default configuration: {self.conf_path}")

    def _save(self):
        """Write current configuration to config.yaml (settings only)."""

        data = {
            'schema_version': CONFIG_SCHEMA_VERSION,
            'settings': self.settings,
        }

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


class DependencyChecker:
    """Checks and manages dependencies from requirements.txt."""

    # Maps pip package names to their Python import names
    IMPORT_MAP: ClassVar[dict[str, str]] = {
        'ffmpeg-python': 'ffmpeg',
        'webdriver-manager': 'webdriver_manager',
        'Pillow': 'PIL',
        'PyYAML': 'yaml',
        'Flask': 'flask',
        'yt-dlp': 'yt_dlp',
    }

    # Packages that must be checked via subprocess instead of import
    SUBPROCESS_CHECK: ClassVar[set[str]] = {'gamdl'}

    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.venv_python: str = sys.executable
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

    def _check_package(self, package_name: str) -> bool:
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

    def get_status(self, playlist_count=0) -> DependencyCheckResult:
        """Return current dependency status as a result object."""
        packages = self.dep_status.get('packages', {})
        missing = [pkg for pkg, ok in packages.items() if not ok]
        playlists = playlist_count
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




