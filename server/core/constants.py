"""
core.constants - Project-wide constants, defaults, and OS detection.

No internal dependencies.
"""
from __future__ import annotations

import os
import platform
import re

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

VERSION = "2.40.5-dev"

DEFAULT_DATA_DIR = "data"
DEFAULT_LIBRARY_DIR = "library"
SOURCE_SUBDIR = "source"
AUDIO_SUBDIR = "audio"
ARTWORK_SUBDIR = "artwork"
DEFAULT_IMPORTER = "gamdl"
IMPORTER_YTDLP = "ytdlp"
YT_COOKIE_PATH = "data/yt-cookies.txt"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_RETENTION_DAYS = 7
DEFAULT_AUDIT_RETENTION_DAYS = 90
DEFAULT_TASK_HISTORY_RETENTION_DAYS = 90
DEFAULT_CLEANUP_REMOVED_TRACKS = False
DEFAULT_CLEAN_SYNC_DESTINATION = False
DEFAULT_CONFIG_FILE = "data/config.yaml"
DEFAULT_PROFILES_FILE = "data/profiles.yaml"
DEFAULT_COOKIES = "data/cookies.txt"
DEFAULT_DB_FILE = "data/music-porter.db"
DEFAULT_USB_DIR = "RZR/Music"

# TXXX frame name used to uniquely identify library MP3 files in the DB
TXXX_TRACK_UUID = "TrackUUID"

# Destination name validation pattern
VALID_DEST_NAME_RE = r'^[a-zA-Z0-9_-]+$'

# Maximum length for destination description (free-text field)
MAX_DEST_DESCRIPTION_LEN = 200

# Virtual (non-filesystem) destination types — not backed by a server-visible path
VIRTUAL_DEST_TYPES = {'web-client', 'ios'}

# All recognized destination URI schemes
KNOWN_DEST_SCHEMES = ('usb://', 'folder://', 'web-client://', 'ios://')

# Schema version constants — increment and add a migration case when changing
# the config.yaml structure or DB tables/columns.
CONFIG_SCHEMA_VERSION = 5
PROFILES_SCHEMA_VERSION = 1  # increment + add a migration case when changing profiles.yaml structure
DB_SCHEMA_VERSION = 18

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
_profiles_file_mtime: float = 0.0  # tracks last-seen mtime of profiles.yaml
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
