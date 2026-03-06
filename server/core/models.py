"""
core.models - Data model dataclasses.

EQConfig, OutputProfile, SyncDestination, result types, and _DisplayProgress.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.constants import EQ_CHAIN_ORDER, EQ_EFFECTS, VIRTUAL_DEST_TYPES


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


@dataclass
class SyncDestination:
    """A saved sync destination (name + schemed path + internal sync key).

    Paths use a scheme prefix:
      - usb:///Volumes/MY_USB/RZR/Music   → USB drive destination
      - folder:///path/to/dir             → Folder destination
      - web-client://My-USB               → Browser-local sync target
    Legacy plain paths are migrated to folder:// on config load.

    sync_key is an internal UUID — never exposed to users.
    linked_destinations lists other destination names sharing the same
    tracking group (populated by SyncTracker queries, not stored in DB).
    """
    name: str
    path: str  # usb:///Volumes/X/RZR/Music or folder:///path/to/dir
    sync_key: str = ''  # internal UUID; never shown to users
    linked_destinations: list[str] = field(default_factory=list)
    playlist_prefs: list[str] | None = None  # None = all playlists

    @property
    def type(self) -> str:
        if self.path.startswith('usb://'):
            return 'usb'
        if self.path.startswith('web-client://'):
            return 'web-client'
        if self.path.startswith('ios://'):
            return 'ios'
        return 'folder'

    @property
    def raw_path(self) -> str:
        if self.path.startswith('usb://'):
            return self.path[6:]
        if self.path.startswith('folder://'):
            return self.path[9:]
        if self.path.startswith('web-client://'):
            return self.path[13:]
        if self.path.startswith('ios://'):
            return self.path[6:]
        return self.path

    @property
    def is_usb(self) -> bool:
        return self.type == 'usb'

    @property
    def is_web_client(self) -> bool:
        return self.type == 'web-client'

    @property
    def available(self) -> bool:
        if self.type in VIRTUAL_DEST_TYPES:
            return True
        return Path(self.raw_path).is_dir()

    def to_api_dict(self) -> dict:
        return {'name': self.name, 'path': self.path,
                'type': self.type, 'available': self.available,
                'linked_destinations': self.linked_destinations,
                'playlist_prefs': self.playlist_prefs}


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
    playlist_track_names: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncResult:
    """Result of SyncManager.sync_to_destination()."""
    success: bool
    source: str
    destination: str
    duration: float
    is_usb: bool = False
    files_found: int = 0
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    orphaned_detected: int = 0
    orphaned_cleaned: int = 0
    orphaned_bytes_freed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SyncStatusResult:
    """Result of SyncTracker.get_destination_status()."""
    destinations: list = field(default_factory=list)
    last_sync_at: float = 0
    playlists: list = field(default_factory=list)
    total_files: int = 0
    synced_files: int = 0
    new_files: int = 0
    new_playlists: int = 0
    group_name: str = ''
    playlist_prefs: list | None = None  # None = all playlists
    orphaned_files: int = 0

    def to_dict(self) -> dict:
        return asdict(self)



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
    usb_result: SyncResult | None = None
    usb_destination: str | None = None
    removed_tracks: list = field(default_factory=list)
    cleanup_stats: dict | None = None

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




