"""
porter_core - Compatibility shim re-exporting all symbols from the split modules.

This module previously contained all business logic. It has been split into
focused sub-modules under server/core/. This shim re-exports every public name
so existing callers (web_ui.py, web_api.py) continue to work unchanged.
"""
from __future__ import annotations

# ruff: noqa: F401
from core.config import (
    ConfigManager,
    DependencyChecker,
    NonInteractivePromptHandler,
    NullDisplayHandler,
    load_output_profiles,
    validate_config,
)
from core.constants import (
    DEFAULT_AUDIT_RETENTION_DAYS,
    DEFAULT_CLEAN_SYNC_DESTINATION,
    DEFAULT_CLEANUP_REMOVED_TRACKS,
    DEFAULT_CONFIG_FILE,
    DEFAULT_COOKIES,
    DEFAULT_DB_FILE,
    DEFAULT_IMPORTER,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_LOG_RETENTION_DAYS,
    DEFAULT_OUTPUT_TYPE,
    DEFAULT_QUALITY_PRESET,
    DEFAULT_TASK_HISTORY_RETENTION_DAYS,
    DEFAULT_USB_DIR,
    DEFAULT_WORKERS,
    EQ_EFFECTS,
    FRESHNESS_CURRENT_DAYS,
    FRESHNESS_RECENT_DAYS,
    FRESHNESS_STALE_DAYS,
    KNOWN_DEST_SCHEMES,
    OUTPUT_PROFILES,
    QUALITY_PRESETS,
    SOURCE_SUBDIR,
    VERSION,
    VIRTUAL_DEST_TYPES,
    get_os_display_name,
)
from core.converter import Converter
from core.database import (
    AuditLogger,
    EQConfigManager,
    PlaylistDB,
    ScheduledJobsDB,
    SyncTracker,
    TaskHistoryDB,
    TrackDB,
)
from core.downloader import CookieManager
from core.logging import Logger
from core.migrations import (
    flush_migration_events,
    migrate_config_schema,
    migrate_data_dir,
    migrate_db_schema,
    migrate_profiles_schema,
)
from core.models import (
    EQConfig,
    SyncDestination,
    SyncStatusResult,
)
from core.pipeline import (
    AggregateStatistics,
    DataManager,
    PipelineOrchestrator,
    SummaryManager,
    audit_library,
    backfill_track_metadata,
)
from core.sync import SyncManager
from core.tagging import TagApplicator
from core.utils import (
    _init_third_party,
    deduplicate_filenames,
    get_audio_dir,
    get_source_dir,
    prune_audit_entries,
    prune_logs,
    prune_task_history,
    sanitize_filename,
)
