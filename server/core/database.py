"""
core.database - All SQLite-backed database classes.

AuditLogger, TaskHistoryDB, ScheduledJobsDB, SyncTracker,
PlaylistDB, TrackDB, EQConfigManager.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from core.constants import (
    DB_SCHEMA_VERSION,
    DEFAULT_DB_FILE,
    IS_MACOS,
    KNOWN_DEST_SCHEMES,
    VALID_DEST_NAME_RE,
    VIRTUAL_DEST_TYPES,
)
from core.models import EQConfig, SyncDestination, SyncStatusResult


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
                    key_name       TEXT PRIMARY KEY,
                    last_sync_at   REAL NOT NULL DEFAULT 0,
                    created_at     REAL NOT NULL DEFAULT 0,
                    playlist_prefs TEXT
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

    def record_file(self, sync_key, playlist, file_path, track_uuid=None):
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
                           (sync_key, file_path, playlist, synced_at, track_uuid)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(sync_key, file_path, playlist)
                       DO UPDATE SET synced_at = ?, track_uuid = ?""",
                    (sync_key, file_path, playlist, now, track_uuid, now, track_uuid),
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

    def get_orphaned_files(self, sync_key):
        """Return sync_files records whose source track no longer exists in TrackDB.

        A file is orphaned when its track_uuid is set but no matching row exists
        in the tracks table (i.e. the track was deleted from the library).

        Returns a list of dicts: {id, file_path, playlist, track_uuid, synced_at}
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT sf.id, sf.file_path, sf.playlist,
                          sf.track_uuid, sf.synced_at
                   FROM sync_files sf
                   LEFT JOIN tracks t ON sf.track_uuid = t.uuid
                   WHERE sf.sync_key = ?
                     AND sf.track_uuid IS NOT NULL
                     AND t.uuid IS NULL""",
                (sync_key,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_orphaned_count(self, sync_key):
        """Return the count of orphaned sync_files records for a sync key."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS cnt
                   FROM sync_files sf
                   LEFT JOIN tracks t ON sf.track_uuid = t.uuid
                   WHERE sf.sync_key = ?
                     AND sf.track_uuid IS NOT NULL
                     AND t.uuid IS NULL""",
                (sync_key,),
            ).fetchone()
            return row['cnt'] if row else 0
        finally:
            conn.close()

    def delete_orphaned_records(self, sync_key):
        """Delete orphaned sync_files records for a sync key.

        Returns the number of records deleted.
        """
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    """DELETE FROM sync_files
                       WHERE sync_key = ?
                         AND track_uuid IS NOT NULL
                         AND track_uuid NOT IN (
                             SELECT uuid FROM tracks
                         )""",
                    (sync_key,),
                )
                deleted = cursor.rowcount
                conn.commit()
                return deleted
            finally:
                conn.close()

    def get_all_orphaned_files(self):
        """Return sync_files records across ALL sync keys whose track no longer exists.

        A file is orphaned when its track_uuid is set but no matching row exists
        in the tracks table (i.e. the track was deleted from the library).

        Returns a list of dicts: {id, file_path, playlist, track_uuid, sync_key, synced_at}
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT sf.id, sf.file_path, sf.playlist,
                          sf.track_uuid, sf.sync_key, sf.synced_at
                   FROM sync_files sf
                   LEFT JOIN tracks t ON sf.track_uuid = t.uuid
                   WHERE sf.track_uuid IS NOT NULL
                     AND t.uuid IS NULL""",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _get_keys(self):
        """List all tracked sync keys (internal).

        Returns list of dicts: {key_name, name, last_sync_at, created_at,
        playlist_prefs, total_synced_files}.
        """
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT k.key_name, k.name, k.last_sync_at, k.created_at,
                       k.playlist_prefs,
                       COUNT(f.id) AS total_synced_files
                FROM sync_keys k
                LEFT JOIN sync_files f ON f.sync_key = k.key_name
                GROUP BY k.key_name
                ORDER BY k.last_sync_at DESC
            """).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                raw = d.get('playlist_prefs')
                d['playlist_prefs'] = (
                    json.loads(raw) if raw else None)
                result.append(d)
            return result
        finally:
            conn.close()

    def get_synced_counts(self, sync_key, playlist_filter=None):
        """Return per-playlist synced file counts for a sync key.

        If playlist_filter is provided (list of playlist keys), only counts
        files belonging to those playlists.
        """
        conn = self._connect()
        try:
            if playlist_filter:
                placeholders = ','.join('?' * len(playlist_filter))
                rows = conn.execute(
                    f"""SELECT playlist, COUNT(*) AS cnt
                       FROM sync_files WHERE sync_key = ?
                       AND playlist IN ({placeholders})
                       GROUP BY playlist""",
                    (sync_key, *playlist_filter),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT playlist, COUNT(*) AS cnt
                       FROM sync_files WHERE sync_key = ?
                       GROUP BY playlist""",
                    (sync_key,),
                ).fetchall()
            return {r['playlist']: r['cnt'] for r in rows}
        finally:
            conn.close()

    def get_synced_bytes(self, sync_key: str, playlist_filter=None) -> int:
        """Return total bytes of synced files for a sync key via TrackDB join.

        If playlist_filter is provided (list of playlist keys), only counts
        bytes for files belonging to those playlists.
        """
        conn = self._connect()
        try:
            if playlist_filter:
                placeholders = ','.join('?' * len(playlist_filter))
                row = conn.execute(
                    f"""SELECT COALESCE(SUM(t.file_size_bytes), 0) AS total
                       FROM sync_files sf
                       JOIN tracks t ON sf.file_path = t.file_path
                       WHERE sf.sync_key = ?
                       AND sf.playlist IN ({placeholders})""",
                    (sync_key, *playlist_filter),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COALESCE(SUM(t.file_size_bytes), 0) AS total
                       FROM sync_files sf
                       JOIN tracks t ON sf.file_path = t.file_path
                       WHERE sf.sync_key = ?""",
                    (sync_key,),
                ).fetchone()
            return int(row['total']) if row else 0
        finally:
            conn.close()

    def _get_playlist_creation_times(self) -> dict:
        """Return {playlist_key: created_at} for all known playlists."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT key, created_at FROM playlists"
            ).fetchall()
            return {r['key']: r['created_at'] for r in rows}
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

    def _get_sync_status_for_key(self, sync_key, export_base_dir,
                                dest_names=None, group_name='',
                                prefs=None):
        """Diff export directory against tracked files for a sync key (internal).

        Returns SyncStatusResult with per-playlist breakdown.
        dest_names is the list of destination names sharing this key.
        group_name is the human-readable label for the group (may be empty).
        """
        export_path = Path(export_base_dir)
        if not export_path.exists():
            return SyncStatusResult(
                destinations=dest_names or [], last_sync_at=0,
                playlists=[], total_files=0, synced_files=0,
                new_files=0, new_playlists=0, group_name=group_name)

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

        creation_times = self._get_playlist_creation_times()
        playlists = []
        total_files = 0
        total_synced = 0
        total_new = 0
        new_playlist_count = 0
        pref_set = set(prefs) if prefs else None

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
            playlist_created_at = creation_times.get(playlist_name, 0)
            is_new_playlist = last_sync > 0 and playlist_created_at > last_sync

            in_prefs = pref_set is None or playlist_name in pref_set
            if not in_prefs:
                sync_status = 'skipped'
            elif is_new_playlist:
                sync_status = 'new'
            elif len(new) > 0:
                sync_status = 'behind'
            else:
                sync_status = 'synced'

            playlists.append({
                'name': playlist_name,
                'total_files': len(files_on_disk),
                'synced_files': len(synced),
                'new_files': len(new),
                'is_new_playlist': is_new_playlist,
                'sync_status': sync_status,
            })
            # synced_files reflects the actual destination state (always unfiltered)
            total_synced += len(synced)
            # total_files/new_files/new_playlists count only pref playlists
            if in_prefs:
                total_files += len(files_on_disk)
                total_new += len(new)
                if is_new_playlist:
                    new_playlist_count += 1

        orphaned = self.get_orphaned_count(sync_key)
        return SyncStatusResult(
            destinations=dest_names or [], last_sync_at=last_sync,
            playlists=playlists, total_files=total_files,
            synced_files=total_synced,
            new_files=max(0, total_new),
            new_playlists=new_playlist_count, group_name=group_name,
            orphaned_files=orphaned)

    def get_destination_status(self, dest_name, export_base_dir):
        """Get sync status for the group containing a destination.

        Resolves destination name → internal sync_key → status.
        Returns SyncStatusResult with all destination names in the group.
        """
        dest = self.get_destination(dest_name)
        if not dest:
            return SyncStatusResult(destinations=[dest_name])

        # Find all destinations sharing this sync_key and fetch group name
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT name FROM destinations WHERE sync_key = ?",
                (dest.sync_key,),
            ).fetchall()
            group_names = [r['name'] for r in rows]
            key_row = conn.execute(
                "SELECT name, playlist_prefs FROM sync_keys "
                "WHERE key_name = ?",
                (dest.sync_key,),
            ).fetchone()
            group_name = (key_row['name'] or '') if key_row else ''
            raw_prefs = key_row['playlist_prefs'] if key_row else None
            prefs = json.loads(raw_prefs) if raw_prefs else None
        finally:
            conn.close()

        result = self._get_sync_status_for_key(
            dest.sync_key, export_base_dir, dest_names=group_names,
            group_name=group_name, prefs=prefs)
        result.playlist_prefs = prefs
        return result

    def get_destination_groups(self, export_base_dir):
        """Get sync status for all destination groups.

        Returns list of SyncStatusResult, one per unique sync_key group.
        Each result includes the destination names in that group.
        """
        all_dests = self.get_all_destinations()
        # Group by sync_key
        key_to_dests = {}
        for d in all_dests:
            key_to_dests.setdefault(d.sync_key, []).append(d)

        # Fetch group names and prefs from sync_keys in one query
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT key_name, name, playlist_prefs FROM sync_keys"
            ).fetchall()
            key_group_names = {r['key_name']: (r['name'] or '')
                               for r in rows}
            key_prefs = {}
            for r in rows:
                raw = r['playlist_prefs']
                key_prefs[r['key_name']] = (
                    json.loads(raw) if raw else None)
        finally:
            conn.close()

        results = []
        for sync_key, dests in key_to_dests.items():
            names = [d.name for d in dests]
            gname = key_group_names.get(sync_key, '')
            status = self._get_sync_status_for_key(
                sync_key, export_base_dir, dest_names=names,
                group_name=gname, prefs=key_prefs.get(sync_key))
            status.playlist_prefs = key_prefs.get(sync_key)
            results.append(status)
        return results

    def reset_destination_tracking(self, dest_name):
        """Reset sync tracking for a destination's group.

        Deletes all sync_files for the destination's sync_key and
        resets last_sync_at to 0. The destination and sync_key remain.
        Returns dict: {reset: bool, files_cleared: int}.
        """
        dest = self.get_destination(dest_name)
        if not dest:
            return {'reset': False, 'files_cleared': 0}

        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM sync_files WHERE sync_key = ?",
                    (dest.sync_key,),
                )
                cleared = cursor.rowcount
                conn.execute(
                    "UPDATE sync_keys SET last_sync_at = 0 "
                    "WHERE key_name = ?",
                    (dest.sync_key,),
                )
                conn.commit()
                return {'reset': True, 'files_cleared': cleared}
            finally:
                conn.close()

    def set_group_name(self, dest_name: str, name: str) -> bool:
        """Set the human-readable label for a destination's group.

        Looks up the sync_key for dest_name and updates sync_keys.name.
        Pass an empty string to clear the name (stores NULL).
        Returns False if the destination is not found.
        """
        dest = self.get_destination(dest_name)
        if not dest:
            return False
        stored = name.strip() if name and name.strip() else None
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE sync_keys SET name = ? WHERE key_name = ?",
                    (stored, dest.sync_key),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def get_group_name(self, dest_name: str) -> str:
        """Return the group name for a destination's group ('' if unset)."""
        dest = self.get_destination(dest_name)
        if not dest:
            return ''
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT name FROM sync_keys WHERE key_name = ?",
                (dest.sync_key,),
            ).fetchone()
            return (row['name'] or '') if row else ''
        finally:
            conn.close()

    def save_playlist_prefs(self, dest_name: str,
                            playlist_keys: list | None) -> bool:
        """Persist playlist preferences for a destination's sync group.

        Stores the given playlist_keys list as JSON in sync_keys.
        Pass None (or empty list) to reset to "sync all".
        Returns False if the destination is not found.
        """
        dest = self.get_destination(dest_name)
        if not dest:
            return False
        # Normalise: treat [] same as None (all playlists)
        stored = (json.dumps(playlist_keys)
                  if playlist_keys else None)
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE sync_keys SET playlist_prefs = ? "
                    "WHERE key_name = ?",
                    (stored, dest.sync_key),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def get_playlist_prefs(self, dest_name: str) -> list | None:
        """Return playlist preferences for a destination's sync group.

        Returns a list of playlist keys or None (= all playlists).
        Returns None if the destination is not found.
        """
        dest = self.get_destination(dest_name)
        if not dest:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT playlist_prefs FROM sync_keys WHERE key_name = ?",
                (dest.sync_key,),
            ).fetchone()
            if not row:
                return None
            raw = row['playlist_prefs']
            return json.loads(raw) if raw else None
        finally:
            conn.close()

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
                    # No tracking records to move, but still clean up the
                    # source key row to avoid orphaned sync_keys entries.
                    conn.execute(
                        "DELETE FROM sync_keys WHERE key_name = ?",
                        (source_key,),
                    )
                    conn.commit()
                    return {'records_moved': 0, 'records_merged': 0,
                            'source_deleted': True}

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

    def get_file_sync_map(self, playlist):
        """Map filenames to destination names they've been synced to.

        Returns dict: {filename: [destination_name, ...]}.
        Resolves internal sync_key UUIDs to human-readable destination names.
        """
        conn = self._connect()
        try:
            # Build sync_key → [dest_names] lookup
            dest_rows = conn.execute(
                "SELECT name, sync_key FROM destinations"
            ).fetchall()
            key_to_names = {}
            for dr in dest_rows:
                key_to_names.setdefault(
                    dr['sync_key'], []).append(dr['name'])

            rows = conn.execute(
                """SELECT file_path, sync_key FROM sync_files
                   WHERE playlist = ? ORDER BY file_path, sync_key""",
                (playlist,),
            ).fetchall()
        finally:
            conn.close()

        sync_map = {}
        for r in rows:
            names = key_to_names.get(r['sync_key'], [])
            for name in names:
                sync_map.setdefault(r['file_path'], []).append(name)
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

    def delete_sync_files_by_track_uuid(self, track_uuid):
        """Delete sync_file records for a specific library track UUID.

        Used during library cleanup to purge tracking records for removed
        tracks. Returns count of deleted records.
        """
        if not track_uuid:
            return 0
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM sync_files WHERE track_uuid = ?",
                    (track_uuid,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    # ── Destination CRUD ──────────────────────────────────────────

    @staticmethod
    def _generate_sync_key():
        """Generate a new internal sync key UUID."""
        return str(uuid.uuid4())

    def add_destination(self, name, path, sync_key=None,
                        validate_path=True, audit_source=None):
        """Add a saved destination to the DB.

        If sync_key is not provided, generates a new UUID internally.
        If sync_key is provided (linking to existing group), uses it.
        Also creates the sync_keys row.
        Returns True on success, False on validation/duplicate error.
        """
        import re as _re
        if not _re.match(VALID_DEST_NAME_RE, name):
            return False

        # Normalize to schemed path
        if not any(path.startswith(s) for s in KNOWN_DEST_SCHEMES):
            path = f'folder://{path}'

        # Auto-generate sync_key UUID if not provided
        if not sync_key:
            sync_key = self._generate_sync_key()

        # Validate filesystem path if needed
        if validate_path:
            dest_tmp = SyncDestination(name, path, sync_key=sync_key)
            if dest_tmp.type not in VIRTUAL_DEST_TYPES:
                raw = dest_tmp.raw_path
                if dest_tmp.is_usb:
                    volume_path = Path(raw).parts[:3] if IS_MACOS else Path(raw).parts[:1]
                    volume_mount = Path(*volume_path) if volume_path else Path(raw)
                    if not volume_mount.is_dir():
                        return False
                elif not Path(raw).is_dir():
                    return False

        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                # Check for duplicates
                existing = conn.execute(
                    "SELECT 1 FROM destinations WHERE name = ? COLLATE NOCASE",
                    (name,),
                ).fetchone()
                if existing:
                    return False
                conn.execute(
                    "INSERT INTO destinations (name, path, sync_key, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, path, sync_key, now, now),
                )
                # Ensure sync_keys row exists
                conn.execute(
                    "INSERT INTO sync_keys (key_name, last_sync_at, created_at) "
                    "VALUES (?, 0, ?) ON CONFLICT(key_name) DO NOTHING",
                    (sync_key, now),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def get_destination(self, name):
        """Get a saved destination by name (case-insensitive).

        Returns SyncDestination or None.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT d.name, d.path, d.sync_key, k.playlist_prefs
                   FROM destinations d
                   LEFT JOIN sync_keys k ON k.key_name = d.sync_key
                   WHERE d.name = ? COLLATE NOCASE""",
                (name,),
            ).fetchone()
            if row:
                raw = row['playlist_prefs']
                prefs = json.loads(raw) if raw else None
                return SyncDestination(row['name'], row['path'],
                                       sync_key=row['sync_key'],
                                       playlist_prefs=prefs)
            return None
        finally:
            conn.close()

    def get_all_destinations(self):
        """List all saved destinations with linked_destinations populated."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT d.name, d.path, d.sync_key, k.playlist_prefs
                   FROM destinations d
                   LEFT JOIN sync_keys k ON k.key_name = d.sync_key
                   ORDER BY d.rowid"""
            ).fetchall()
            # Build sync_key → [names] map for linked_destinations
            key_to_names = {}
            for r in rows:
                key_to_names.setdefault(r['sync_key'], []).append(r['name'])

            dests = []
            for r in rows:
                linked = [n for n in key_to_names.get(r['sync_key'], [])
                          if n != r['name']]
                raw = r['playlist_prefs']
                prefs = json.loads(raw) if raw else None
                dests.append(SyncDestination(
                    r['name'], r['path'], sync_key=r['sync_key'],
                    linked_destinations=linked, playlist_prefs=prefs))
            return dests
        finally:
            conn.close()

    def remove_destination(self, name):
        """Remove a destination by name.

        If this is the last destination using its sync_key, the sync_key
        and all tracking data are also deleted. Otherwise, tracking data
        is preserved for the remaining destinations in the group.
        Returns True if found and deleted.
        """
        dest = self.get_destination(name)
        if not dest:
            return False
        sync_key = dest.sync_key

        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM destinations WHERE name = ? COLLATE NOCASE",
                    (name,),
                )
                # Check if any other destinations still use this sync_key
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM destinations WHERE sync_key = ?",
                    (sync_key,),
                ).fetchone()[0]
                if remaining == 0 and sync_key:
                    # Last destination — clean up tracking data
                    conn.execute(
                        "DELETE FROM sync_keys WHERE key_name = ?",
                        (sync_key,),
                    )
                conn.commit()
                return True
            finally:
                conn.close()

    def rename_destination(self, old_name, new_name):
        """Rename a destination. sync_key unchanged. Returns True on success."""
        import re as _re
        if not _re.match(VALID_DEST_NAME_RE, new_name):
            return False
        if old_name.lower() == new_name.lower():
            return False
        with self._write_lock:
            conn = self._connect()
            try:
                # Check new name not taken
                exists = conn.execute(
                    "SELECT 1 FROM destinations WHERE name = ? COLLATE NOCASE",
                    (new_name,),
                ).fetchone()
                if exists:
                    return False
                cursor = conn.execute(
                    "UPDATE destinations SET name = ?, updated_at = ? "
                    "WHERE name = ? COLLATE NOCASE",
                    (new_name, time.time(), old_name),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def find_destination_by_path(self, path):
        """Find a destination by schemed path. Returns SyncDestination or None."""
        normalized = path.rstrip('/\\')
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT name, path, sync_key FROM destinations"
            ).fetchall()
            for r in rows:
                if r['path'].rstrip('/\\') == normalized:
                    return SyncDestination(r['name'], r['path'],
                                           sync_key=r['sync_key'])
            return None
        finally:
            conn.close()

    def link_destination(self, name, target_dest_name):
        """Link a destination to another destination's tracking group.

        Looks up the target destination's sync_key UUID, assigns it to
        this destination, and merges any existing tracking data.
        Returns True if successful.
        """
        if not target_dest_name or not target_dest_name.strip():
            return False
        target = self.get_destination(target_dest_name.strip())
        if not target:
            return False
        source = self.get_destination(name)
        if not source:
            return False
        if source.sync_key == target.sync_key:
            return True  # Already in the same group

        old_key = source.sync_key
        new_key = target.sync_key
        now = time.time()

        # Read the target group's name before merging so we can restore it
        # if merge_key (or any future caller) inadvertently changes it.
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT name FROM sync_keys WHERE key_name = ?", (new_key,)
            ).fetchone()
            target_group_name = (row['name'] if row else None)
        finally:
            conn.close()

        with self._write_lock:
            conn = self._connect()
            try:
                # Update destination to use target's sync_key
                conn.execute(
                    "UPDATE destinations SET sync_key = ?, updated_at = ? "
                    "WHERE name = ? COLLATE NOCASE",
                    (new_key, now, name),
                )
                conn.commit()
            finally:
                conn.close()

        # Merge tracking data from old key into new key
        if old_key and old_key != new_key:
            self.merge_key(old_key, new_key)

        # Explicitly preserve the target group's name: linking must never
        # change the label of the group being joined.
        if target_group_name:
            with self._write_lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "UPDATE sync_keys SET name = ? "
                        "WHERE key_name = ? AND (name IS NULL OR name != ?)",
                        (target_group_name, new_key, target_group_name),
                    )
                    conn.commit()
                finally:
                    conn.close()

        return True

    def unlink_destination(self, name):
        """Unlink a destination from its shared tracking group.

        Creates a new independent sync_key UUID for this destination.
        Tracking data stays with the original group (the unlinked
        destination starts fresh unless explicitly re-synced).
        Returns True if found and updated.
        """
        dest = self.get_destination(name)
        if not dest:
            return False
        new_key = self._generate_sync_key()
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE destinations SET sync_key = ?, updated_at = ? "
                    "WHERE name = ? COLLATE NOCASE",
                    (new_key, now, name),
                )
                # Create the new sync_keys row
                conn.execute(
                    "INSERT INTO sync_keys (key_name, last_sync_at, created_at) "
                    "VALUES (?, 0, ?) ON CONFLICT(key_name) DO NOTHING",
                    (new_key, now),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def resolve_destination(self, path=None, name=None, drive_name=None,
                            link_to=None):
        """Server-side destination resolution.

        Finds or creates a destination from the provided hints.
        If link_to is provided (a destination name), the new destination
        shares that destination's tracking group.
        Returns dict: {destination: SyncDestination, created: bool}.
        """
        # 1. Look up by name if provided
        if name:
            dest = self.get_destination(name)
            if dest:
                return {'destination': dest, 'created': False}

        # 2. Look up by path if provided
        if path:
            dest = self.find_destination_by_path(path)
            if dest:
                return {'destination': dest, 'created': False}

        # 3. Auto-create from hints
        if not path and not name:
            return None

        if not name:
            # Generate name from drive_name or path basename
            if drive_name:
                name = drive_name
            elif path:
                dest_tmp = SyncDestination('_tmp', path, sync_key='')
                if dest_tmp.is_usb:
                    raw = dest_tmp.raw_path
                    parts = Path(raw).parts
                    name = parts[2] if len(parts) > 2 and parts[1] == 'Volumes' else Path(raw).name
                else:
                    name = Path(dest_tmp.raw_path).name
            # Sanitize name to valid characters
            import re as _re
            name = _re.sub(r'[^a-zA-Z0-9_-]', '-', name or '')
            if not name:
                name = 'destination'

        # Determine sync_key: link to existing destination or generate UUID
        sync_key = None
        if link_to:
            target = self.get_destination(link_to)
            if target:
                sync_key = target.sync_key

        ok = self.add_destination(name, path or f'folder:///{name}',
                                  sync_key=sync_key, validate_path=False)
        if not ok:
            # Name collision — try suffixed names
            for i in range(2, 100):
                suffixed = f'{name}-{i}'
                ok = self.add_destination(suffixed, path or f'folder:///{suffixed}',
                                          sync_key=sync_key, validate_path=False)
                if ok:
                    name = suffixed
                    break
            if not ok:
                return None

        dest = self.get_destination(name)
        return {'destination': dest, 'created': True}



class PlaylistDB:
    """Persistent playlist storage using SQLite.

    Thread-safe via a write lock; reads are lockless (WAL mode).
    Each call opens/closes its own connection for thread safety.
    """

    def __init__(self, db_path=DEFAULT_DB_FILE, audit_logger=None,
                 audit_source='cli'):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self.audit_logger = audit_logger
        self._audit_source = audit_source
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
                CREATE TABLE IF NOT EXISTS playlists (
                    key                TEXT PRIMARY KEY,
                    url                TEXT NOT NULL,
                    name               TEXT NOT NULL,
                    source_type        TEXT NOT NULL DEFAULT 'apple_music',
                    created_at         REAL NOT NULL,
                    updated_at         REAL NOT NULL,
                    last_downloaded_at REAL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def get(self, key):
        """Get single playlist by key (case-insensitive). Returns dict or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT key, url, name, source_type, created_at, updated_at,"
                " last_downloaded_at "
                "FROM playlists WHERE key = ? COLLATE NOCASE",
                (key,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all(self):
        """List all playlists ordered by insertion order."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT key, url, name, source_type, created_at, updated_at,"
                " last_downloaded_at "
                "FROM playlists ORDER BY rowid"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add(self, key, url, name, source_type='apple_music'):
        """Insert a new playlist. Returns True on success, False if key exists."""
        import re as _re
        if not key or not _re.match(r'^[a-zA-Z0-9_-]+$', key):
            return False
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM playlists WHERE key = ? COLLATE NOCASE",
                    (key,),
                ).fetchone()
                if existing:
                    return False
                conn.execute(
                    "INSERT INTO playlists (key, url, name, source_type, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (key, url, name, source_type, now, now),
                )
                conn.commit()
            finally:
                conn.close()
        if self.audit_logger:
            self.audit_logger.log(
                'playlist_add', f"Added playlist '{name}' ({key})",
                'completed', params={'key': key, 'name': name, 'source_type': source_type},
                source=self._audit_source)
        return True

    def update(self, key, url=None, name=None):
        """Update url and/or name for a playlist. Returns True if found."""
        row = self.get(key)
        if not row:
            return False
        now = time.time()
        new_url = url if url is not None else row['url']
        new_name = name if name is not None else row['name']
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE playlists SET url = ?, name = ?, updated_at = ? "
                    "WHERE key = ? COLLATE NOCASE",
                    (new_url, new_name, now, key),
                )
                conn.commit()
            finally:
                conn.close()
        if self.audit_logger:
            self.audit_logger.log(
                'playlist_update', f"Updated playlist '{key}'",
                'completed', params={'key': key, 'url': url, 'name': name},
                source=self._audit_source)
        return True

    def remove(self, key):
        """Delete a playlist by key. Returns True if found."""
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM playlists WHERE key = ? COLLATE NOCASE",
                    (key,),
                )
                conn.commit()
                deleted = cursor.rowcount > 0
            finally:
                conn.close()
        if deleted and self.audit_logger:
            self.audit_logger.log(
                'playlist_delete', f"Removed playlist '{key}'",
                'completed', params={'key': key},
                source=self._audit_source)
        return deleted

    def record_download(self, key):
        """Record that a download was attempted for this playlist."""
        now = time.time()
        with self._write_lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "UPDATE playlists SET last_downloaded_at = ? "
                    "WHERE key = ? COLLATE NOCASE",
                    (now, key),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def count(self):
        """Return total playlist count."""
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]
        finally:
            conn.close()


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
                    updated_at      REAL NOT NULL,
                    hidden          INTEGER NOT NULL DEFAULT 0,
                    hidden_at       REAL,
                    locked          INTEGER NOT NULL DEFAULT 0
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

    def get_tracks_by_playlist(self, playlist, include_hidden=False):
        """Return tracks for a playlist, ordered by title.

        Args:
            include_hidden: If True, includes hidden tracks. Defaults to False
                (active tracks only, backward-compatible).
        """
        conn = self._connect()
        try:
            if include_hidden:
                rows = conn.execute(
                    "SELECT * FROM tracks WHERE playlist = ? ORDER BY title",
                    (playlist,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tracks WHERE playlist = ? AND hidden = 0"
                    " ORDER BY title",
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
        """Return per-playlist aggregate stats (active tracks only).

        Returns list of dicts with keys: playlist, track_count,
        total_size_bytes, total_duration_s, max_updated_at,
        cover_with, cover_without.
        """
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT playlist,
                       SUM(CASE WHEN hidden = 0 THEN 1 ELSE 0 END) AS track_count,
                       COALESCE(SUM(CASE WHEN hidden = 0 THEN file_size_bytes ELSE 0 END), 0) AS total_size_bytes,
                       COALESCE(SUM(CASE WHEN hidden = 0 THEN duration_s ELSE 0 END), 0) AS total_duration_s,
                       COALESCE(MAX(CASE WHEN hidden = 0 THEN updated_at END), 0) AS max_updated_at,
                       SUM(CASE WHEN hidden = 0 AND cover_art_path IS NOT NULL
                           THEN 1 ELSE 0 END) AS cover_with,
                       SUM(CASE WHEN hidden = 0 AND cover_art_path IS NULL
                           THEN 1 ELSE 0 END) AS cover_without,
                       COUNT(*) AS total_track_count,
                       SUM(CASE WHEN hidden = 1 THEN 1 ELSE 0 END) AS hidden_count
                FROM tracks
                GROUP BY playlist
                ORDER BY playlist
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_track_count(self):
        """Return the total number of active (non-hidden) tracks."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tracks WHERE hidden = 0"
            ).fetchone()
            return row['cnt'] if row else 0
        finally:
            conn.close()

    def get_all_tracks(self):
        """Return all active (non-hidden) tracks, ordered by playlist then title."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE hidden = 0 ORDER BY playlist, title"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def search_tracks(self, query, include_hidden=True):
        """Search tracks by title, artist, or album (case-insensitive LIKE).

        ``query`` must already have SQL LIKE metacharacters escaped by the
        caller (``%`` → ``\\%``, ``_`` → ``\\_``, ``\\`` → ``\\\\``).
        """
        pattern = f"%{query}%"
        hidden_clause = " AND hidden = 0" if not include_hidden else ""
        sql = (
            "SELECT * FROM tracks"
            " WHERE ("
            "  UPPER(title)  LIKE UPPER(?) ESCAPE '\\'"
            "  OR UPPER(artist) LIKE UPPER(?) ESCAPE '\\'"
            "  OR UPPER(album)  LIKE UPPER(?) ESCAPE '\\'"
            f"){hidden_clause}"
            " ORDER BY playlist, title"
        )
        conn = self._connect()
        try:
            rows = conn.execute(sql, (pattern, pattern, pattern)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_orphaned_playlist_tracks(self):
        """Return tracks whose playlist column references a non-existent playlist.

        Cross-table query against the playlists table. Returns a list of track
        dicts for tracks with a playlist key that no longer exists.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT t.*
                   FROM tracks t
                   WHERE t.playlist NOT IN (SELECT key FROM playlists)
                   ORDER BY t.playlist, t.title""",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_playlist_fingerprint(self, playlist):
        """Return a lightweight fingerprint (count + max_updated_at + total_size).

        Changes when any active track is added, removed, updated, or hidden/unhidden.
        Returns None if the playlist has no active tracks.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(updated_at) AS max_updated, "
                "COALESCE(SUM(file_size_bytes), 0) AS total_size "
                "FROM tracks WHERE playlist = ? AND hidden = 0",
                (playlist,),
            ).fetchone()
            if not row or row["cnt"] == 0:
                return None
            return f"{row['cnt']}-{row['max_updated']}-{row['total_size']}"
        finally:
            conn.close()

    def set_hidden(self, uuid, hidden: bool):
        """Set or clear the hidden flag for a track.

        When hiding, records the current time in hidden_at.
        When unhiding, clears hidden_at.
        """
        import time as _time
        hidden_at = _time.time() if hidden else None
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE tracks SET hidden = ?, hidden_at = ?,"
                    " updated_at = ? WHERE uuid = ?",
                    (1 if hidden else 0, hidden_at, _time.time(), uuid),
                )
                conn.commit()
            finally:
                conn.close()

    def get_hidden_tracks(self, playlist, since=None):
        """Return hidden tracks for a playlist.

        Args:
            since: Optional Unix timestamp — only return tracks hidden after this time.
        """
        conn = self._connect()
        try:
            if since is not None:
                rows = conn.execute(
                    "SELECT * FROM tracks WHERE playlist = ? AND hidden = 1"
                    " AND hidden_at > ? ORDER BY title",
                    (playlist, since),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tracks WHERE playlist = ? AND hidden = 1"
                    " ORDER BY title",
                    (playlist,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def set_locked(self, uuid, locked: bool):
        """Set or clear the locked flag for a track."""
        import time as _time
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE tracks SET locked = ?, updated_at = ? WHERE uuid = ?",
                    (1 if locked else 0, _time.time(), uuid),
                )
                conn.commit()
            finally:
                conn.close()

    def set_all_locked(self, playlist, locked: bool):
        """Bulk set or clear the locked flag for all tracks in a playlist."""
        import time as _time
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE tracks SET locked = ?, updated_at = ?"
                    " WHERE playlist = ?",
                    (1 if locked else 0, _time.time(), playlist),
                )
                conn.commit()
            finally:
                conn.close()

    def hide_duplicates(self, playlist_key):
        """Hide duplicate tracks (same artist+title) within a playlist.

        Keeps the earliest created_at; hides all others. Skips locked tracks.
        Returns the number of tracks hidden.
        """
        tracks = [
            t for t in self.get_tracks_by_playlist(playlist_key, include_hidden=False)
            if not t.get('locked')
        ]
        groups = {}
        for track in tracks:
            dup_key = (
                f"{(track.get('artist') or '').lower()}"
                f"|||{(track.get('title') or '').lower()}"
            )
            groups.setdefault(dup_key, []).append(track)

        hidden_count = 0
        for group in groups.values():
            if len(group) <= 1:
                continue
            group.sort(key=lambda t: t.get('created_at') or '')
            for track in group[1:]:
                self.set_hidden(track['uuid'], True)
                hidden_count += 1
        return hidden_count


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


