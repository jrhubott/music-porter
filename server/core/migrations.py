"""
core.migrations - Schema migration functions for DB, config, and profiles.

Runs sequentially at startup to bring stored state up to current schema.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
import uuid
from pathlib import Path

from core.constants import (
    ARTWORK_SUBDIR,
    AUDIO_SUBDIR,
    CONFIG_SCHEMA_VERSION,
    DB_SCHEMA_VERSION,
    DEFAULT_CONFIG_FILE,
    DEFAULT_COOKIES,
    DEFAULT_DATA_DIR,
    DEFAULT_DB_FILE,
    DEFAULT_IMPORTER,
    DEFAULT_LIBRARY_DIR,
    DEFAULT_OUTPUT_PROFILES,
    DEFAULT_PROFILES_FILE,
    PROFILES_SCHEMA_VERSION,
    SOURCE_SUBDIR,
)
from core.logging import MigrationEvent
from core.utils import _secure_path


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


def _archive_file(src_path, version_label):
    """Copy a file to data/archive/ with a version suffix if not already archived."""
    src = Path(src_path)
    if not src.exists():
        return
    archive_dir = Path(DEFAULT_DATA_DIR) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{src.name}.v{version_label}"
    if not dest.exists():
        shutil.copy2(str(src), str(dest))


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

        if current > DB_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current} is newer than this "
                f"software supports ({DB_SCHEMA_VERSION}). Update the "
                f"software or restore from data/archive/."
            )

        if current >= DB_SCHEMA_VERSION:
            return []  # already up to date

        # Archive pre-migration DB for rollback safety
        _archive_file(db_path, current)

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

        # ── Version 6 → 7: playlists + destinations tables ────────────
        if current < 7:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    key         TEXT PRIMARY KEY,
                    url         TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS destinations (
                    name        TEXT PRIMARY KEY,
                    path        TEXT NOT NULL,
                    sync_key    TEXT NOT NULL,
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL
                )
            """)
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_destinations_sync_key
                ON destinations(sync_key)""")
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
            changes.append(
                "added playlists and destinations tables")
            if logger:
                logger.info(
                    "DB migration 6→7: added playlists + destinations tables")

        # ── Version 7 → 8: sync keys become internal UUIDs ────────────
        if current < 8:
            # Migrate human-readable sync_key values to UUIDs.
            # FK constraints are disabled for the migration since we're
            # updating PK values referenced by child tables.
            conn.execute("PRAGMA foreign_keys = OFF")

            existing_keys = conn.execute(
                "SELECT key_name FROM sync_keys"
            ).fetchall()
            for row in existing_keys:
                old_key = row[0]
                new_key = str(uuid.uuid4())
                # Update child tables first, then parent PK
                conn.execute(
                    "UPDATE sync_files SET sync_key = ? WHERE sync_key = ?",
                    (new_key, old_key),
                )
                conn.execute(
                    "UPDATE destinations SET sync_key = ? WHERE sync_key = ?",
                    (new_key, old_key),
                )
                conn.execute(
                    "UPDATE sync_keys SET key_name = ? WHERE key_name = ?",
                    (new_key, old_key),
                )

            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA user_version = 8")
            conn.commit()
            migrated_count = len(existing_keys)
            changes.append(
                f"migrated {migrated_count} sync keys to internal UUIDs")
            if logger:
                logger.info(
                    f"DB migration 7→8: migrated {migrated_count} sync keys "
                    "to UUIDs")

        # ── Version 8 → 9: group name on sync_keys ──────────────────────
        if current < 9:
            conn.execute("ALTER TABLE sync_keys ADD COLUMN name TEXT")
            conn.execute("PRAGMA user_version = 9")
            conn.commit()
            changes.append("added name column to sync_keys")
            if logger:
                logger.info(
                    "DB migration 8→9: added name column to sync_keys")

        # ── Version 9 → 10: playlist_prefs on sync_keys ──────────────────
        if current < 10:
            conn.execute(
                "ALTER TABLE sync_keys ADD COLUMN playlist_prefs TEXT")
            conn.execute("PRAGMA user_version = 10")
            conn.commit()
            changes.append("added playlist_prefs column to sync_keys")
            if logger:
                logger.info(
                    "DB migration 9→10: added playlist_prefs column "
                    "to sync_keys")

        # ── Version 10 → 11: removed_tracks table + track_uuid on sync_files
        if current < 11:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS removed_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT NOT NULL,
                    playlist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT NOT NULL,
                    display_filename TEXT,
                    removed_at REAL NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_removed_tracks_playlist"
                " ON removed_tracks(playlist)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_removed_tracks_removed_at"
                " ON removed_tracks(removed_at)")
            conn.execute(
                "ALTER TABLE sync_files ADD COLUMN track_uuid TEXT")
            conn.execute("PRAGMA user_version = 11")
            conn.commit()
            changes.append(
                "added removed_tracks table and track_uuid column to "
                "sync_files")
            if logger:
                logger.info(
                    "DB migration 10→11: added removed_tracks table and "
                    "track_uuid column to sync_files")

        # ── Version 11 → 12: index on sync_files.track_uuid ──────────────
        if current < 12:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sync_files_track_uuid"
                " ON sync_files(track_uuid)")
            conn.execute("PRAGMA user_version = 12")
            conn.commit()
            changes.append("added idx_sync_files_track_uuid index")
            if logger:
                logger.info(
                    "DB migration 11→12: added idx_sync_files_track_uuid"
                    " index on sync_files(track_uuid)")

        if current < 13:
            conn.execute(
                "ALTER TABLE tracks ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE tracks ADD COLUMN hidden_at REAL")
            conn.execute(
                "ALTER TABLE tracks ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_hidden"
                " ON tracks(playlist, hidden)")
            conn.execute("PRAGMA user_version = 13")
            conn.commit()
            changes.append("added hidden, hidden_at, locked columns to tracks")
            if logger:
                logger.info(
                    "DB migration 12→13: added hidden, hidden_at, locked"
                    " columns and idx_tracks_hidden index to tracks table")

        if current < 14:
            # Repair: v13 migration may have been skipped if TrackDB._init_db()
            # pre-stamped user_version=13 before migrate_db_schema() ran.
            # Add each column only if it is not already present.
            existing_cols = {
                r[1] for r in
                conn.execute("PRAGMA table_info(tracks)").fetchall()
            }
            if 'hidden' not in existing_cols:
                conn.execute(
                    "ALTER TABLE tracks"
                    " ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
            if 'hidden_at' not in existing_cols:
                conn.execute("ALTER TABLE tracks ADD COLUMN hidden_at REAL")
            if 'locked' not in existing_cols:
                conn.execute(
                    "ALTER TABLE tracks"
                    " ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_hidden"
                " ON tracks(playlist, hidden)")
            conn.execute("PRAGMA user_version = 14")
            conn.commit()
            changes.append("ensured hidden, hidden_at, locked columns on tracks (v13 repair)")
            if logger:
                logger.info(
                    "DB migration 13→14: ensured hidden/hidden_at/locked"
                    " columns exist on tracks table")

        if current < 15:
            # Drop removed_tracks table — scan-based destination cleanup replaces
            # the old API-based removal tracking mechanism.
            conn.execute("DROP TABLE IF EXISTS removed_tracks")
            conn.execute("PRAGMA user_version = 15")
            conn.commit()
            changes.append("dropped removed_tracks table (replaced by scan-based cleanup)")
            if logger:
                logger.info(
                    "DB migration 14→15: dropped removed_tracks table")

        if current < 16:
            conn.execute(
                "ALTER TABLE playlists ADD COLUMN last_downloaded_at REAL")
            conn.execute("PRAGMA user_version = 16")
            conn.commit()
            changes.append("added last_downloaded_at column to playlists table")
            if logger:
                logger.info(
                    "DB migration 15→16: added last_downloaded_at to playlists")

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

    if current > CONFIG_SCHEMA_VERSION:
        raise RuntimeError(
            f"Config schema version {current} is newer than this "
            f"software supports ({CONFIG_SCHEMA_VERSION}). Update the "
            f"software or restore from data/archive/."
        )

    if current >= CONFIG_SCHEMA_VERSION:
        return []  # already up to date

    # Archive pre-migration config for rollback safety
    _archive_file(conf_path, current)

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

    # ── Version 3 → 4: move playlists + destinations to DB ────────
    if current < 4:
        # DB tables already exist from DB migration v7 (runs first)
        db_path = Path(DEFAULT_DB_FILE)
        if db_path.exists():
            db_conn = sqlite3.connect(str(db_path), check_same_thread=False)
            try:
                now = time.time()

                # Migrate playlists from config → DB
                for entry in data.get('playlists', []):
                    key = str(entry.get('key', '')).strip()
                    url = str(entry.get('url', '')).strip()
                    name = str(entry.get('name', '')).strip()
                    if key and url and name:
                        db_conn.execute(
                            "INSERT OR IGNORE INTO playlists "
                            "(key, url, name, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (key, url, name, now, now),
                        )

                # Migrate destinations from config → DB
                for entry in data.get('destinations', []):
                    dname = str(entry.get('name', '')).strip()
                    dpath = str(entry.get('path', '')).strip()
                    if dname and dpath:
                        dsync_key = str(entry.get('sync_key', '')).strip()
                        if not dsync_key:
                            dsync_key = dname  # No more null sync_key
                        db_conn.execute(
                            "INSERT OR IGNORE INTO destinations "
                            "(name, path, sync_key, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (dname, dpath, dsync_key, now, now),
                        )
                        # Ensure sync_keys row exists
                        db_conn.execute(
                            "INSERT OR IGNORE INTO sync_keys "
                            "(key_name, last_sync_at, created_at) "
                            "VALUES (?, 0, ?)",
                            (dsync_key, now),
                        )

                db_conn.commit()
            finally:
                db_conn.close()

        # Remove playlists and destinations from config.yaml
        data.pop('playlists', None)
        data.pop('destinations', None)

        data['schema_version'] = 4
        dirty = True
        changes.append("moved playlists and destinations to database")
        if logger:
            logger.info(
                "Config migration 3→4: moved playlists + destinations to DB")

    # ── Version 4 → 5: move output_types to data/profiles.yaml ──────────────
    if current < 5:
        profiles_path = Path(DEFAULT_PROFILES_FILE)
        raw_types = data.get('output_types')

        # Only write profiles.yaml if it doesn't already exist.
        # Fresh installs have profiles.yaml committed to git; only existing
        # installs with output_types in config.yaml need the copy.
        if not profiles_path.exists() and isinstance(raw_types, dict) and raw_types:
            import copy as _copy
            profiles_data = {
                'schema_version': 1,
                'output': _copy.deepcopy(raw_types),
            }
            with open(profiles_path, 'w') as pf:
                pf.write("# Music Porter Output Profiles\n")
                pf.write("# Edit this file to add or customise output profiles.\n\n")
                yaml.dump(profiles_data, pf,
                          default_flow_style=False, sort_keys=False)
            if logger:
                logger.info(
                    f"Config migration 4→5: wrote output profiles to {profiles_path}")

        # Always remove output_types from config.yaml
        if 'output_types' in data:
            data.pop('output_types')
            dirty = True

        data['schema_version'] = 5
        dirty = True
        changes.append("moved output_types to data/profiles.yaml")
        if logger:
            logger.info("Config migration 4→5: removed output_types from config.yaml")

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


def migrate_profiles_schema(logger=None):
    """Apply sequential profiles.yaml schema migrations.

    Call once at startup, before ConfigManager is instantiated.
    Returns a list of MigrationEvent entries for deferred audit logging.

    Migration convention (same as migrate_config_schema):
      - Each `if current < N:` block sets schema_version to exactly N (not
        PROFILES_SCHEMA_VERSION). New migrations go exclusively in a new block.
      - Migrations must be idempotent and sequential (1→2→3…).
      - Never modify existing version blocks.
    """
    profiles_path = Path(DEFAULT_PROFILES_FILE)
    if not profiles_path.exists():
        return []

    try:
        import yaml
    except ImportError:
        return []  # PyYAML not yet installed — DependencyChecker handles this

    try:
        with open(profiles_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        if logger:
            logger.warn(f"Could not read profiles.yaml for migration: {e}")
        return []

    current = data.get('schema_version', 1)

    if current > PROFILES_SCHEMA_VERSION:
        raise RuntimeError(
            f"Profiles schema version {current} is newer than this "
            f"software supports ({PROFILES_SCHEMA_VERSION}). Update the "
            f"software or restore from data/archive/."
        )

    if current >= PROFILES_SCHEMA_VERSION:
        return []  # already up to date

    from_version = current
    dirty = False
    changes = []

    # Future migrations go here, e.g.:
    # if current < 2:
    #     # ... transform data ...
    #     data['schema_version'] = 2
    #     dirty = True
    #     changes.append("...")

    if dirty:
        with open(profiles_path, 'w') as f:
            f.write("# Music Porter Output Profiles\n")
            f.write("# Edit this file to add or customise output profiles.\n\n")
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        if logger:
            logger.info(
                f"Profiles schema updated to version {PROFILES_SCHEMA_VERSION}")
        return [MigrationEvent(
            'schema_migrate',
            f"Profiles schema migrated from version {from_version} to {PROFILES_SCHEMA_VERSION}",
            'completed',
            {'target': 'profiles', 'from_version': from_version,
             'to_version': PROFILES_SCHEMA_VERSION, 'changes': changes},
        )]

    return []


def flush_migration_events(events, audit_logger, source='cli'):
    """Flush deferred MigrationEvent entries into the audit trail."""
    for evt in events:
        audit_logger.log(evt.operation, evt.description, evt.status,
                         params=evt.params, source=source)


