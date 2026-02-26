"""
web_ui.py - Flask web dashboard for music-porter

Provides a browser-based UI for all music-porter operations with
live log streaming via Server-Sent Events (SSE).

User Prompt Handling (SRS 2.4.3):
    Web operations intentionally use NonInteractivePromptHandler (the default
    when no handler is passed to business classes).  All web tasks are
    fire-and-forget background jobs — there is no modal dialog infrastructure
    for mid-operation prompts.  NonInteractivePromptHandler returns safe
    defaults: deny destructive actions, skip optional prompts, return
    default values for text input.

    Exception: operations that require confirm_destructive() (e.g. tag reset)
    use WebPromptHandler, which auto-confirms because the user already
    initiated the action via the web UI.

Display Handling (SRS 2.6.4):
    WebDisplayHandler translates show_progress() / show_status() calls into
    SSE events pushed to the frontend via /api/stream/<task_id>.
"""

import json
import os
import platform
import queue
import re
import signal
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import porter_core as mp

# Initialize third-party imports once at load time.
# The web server runs inside the venv so all packages are already available.
# This avoids DependencyChecker's pip/os.execv() in background threads.
mp._init_third_party()

# Ensure data directory exists and migrate legacy files
mp.migrate_data_dir()

# Load output profiles from config at import time so OUTPUT_PROFILES is
# populated before any request handler accesses it.
_startup_config = mp.ConfigManager(logger=mp.Logger(verbose=False))
mp.load_output_profiles(_startup_config)


# ══════════════════════════════════════════════════════════════════
# WebLogger — routes log output to SSE queue + log file
# ══════════════════════════════════════════════════════════════════

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


class WebLogger(mp.Logger):
    """Logger subclass that sends messages to an SSE queue instead of stdout."""

    def __init__(self, log_queue, cancel_event=None, verbose=False):
        super().__init__(verbose=verbose)
        self._queue = log_queue
        self._cancel_event = cancel_event

    def _write(self, level, message):
        """Push to SSE queue and write to log file (no console)."""
        if self._cancel_event and self._cancel_event.is_set():
            return
        clean = _ANSI_RE.sub('', message)
        self._queue.put({'level': level, 'message': clean})
        self._write_file_only(level, message)

    def file_info(self, message):
        """Push per-file messages to SSE queue (visible in web UI)."""
        if self._cancel_event and self._cancel_event.is_set():
            return
        clean = _ANSI_RE.sub('', message)
        self._queue.put({'level': 'INFO', 'message': clean})
        self._write_file_only("INFO", message)

    def _make_progress_callback(self):
        """Return a closure that pushes throttled progress events to SSE."""
        last_pct = [-1]  # mutable container for closure

        def callback(current, total, stage):
            if self._cancel_event and self._cancel_event.is_set():
                return
            if total > 0:
                pct = int(current * 100 / total)
            else:
                pct = -1  # indeterminate
            if pct == last_pct[0]:
                return  # throttle: only fire on percentage change
            last_pct[0] = pct
            self._queue.put({
                'type': 'progress',
                'current': current,
                'total': total,
                'stage': stage,
                'percent': pct,
            })

        return callback

    def register_bar(self, bar):
        pass

    def unregister_bar(self, bar):
        pass


# ══════════════════════════════════════════════════════════════════
# WebDisplayHandler — DisplayHandler for SSE progress events
# ══════════════════════════════════════════════════════════════════


class WebDisplayHandler:
    """DisplayHandler that pushes progress to SSE queue for web UI.

    Implements the DisplayHandler protocol (porter_core) so that business
    classes route show_progress / show_status calls here instead of the
    NullDisplayHandler default.  Each call enqueues an SSE event that the
    frontend receives via /api/stream/<task_id>.
    """

    def __init__(self, log_queue, cancel_event=None):
        self._queue = log_queue
        self._cancel_event = cancel_event
        self._last_pct = -1

    def show_progress(self, current, total, message):
        if self._cancel_event and self._cancel_event.is_set():
            return
        if total > 0:
            pct = int(current * 100 / total)
            if pct != self._last_pct:
                self._last_pct = pct
                self._queue.put({
                    'type': 'progress',
                    'current': current,
                    'total': total,
                    'percent': pct,
                    'stage': message,
                })

    def finish_progress(self):
        self._last_pct = -1

    def show_status(self, message, level="info"):
        self._queue.put({'level': level.upper(), 'message': message})

    def show_banner(self, title, subtitle=None):
        pass  # Web UI has its own page headers


# ══════════════════════════════════════════════════════════════════
# WebPromptHandler — auto-confirm for web-initiated actions
# ══════════════════════════════════════════════════════════════════


class WebPromptHandler(mp.NonInteractivePromptHandler):
    """Auto-confirms destructive actions in web context (user already clicked the button)."""

    def confirm_destructive(self, message: str) -> bool:
        return True


# ══════════════════════════════════════════════════════════════════
# TaskState + TaskManager — background operation tracking
# ══════════════════════════════════════════════════════════════════

@dataclass
class TaskState:
    id: str
    operation: str
    description: str
    status: str = 'pending'       # pending | running | completed | failed | cancelled
    result: dict = field(default_factory=dict)
    error: str = ''
    thread: threading.Thread = field(default=None, repr=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    log_queue: queue.Queue = field(default_factory=queue.Queue, repr=False)
    started_at: float = 0.0
    finished_at: float = 0.0

    def elapsed(self):
        if self.started_at == 0:
            return 0
        end = self.finished_at if self.finished_at else time.time()
        return end - self.started_at

    def to_dict(self):
        return {
            'id': self.id,
            'operation': self.operation,
            'description': self.description,
            'status': self.status,
            'result': self.result,
            'error': self.error,
            'elapsed': round(self.elapsed(), 1),
            'started_at': self.started_at,
            'finished_at': self.finished_at,
        }


class TaskManager:
    """Manages background operations. One major operation at a time."""

    def __init__(self, task_db=None):
        self._tasks = {}
        self._lock = threading.RLock()
        self._db = task_db

    def submit(self, operation, description, target, audit_callback=None,
               source='web'):
        """Submit a new background task. Returns task_id or None if busy.

        target is called as target(task_id) so it can create a WebLogger.
        audit_callback is called with (task) in finally block for audit logging.
        """
        with self._lock:
            # Check for running tasks
            for t in self._tasks.values():
                if t.status == 'running':
                    return None

            task_id = uuid.uuid4().hex[:12]
            task = TaskState(id=task_id, operation=operation, description=description)
            self._tasks[task_id] = task

            # Persist to DB
            if self._db:
                self._db.insert(task_id, operation, description, source=source)

            def _run():
                task.status = 'running'
                task.started_at = time.time()
                if self._db:
                    self._db.update_status(task_id, 'running',
                                           started_at=task.started_at)
                try:
                    result = target(task_id)
                    if task.cancel_event.is_set():
                        task.status = 'cancelled'
                    else:
                        task.status = 'completed'
                        task.result = result if isinstance(result, dict) else {'success': bool(result)}
                except Exception as e:
                    task.status = 'failed'
                    task.error = str(e)
                finally:
                    task.finished_at = time.time()
                    # Persist final state to DB
                    if self._db:
                        self._db.update_status(
                            task_id, task.status,
                            result=task.result or None,
                            error=task.error,
                            finished_at=task.finished_at,
                        )
                    # Send sentinel so SSE stream knows we're done
                    task.log_queue.put(None)
                    # Audit callback for completion logging
                    if audit_callback:
                        try:
                            audit_callback(task)
                        except Exception:
                            pass

            thread = threading.Thread(target=_run, daemon=True)
            task.thread = thread
            thread.start()
            return task_id

    def get(self, task_id):
        # Check in-memory first (needed for thread/queue/cancel)
        task = self._tasks.get(task_id)
        if task:
            return task
        # Fall back to DB for historical tasks
        if self._db:
            return self._db.get(task_id)
        return None

    def list_all(self):
        """Return task history from DB, merging live elapsed for running tasks."""
        if not self._db:
            with self._lock:
                return [t.to_dict() for t in self._tasks.values()]

        entries, _ = self._db.get_entries(limit=100, offset=0)
        # Merge live elapsed from in-memory state for running tasks
        with self._lock:
            for entry in entries:
                live = self._tasks.get(entry['id'])
                if live and live.status == 'running':
                    entry['elapsed'] = round(live.elapsed(), 1)
                    entry['status'] = live.status
        return entries

    def cancel(self, task_id):
        task = self._tasks.get(task_id)
        if task and task.status == 'running':
            task.cancel_event.set()
            return True
        return False

    def is_busy(self):
        with self._lock:
            return any(t.status == 'running' for t in self._tasks.values())


# ══════════════════════════════════════════════════════════════════
# PipelineScheduler — recurring automatic pipeline execution
# ══════════════════════════════════════════════════════════════════

_SCHEDULER_DEFAULTS = {
    'enabled': False,
    'interval_hours': 24,
    'playlists': [],
    'preset': None,
    'retry_minutes': 15,
    'max_retries': 3,
}


class PipelineScheduler:
    """Runs the pipeline on a recurring schedule using threading.Timer chains.

    Each timer firing schedules the next one, allowing clean cancellation
    and reconfiguration without blocked sleeping threads.

    Lifecycle: created in start_server(), stored on AppContext.
    start() begins the timer chain if config says enabled.
    stop() cancels any pending timer (called on server shutdown).
    reconfigure() updates settings and restarts the timer if needed.
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._timer = None
        self._lock = threading.RLock()

        # Config (loaded from config.yaml)
        self._enabled = False
        self._interval_hours = 24
        self._playlists = []
        self._preset = None
        self._retry_minutes = 15
        self._max_retries = 3

        # Runtime state
        self._last_run_time = None
        self._last_run_status = ''
        self._last_run_error = ''
        self._next_run_time = None
        self._retry_count = 0
        self._running = False

    def _load_config(self):
        """Read scheduler settings from config.yaml."""
        config = self._ctx.get_config()
        sched = config.get_setting('scheduler') or {}
        self._enabled = sched.get('enabled', False)
        self._interval_hours = sched.get('interval_hours', 24)
        self._playlists = sched.get('playlists', [])
        self._preset = sched.get('preset')
        self._retry_minutes = sched.get('retry_minutes', 15)
        self._max_retries = sched.get('max_retries', 3)

    def start(self):
        """Load config and start timer chain if enabled. Called at server startup."""
        with self._lock:
            self._load_config()
            if self._enabled:
                self._schedule_next(self._interval_hours * 3600)

    def stop(self):
        """Cancel any pending timer. Called at server shutdown."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._next_run_time = None

    def reconfigure(self, new_settings):
        """Update scheduler config and restart timer chain.

        Called by POST /api/scheduler/config.
        new_settings is the full scheduler dict to write to config.yaml.
        """
        with self._lock:
            config = self._ctx.get_config()
            config.update_setting('scheduler', new_settings)

            if self._timer:
                self._timer.cancel()
                self._timer = None
                self._next_run_time = None

            self._load_config()
            self._retry_count = 0
            if self._enabled:
                self._schedule_next(self._interval_hours * 3600)

    def run_now(self):
        """Trigger an immediate scheduled run. Returns True if submitted."""
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
                self._next_run_time = None
            return self._execute()

    def _schedule_next(self, delay_seconds):
        """Schedule the next execution after delay_seconds."""
        self._timer = threading.Timer(delay_seconds, self._on_timer)
        self._timer.daemon = True
        self._timer.name = 'PipelineScheduler'
        self._timer.start()
        self._next_run_time = time.time() + delay_seconds

    def _on_timer(self):
        """Timer callback. Attempts to execute, retries or reschedules."""
        with self._lock:
            self._timer = None
            self._next_run_time = None
            success = self._execute()

            if not success and self._retry_count < self._max_retries:
                self._retry_count += 1
                self._schedule_next(self._retry_minutes * 60)
            elif not success:
                # Exhausted retries — schedule next full cycle
                self._last_run_status = 'skipped'
                self._last_run_error = (
                    f'Skipped after {self._max_retries} retries (busy)')
                self._last_run_time = time.time()
                self._retry_count = 0
                if self._enabled:
                    self._schedule_next(self._interval_hours * 3600)

    def _execute(self):
        """Submit pipeline task to TaskManager. Returns True if submitted."""
        if self._ctx.task_manager.is_busy():
            return False

        self._running = True
        # Capture current config for the closure
        playlists_filter = list(self._playlists)
        preset = self._preset

        def _run(task_id):
            logger = self._ctx.make_logger(task_id, verbose=False)
            config = mp.ConfigManager(
                logger=logger,
                audit_logger=self._ctx.audit_logger,
                audit_source='scheduler',
            )
            profile = self._ctx.get_output_profile(config)
            workers = config.get_setting('workers', mp.DEFAULT_WORKERS)
            deps = mp.DependencyChecker(logger)
            quality_preset = preset or profile.quality_preset
            display = self._ctx.make_display_handler(task_id)
            task = self._ctx.task_manager.get(task_id)

            orchestrator = mp.PipelineOrchestrator(
                logger, deps, config,
                quality_preset=quality_preset,
                workers=workers,
                output_profile=profile,
                display_handler=display,
                cancel_event=task.cancel_event,
                audit_logger=self._ctx.audit_logger,
                audit_source='scheduler',
            )

            # Determine which playlists to process
            if playlists_filter:
                to_run = [
                    p for p in config.playlists
                    if p.key in playlists_filter
                ]
            else:
                to_run = list(config.playlists)

            if not to_run:
                logger.warning("No playlists to process")
                return {'success': True, 'total': 0, 'ok': 0, 'failed': 0}

            logger.info(
                f"Scheduled pipeline: {len(to_run)} playlist"
                f"{'s' if len(to_run) != 1 else ''}")
            aggregate = mp.AggregateStatistics()

            for i, pl in enumerate(to_run):
                if task.cancel_event.is_set():
                    break
                logger.info(f"\n{'=' * 60}")
                logger.info(
                    f"Processing {i + 1}/{len(to_run)}: {pl.name}")
                logger.info(f"{'=' * 60}")
                idx = config.playlists.index(pl) + 1
                orchestrator.run_full_pipeline(
                    playlist=str(idx), auto=True,
                    copy_to_usb=False, dry_run=False, verbose=False,
                    quality_preset=quality_preset,
                )
                aggregate.add_playlist_result(orchestrator.stats)

            aggregate.end_time = time.time()
            agg_result = aggregate.to_result()
            return {
                'success': agg_result.success,
                'total': agg_result.total_playlists,
                'ok': agg_result.successful_playlists,
                'failed': agg_result.failed_playlists,
            }

        def _audit_callback(task):
            with self._lock:
                self._running = False
                self._last_run_time = time.time()
                self._last_run_status = task.status
                self._last_run_error = task.error or ''
                self._retry_count = 0
                if self._enabled and not self._timer:
                    self._schedule_next(self._interval_hours * 3600)

            self._ctx.audit_logger.log(
                'scheduled_pipeline',
                f"Scheduled pipeline {task.status}",
                task.status,
                params={'result': task.result, 'error': task.error},
                duration_s=task.elapsed(),
                source='scheduler',
            )

        pl_desc = ', '.join(playlists_filter) if playlists_filter else 'all'
        desc = f'Scheduled pipeline: {pl_desc}'

        task_id = self._ctx.task_manager.submit(
            'scheduled_pipeline', desc, _run,
            audit_callback=_audit_callback,
            source='scheduler',
        )

        if task_id is None:
            self._running = False
            return False

        return True

    def status(self):
        """Return scheduler status for API/UI consumption."""
        with self._lock:
            return {
                'enabled': self._enabled,
                'interval_hours': self._interval_hours,
                'playlists': list(self._playlists),
                'preset': self._preset,
                'retry_minutes': self._retry_minutes,
                'max_retries': self._max_retries,
                'running': self._running,
                'last_run_time': self._last_run_time,
                'last_run_iso': (
                    datetime.fromtimestamp(self._last_run_time).isoformat()
                    if self._last_run_time else None
                ),
                'last_run_status': self._last_run_status,
                'last_run_error': self._last_run_error,
                'next_run_time': self._next_run_time,
                'next_run_iso': (
                    datetime.fromtimestamp(self._next_run_time).isoformat()
                    if self._next_run_time else None
                ),
                'retry_count': self._retry_count,
            }


# ══════════════════════════════════════════════════════════════════
# AppContext — shared state for Flask routes (replaces closures)
# ══════════════════════════════════════════════════════════════════

@dataclass
class AppContext:
    """Shared application state accessible via current_app.config['CTX'].

    Replaces closure variables that were previously captured inside
    create_app().  API routes in web_api.py access this through
    ``current_app.config['CTX']``.
    """

    task_manager: TaskManager
    audit_logger: object  # mp.AuditLogger
    sync_tracker: object  # mp.SyncTracker
    api_key: str
    project_root: Path
    scheduler: 'PipelineScheduler | None' = None

    # ── Request-scoped helpers ─────────────────────────────────

    def detect_source(self):
        """Detect request source: 'ios', 'api', or 'web'."""
        ua = request.headers.get('User-Agent', '')
        if 'MusicPorter-iOS' in ua:
            return 'ios'
        if request.headers.get('Authorization', '').startswith('Bearer '):
            return 'api'
        return 'web'

    def client_info(self):
        """Return dict of client request metadata for audit logging."""
        return {
            'ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'method': request.method,
            'path': request.path,
        }

    # ── Factory helpers ────────────────────────────────────────

    def make_logger(self, task_id, verbose=False):
        """Create a WebLogger wired to the task's SSE queue."""
        task = self.task_manager.get(task_id)
        return WebLogger(task.log_queue, task.cancel_event, verbose=verbose)

    def make_display_handler(self, task_id):
        """Create a WebDisplayHandler wired to the task's SSE queue."""
        task = self.task_manager.get(task_id)
        return WebDisplayHandler(task.log_queue, task.cancel_event)

    def get_config(self):
        """Create a fresh ConfigManager with audit logging."""
        logger = mp.Logger(verbose=False)
        return mp.ConfigManager(logger=logger, audit_logger=self.audit_logger,
                                audit_source='web')

    def get_output_profile(self, config):
        """Return the active OutputProfile, refreshed from config.yaml."""
        mp.load_output_profiles(config)
        output_type = config.get_setting('output_type', mp.DEFAULT_OUTPUT_TYPE)
        if output_type not in mp.OUTPUT_PROFILES:
            output_type = mp.DEFAULT_OUTPUT_TYPE
        return mp.OUTPUT_PROFILES[output_type]

    def get_server_name(self):
        """Return configured server_name or hostname."""
        config = self.get_config()
        return config.get_setting('server_name') or socket.gethostname()

    def safe_dir(self, directory):
        """Validate directory is within project root. Returns str or None."""
        try:
            resolved = Path(directory).resolve()
            root = self.project_root.resolve()
            if not str(resolved).startswith(str(root)):
                return None
            return str(resolved)
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _get_freshness_level(last_modified: datetime | None, today: date) -> str:
    """Return freshness level name for a playlist's last_modified date."""
    if not last_modified:
        return "outdated"
    age_days = (today - last_modified.date()).days
    if age_days <= mp.FRESHNESS_CURRENT_DAYS:
        return "current"
    elif age_days <= mp.FRESHNESS_RECENT_DAYS:
        return "recent"
    elif age_days <= mp.FRESHNESS_STALE_DAYS:
        return "stale"
    else:
        return "outdated"


# ══════════════════════════════════════════════════════════════════
# Flask Application Factory
# ══════════════════════════════════════════════════════════════════

def create_app(project_root=None, no_auth=False, server_host=None,
               server_port=None, external_url=None,
               behind_proxy=False, proxy_count=1):
    """Create and configure the Flask application."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent

    project_root = Path(project_root)
    template_dir = project_root / 'templates'

    app = Flask(__name__, template_folder=str(template_dir))
    app.config['PROJECT_ROOT'] = str(project_root)
    app.config['NO_AUTH'] = no_auth
    app.config['SERVER_HOST'] = server_host
    app.config['SERVER_PORT'] = server_port
    app.config['EXTERNAL_URL'] = external_url

    # Secret key for Flask session cookies (server mode login).
    # Ephemeral — regenerated each server start, invalidating all sessions.
    if not no_auth:
        import secrets as _secrets
        app.secret_key = _secrets.token_hex(32)

    # ── Shared Application Context ───────────────────────────
    _boot_config = mp.ConfigManager(logger=mp.Logger(verbose=False))
    _api_key = _boot_config.ensure_api_key()
    _db_path = str(project_root / mp.DEFAULT_DB_FILE)

    _task_db = mp.TaskHistoryDB(_db_path)
    ctx = AppContext(
        task_manager=TaskManager(task_db=_task_db),
        audit_logger=mp.AuditLogger(_db_path),
        sync_tracker=mp.SyncTracker(_db_path),
        api_key=_api_key,
        project_root=project_root,
    )
    app.config['CTX'] = ctx

    # ── Register API Blueprint ───────────────────────────────
    from web_api import api_bp
    app.register_blueprint(api_bp)

    # ── CORS headers for iOS companion app ───────────────────
    @app.after_request
    def _add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

    @app.context_processor
    def _inject_auth_context():
        return {'server_mode': not no_auth}

    # ── API key authentication middleware ─────────────────────
    @app.before_request
    def _check_api_auth():
        # Web mode (--no-auth): skip all authentication
        if app.config.get('NO_AUTH'):
            return None
        # Always allow the login/logout pages and static files
        if request.path in ('/login', '/logout'):
            return None
        # Check auth sources
        has_session = session.get('authenticated') is True
        has_bearer = False
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            if auth_header[7:] == ctx.api_key:
                has_bearer = True
        # API routes: accept session OR Bearer token
        if request.path.startswith('/api/'):
            if request.method == 'OPTIONS':
                return None
            if has_session or has_bearer:
                return None
            ctx.audit_logger.log('auth_denied', f"Unauthorized: {request.path}",
                                 'failed', params=ctx.client_info(),
                                 source=ctx.detect_source())
            return jsonify({'error': 'Unauthorized — provide Authorization: Bearer <api_key>'}), 401
        # HTML pages: require session, redirect to login if missing
        if not has_session:
            return redirect(url_for('login_page'))
        return None

    # ── Login / Logout ────────────────────────────────────────

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if app.config.get('NO_AUTH'):
            return redirect(url_for('dashboard'))
        if session.get('authenticated'):
            return redirect(url_for('dashboard'))
        error = None
        if request.method == 'POST':
            submitted_key = request.form.get('api_key', '').strip()
            if submitted_key == ctx.api_key:
                session['authenticated'] = True
                session.permanent = False
                ctx.audit_logger.log('login', 'Login success', 'completed',
                                     params=ctx.client_info(), source='web')
                return redirect(url_for('dashboard'))
            ctx.audit_logger.log('login', 'Login failed', 'failed',
                                 params=ctx.client_info(), source='web')
            error = 'Invalid API key. Check the server terminal for the correct key.'
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        ctx.audit_logger.log('logout', 'User logged out', 'completed',
                             params=ctx.client_info(), source='web')
        session.clear()
        return redirect(url_for('login_page'))

    # ── Page Routes ──────────────────────────────────────────────

    @app.route('/')
    def dashboard():
        return render_template('dashboard.html')

    @app.route('/playlists')
    def playlists_page():
        return render_template('playlists.html')

    @app.route('/pipeline')
    def pipeline_page():
        return render_template('pipeline.html')

    @app.route('/convert')
    def convert_page():
        return render_template('convert.html')

    @app.route('/tags')
    def tags_page():
        return render_template('tags.html')

    @app.route('/cover-art')
    def cover_art_page():
        return render_template('cover_art.html')

    @app.route('/sync')
    def sync_page():
        return render_template('sync.html')

    @app.route('/usb')
    def usb_page():
        return redirect(url_for('sync_page'))

    @app.route('/sync-status')
    def sync_status_page():
        return redirect(url_for('sync_page'))

    @app.route('/settings')
    def settings_page():
        return render_template('settings.html')

    @app.route('/operations')
    def operations_page():
        return render_template('operations.html')

    @app.route('/audit')
    def audit_page():
        return render_template('audit.html')

    @app.route('/about')
    def about_page():
        return render_template('about.html')

    if behind_proxy:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_count,
            x_proto=proxy_count,
            x_host=proxy_count,
        )

    return app


# ══════════════════════════════════════════════════════════════════
# Server Entry Point
# ══════════════════════════════════════════════════════════════════

def _kill_port_process(port):
    """Kill any existing process listening on the given port (best-effort)."""
    try:
        system = platform.system()
        if system in ('Darwin', 'Linux'):
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return
            for pid_str in result.stdout.strip().splitlines():
                pid = int(pid_str)
                if pid == os.getpid():
                    continue
                print(f"  Killing existing process on port {port} (PID {pid})...")
                os.kill(pid, signal.SIGTERM)
        elif system == 'Windows':
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return
            for line in result.stdout.splitlines():
                if 'LISTENING' in line and f':{port}' in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    if pid == os.getpid():
                        continue
                    print(f"  Killing existing process on port {port} (PID {pid})...")
                    subprocess.run(
                        ['taskkill', '/PID', str(pid), '/F'],
                        capture_output=True, timeout=5,
                    )
    except Exception as e:
        print(f"  Warning: could not free port {port}: {e}")


def _print_pairing_qr(host, port, api_key, external_url=None):
    """Print a QR code to the terminal for iOS app pairing.

    The QR code encodes a JSON payload with the server address and API key:
    {"host": "...", "port": 5555, "key": "...", "url": "..."}
    """
    try:
        import io

        import segno
        qr_data = {"host": host, "port": port, "key": api_key}
        if external_url:
            qr_data["url"] = external_url
        payload = json.dumps(qr_data)
        qr = segno.make(payload)
        buf = io.StringIO()
        qr.terminal(out=buf, compact=True)
        # Indent each line for consistent formatting
        for line in buf.getvalue().splitlines():
            print(f"  {line}")
        print()
    except ImportError:
        print("  (Install 'segno' for QR code: pip install segno)")
    except Exception:
        pass  # Gracefully skip QR on any error


def start_server(host='127.0.0.1', port=5555, no_auth=False,
                  show_api_key=False, enable_bonjour=False,
                  behind_proxy=False, proxy_count=1):
    """Start the Flask development server.

    Args:
        host: Host to bind.
        port: Port to bind.
        no_auth: If True, skip API key authentication on /api/* routes.
        show_api_key: If True, print the API key at startup.
        enable_bonjour: If True, advertise via mDNS/Bonjour.
        behind_proxy: If True, trust X-Forwarded-* headers from reverse proxy.
        proxy_count: Number of trusted proxy hops (default: 1).
    """
    _kill_port_process(port)

    # Determine local network IP for iOS connection info
    local_ip = BonjourAdvertiser._get_local_ip() or host
    external_url = None

    if not no_auth:
        config = mp.ConfigManager(logger=mp.Logger(verbose=False))
        api_key = config.ensure_api_key()
        external_url = config.get_setting('external_url')

        # Always show full API key and connection details for server mode
        print(f"\n  ── Server Mode ({'auth enabled' if not no_auth else 'no auth'}) ──")
        print(f"  Server:    http://{host}:{port}")
        if host == '0.0.0.0':
            print(f"  Local URL: http://{local_ip}:{port}")
        if external_url:
            print(f"  External:  {external_url}")
        print(f"  API Key:   {api_key}")
        print("  Auth:      Bearer token required on /api/* routes")
        print()
        print("  ── iOS Companion App Connection ──")
        print("  1. Open the Music Porter iOS app")
        if external_url:
            print(f"  2. Enter server address: {external_url}")
        else:
            print(f"  2. Enter server address: {local_ip}:{port}")
        print(f"  3. Enter API key: {api_key}")
        print("  4. Or scan the QR code below:")
        print()
        _print_pairing_qr(local_ip, port, api_key, external_url=external_url)
    else:
        print("\n  ── Web Dashboard Mode (no auth) ──")
        print(f"  Server:  http://{host}:{port}")

    if behind_proxy:
        print(f"\n  Proxy:   enabled ({proxy_count} hop{'s' if proxy_count != 1 else ''})")

    print("\n  Press Ctrl+C to stop\n")

    app = create_app(no_auth=no_auth, server_host=local_ip,
                      server_port=port, external_url=external_url,
                      behind_proxy=behind_proxy, proxy_count=proxy_count)

    # Initialize and start the pipeline scheduler
    ctx = app.config['CTX']
    ctx.scheduler = PipelineScheduler(ctx)
    ctx.scheduler.start()

    # Bonjour/mDNS advertisement
    bonjour = None
    if enable_bonjour and host != '127.0.0.1':
        bonjour = BonjourAdvertiser(port)
        bonjour.start()

    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        ctx.scheduler.stop()
        if bonjour:
            bonjour.stop()


# ══════════════════════════════════════════════════════════════════
# Bonjour/mDNS Service Advertisement
# ══════════════════════════════════════════════════════════════════

class BonjourAdvertiser:
    """Advertises the music-porter server via mDNS/Bonjour.

    Uses zeroconf to register a _music-porter._tcp.local. service so
    iOS companion apps can discover the server on the local network.
    """

    SERVICE_TYPE = "_music-porter._tcp.local."

    def __init__(self, port):
        self._port = port
        self._zeroconf = None
        self._info = None

    def start(self):
        """Register the mDNS service."""
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            print("  Bonjour: skipped (zeroconf not installed)")
            return

        logger = mp.Logger(verbose=False)
        config = mp.ConfigManager(logger=logger)
        hostname = config.get_setting('server_name') or socket.gethostname()
        # Get local IP for service registration
        local_ip = self._get_local_ip()
        if not local_ip:
            print("  Bonjour: skipped (could not determine local IP)")
            return

        # Service name must be unique; use hostname without special chars
        safe_name = hostname.replace('.', '-')
        self._info = ServiceInfo(
            self.SERVICE_TYPE,
            f"Music Porter on {safe_name}.{self.SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                'version': mp.VERSION,
                'platform': mp.get_os_display_name(),
                'api_version': '1',
            },
        )
        try:
            self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._info, allow_name_change=True)
            print(f"  Bonjour: advertising as _music-porter._tcp on {local_ip}:{self._port}")
        except Exception as e:
            print(f"  Bonjour: failed to register ({e})")
            self._zeroconf = None
            self._info = None

    def stop(self):
        """Unregister the mDNS service."""
        if self._zeroconf and self._info:
            self._zeroconf.unregister_service(self._info)
            self._zeroconf.close()

    @staticmethod
    def _get_local_ip():
        """Get the local network IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None


if __name__ == '__main__':
    start_server()
