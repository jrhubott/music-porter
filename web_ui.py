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
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)

import porter_core as mp

# Initialize third-party imports once at load time.
# The web server runs inside the venv so all packages are already available.
# This avoids DependencyChecker's pip/os.execv() in background threads.
mp._init_third_party()

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

    def __init__(self):
        self._tasks = {}
        self._lock = threading.RLock()

    def submit(self, operation, description, target):
        """Submit a new background task. Returns task_id or None if busy.

        target is called as target(task_id) so it can create a WebLogger.
        """
        with self._lock:
            # Check for running tasks
            for t in self._tasks.values():
                if t.status == 'running':
                    return None

            task_id = uuid.uuid4().hex[:12]
            task = TaskState(id=task_id, operation=operation, description=description)
            self._tasks[task_id] = task

            def _run():
                task.status = 'running'
                task.started_at = time.time()
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
                    # Send sentinel so SSE stream knows we're done
                    task.log_queue.put(None)

            thread = threading.Thread(target=_run, daemon=True)
            task.thread = thread
            thread.start()
            return task_id

    def get(self, task_id):
        return self._tasks.get(task_id)

    def list_all(self):
        with self._lock:
            return [t.to_dict() for t in self._tasks.values()]

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

def create_app(project_root=None, no_auth=False):
    """Create and configure the Flask application."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent

    project_root = Path(project_root)
    template_dir = project_root / 'templates'

    app = Flask(__name__, template_folder=str(template_dir))
    app.config['PROJECT_ROOT'] = str(project_root)
    app.config['NO_AUTH'] = no_auth

    # Secret key for Flask session cookies (server mode login).
    # Ephemeral — regenerated each server start, invalidating all sessions.
    if not no_auth:
        import secrets as _secrets
        app.secret_key = _secrets.token_hex(32)

    task_manager = TaskManager()

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
    # Ensure an API key exists in config.yaml
    _boot_config = mp.ConfigManager(logger=mp.Logger(verbose=False))
    _api_key = _boot_config.ensure_api_key()

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
            if auth_header[7:] == _api_key:
                has_bearer = True
        # API routes: accept session OR Bearer token
        if request.path.startswith('/api/'):
            if request.method == 'OPTIONS':
                return None
            if has_session or has_bearer:
                return None
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
            if submitted_key == _api_key:
                session['authenticated'] = True
                session.permanent = False
                return redirect(url_for('dashboard'))
            error = 'Invalid API key. Check the server terminal for the correct key.'
        return render_template('login.html', error=error)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login_page'))

    # ── Helper to create a WebLogger for a task ──────────────────
    def _make_logger(task_id, verbose=False):
        task = task_manager.get(task_id)
        return WebLogger(task.log_queue, task.cancel_event, verbose=verbose)

    def _make_display_handler(task_id):
        """Create a WebDisplayHandler wired to the task's SSE queue."""
        task = task_manager.get(task_id)
        return WebDisplayHandler(task.log_queue, task.cancel_event)

    def _get_config():
        logger = mp.Logger(verbose=False)
        return mp.ConfigManager(logger=logger)

    def _get_output_profile(config):
        mp.load_output_profiles(config)  # refresh from config.yaml
        output_type = config.get_setting('output_type', mp.DEFAULT_OUTPUT_TYPE)
        if output_type not in mp.OUTPUT_PROFILES:
            output_type = mp.DEFAULT_OUTPUT_TYPE
        return mp.OUTPUT_PROFILES[output_type]

    def _safe_dir(directory):
        """Validate directory is within project root."""
        try:
            resolved = Path(directory).resolve()
            root = project_root.resolve()
            if not str(resolved).startswith(str(root)):
                return None
            return str(resolved)
        except Exception:
            return None

    # ── API: Auth & Server Info ──────────────────────────────────

    @app.route('/api/auth/validate', methods=['POST'])
    def api_auth_validate():
        """Validate API key and return server identity."""
        return jsonify({
            'valid': True,
            'version': mp.VERSION,
            'server_name': socket.gethostname(),
            'api_version': 1,
        })

    @app.route('/api/server-info')
    def api_server_info():
        """Return server metadata for client discovery."""
        config = _get_config()
        mp.load_output_profiles(config)
        return jsonify({
            'name': socket.gethostname(),
            'version': mp.VERSION,
            'platform': mp.get_os_display_name(),
            'profiles': list(mp.OUTPUT_PROFILES.keys()),
            'api_version': 1,
        })

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

    @app.route('/usb')
    def usb_page():
        if not app.config.get('NO_AUTH'):
            return redirect(url_for('dashboard'))
        return render_template('usb_sync.html')

    @app.route('/settings')
    def settings_page():
        return render_template('settings.html')

    @app.route('/operations')
    def operations_page():
        return render_template('operations.html')

    # ── API: Dashboard Status ────────────────────────────────────

    @app.route('/api/status')
    def api_status():
        config = _get_config()
        profile = _get_output_profile(config)

        # Cookie status
        cookie_mgr = mp.CookieManager('cookies.txt', mp.Logger(verbose=False))
        cs = cookie_mgr.validate()
        cookie_data = {
            'valid': cs.valid,
            'exists': cs.exists,
            'reason': cs.reason,
            'days_remaining': round(cs.days_until_expiration) if cs.days_until_expiration else None,
        }

        # Library stats (quick scan)
        export_dir = mp.get_export_dir(profile.name)
        total_files = 0
        total_size = 0
        playlist_count = 0
        export_path = Path(export_dir)
        if export_path.exists():
            for subdir in export_path.iterdir():
                if subdir.is_dir():
                    playlist_count += 1
                    for f in subdir.glob('*.mp3'):
                        total_files += 1
                        total_size += f.stat().st_size

        return jsonify({
            'version': mp.VERSION,
            'cookies': cookie_data,
            'library': {
                'playlists': playlist_count,
                'files': total_files,
                'size_mb': round(total_size / (1024 * 1024), 1) if total_size else 0,
            },
            'profile': profile.name,
            'busy': task_manager.is_busy(),
        })

    # ── API: Cookie Management ────────────────────────────────────

    @app.route('/api/cookies/browsers')
    def api_cookies_browsers():
        cookie_mgr = mp.CookieManager('cookies.txt', mp.Logger(verbose=False))
        default_browser = cookie_mgr._detect_default_browser()
        installed = cookie_mgr._detect_installed_browsers()
        return jsonify({
            'default': default_browser,
            'installed': installed,
        })

    @app.route('/api/cookies/refresh', methods=['POST'])
    def api_cookies_refresh():
        data = request.get_json(silent=True) or {}
        browser = data.get('browser', 'auto')
        verbose = data.get('verbose', False)

        desc = f'Cookie refresh ({browser})'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)

            # Log current status first
            cookie_mgr = mp.CookieManager('cookies.txt', logger)
            status = cookie_mgr.validate()
            if status.valid:
                logger.ok(f"Current status: {status.reason}")
            elif status.exists:
                logger.warn(f"Current status: {status.reason}")
            else:
                logger.warn("No cookies file found")

            # Attempt refresh
            success = cookie_mgr.auto_refresh(backup=True, browser=browser)

            if success:
                new_status = cookie_mgr.validate()
                return {'success': True, 'reason': new_status.reason,
                        'days_remaining': round(new_status.days_until_expiration) if new_status.days_until_expiration else None}
            else:
                return {'success': False}

        task_id = task_manager.submit('cookie_refresh', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: Library Summary ──────────────────────────────────────

    @app.route('/api/summary')
    def api_summary():
        config = _get_config()
        profile = _get_output_profile(config)
        export_dir = mp.get_export_dir(profile.name)

        quiet_logger = mp.Logger(verbose=False)
        mgr = mp.SummaryManager(logger=quiet_logger)
        export_path = Path(export_dir)

        if not export_path.exists():
            return jsonify({
                'total_playlists': 0, 'total_files': 0,
                'total_size_bytes': 0, 'scan_duration': 0,
                'tag_integrity': {'checked': 0, 'protected': 0, 'missing': 0},
                'cover_art': {'with_art': 0, 'without_art': 0, 'original': 0, 'resized': 0},
                'playlists': [], 'profile': profile.name,
            })

        start_time = time.time()

        playlist_dirs = mgr._scan_playlists(export_path)
        for pdir in playlist_dirs:
            ps = mgr._analyze_playlist(pdir)
            if ps:
                mgr.stats.playlists.append(ps)

        mgr.stats.total_playlists = len(mgr.stats.playlists)
        mgr.stats.total_files = sum(p.file_count for p in mgr.stats.playlists)
        mgr.stats.total_size_bytes = sum(p.total_size_bytes for p in mgr.stats.playlists)

        mgr._check_tag_integrity()

        scan_duration = round(time.time() - start_time, 2)

        today = date.today()
        freshness_counts = {"current": 0, "recent": 0, "stale": 0, "outdated": 0}

        playlists_json = []
        for p in mgr.stats.playlists:
            freshness = _get_freshness_level(p.last_modified, today)
            freshness_counts[freshness] += 1
            playlists_json.append({
                'name': p.name,
                'file_count': p.file_count,
                'size_bytes': p.total_size_bytes,
                'avg_size_mb': round(p.avg_file_size_mb, 1),
                'last_modified': p.last_modified.isoformat() if p.last_modified else None,
                'freshness': freshness,
                'tags_checked': p.sample_files_checked,
                'tags_protected': p.sample_files_with_tags,
                'cover_with': p.files_with_cover_art,
                'cover_without': p.files_without_cover_art,
            })

        return jsonify({
            'total_playlists': mgr.stats.total_playlists,
            'total_files': mgr.stats.total_files,
            'total_size_bytes': mgr.stats.total_size_bytes,
            'scan_duration': scan_duration,
            'tag_integrity': {
                'checked': mgr.stats.sample_size,
                'protected': mgr.stats.files_with_protection_tags,
                'missing': mgr.stats.files_missing_protection_tags,
            },
            'cover_art': {
                'with_art': mgr.stats.files_with_cover_art,
                'without_art': mgr.stats.files_without_cover_art,
                'original': mgr.stats.files_with_original_cover_art,
                'resized': mgr.stats.files_with_resized_cover_art,
            },
            'freshness': freshness_counts,
            'playlists': playlists_json,
            'profile': profile.name,
        })

    # ── API: Library Stats (music/ directory) ───────────────────

    @app.route('/api/library-stats')
    def api_library_stats():
        config = _get_config()
        profile = _get_output_profile(config)

        quiet_logger = mp.Logger(verbose=False)
        mgr = mp.SummaryManager(logger=quiet_logger)
        stats = mgr.scan_music_library(
            music_dir=mp.DEFAULT_MUSIC_DIR,
            export_profile=profile.name,
        )

        if stats is None:
            return jsonify({
                'total_playlists': 0, 'total_files': 0,
                'total_size_bytes': 0, 'total_exported': 0,
                'total_unconverted': 0, 'scan_duration': 0,
            })

        return jsonify({
            'total_playlists': stats.total_playlists,
            'total_files': stats.total_files,
            'total_size_bytes': stats.total_size_bytes,
            'total_exported': stats.total_exported,
            'total_unconverted': stats.total_unconverted,
            'scan_duration': round(stats.scan_duration, 2),
        })

    # ── API: Playlists CRUD ──────────────────────────────────────

    @app.route('/api/playlists', methods=['GET'])
    def api_playlists_list():
        config = _get_config()
        return jsonify([
            {'key': p.key, 'url': p.url, 'name': p.name}
            for p in config.playlists
        ])

    @app.route('/api/playlists', methods=['POST'])
    def api_playlists_add():
        data = request.get_json(force=True)
        key = data.get('key', '').strip()
        url = data.get('url', '').strip()
        name = data.get('name', '').strip()

        if not key or not url or not name:
            return jsonify({'error': 'key, url, and name are required'}), 400

        config = _get_config()
        if config.add_playlist(key, url, name):
            return jsonify({'ok': True})
        return jsonify({'error': f"Playlist key '{key}' already exists"}), 409

    @app.route('/api/playlists/<key>', methods=['PUT'])
    def api_playlists_update(key):
        data = request.get_json(force=True)
        config = _get_config()
        if config.update_playlist(key, url=data.get('url'), name=data.get('name')):
            return jsonify({'ok': True})
        return jsonify({'error': f"Playlist '{key}' not found"}), 404

    @app.route('/api/playlists/<key>', methods=['DELETE'])
    def api_playlists_delete(key):
        config = _get_config()
        if config.remove_playlist(key):
            return jsonify({'ok': True})
        return jsonify({'error': f"Playlist '{key}' not found"}), 404

    # ── API: Settings ────────────────────────────────────────────

    @app.route('/api/settings', methods=['GET'])
    def api_settings_get():
        config = _get_config()
        profiles = {
            name: {'description': p.description, 'quality_preset': p.quality_preset,
                   'artwork_size': p.artwork_size, 'id3_version': p.id3_version,
                   'directory_structure': p.directory_structure,
                   'filename_format': p.filename_format}
            for name, p in mp.OUTPUT_PROFILES.items()
        }
        return jsonify({
            'settings': config.settings,
            'profiles': profiles,
            'quality_presets': list(mp.QUALITY_PRESETS.keys()),
            'dir_structures': list(mp.VALID_DIR_STRUCTURES),
            'filename_formats': list(mp.VALID_FILENAME_FORMATS),
        })

    @app.route('/api/settings', methods=['POST'])
    def api_settings_update():
        data = request.get_json(force=True)
        config = _get_config()
        for key, value in data.items():
            config.update_setting(key, value)
        return jsonify({'ok': True})

    # ── API: Directory Listings ──────────────────────────────────

    @app.route('/api/directories/music')
    def api_dirs_music():
        music_dir = project_root / mp.DEFAULT_MUSIC_DIR
        dirs = []
        if music_dir.exists():
            for d in sorted(music_dir.iterdir()):
                if d.is_dir() and not d.name.startswith('.'):
                    dirs.append(d.name)
        return jsonify(dirs)

    @app.route('/api/directories/export')
    def api_dirs_export():
        config = _get_config()
        profile = _get_output_profile(config)
        export_dir = project_root / mp.get_export_dir(profile.name)
        playlist_map = {p.key: p.name for p in config.playlists}
        dirs = []
        if export_dir.exists():
            for d in sorted(export_dir.iterdir()):
                if d.is_dir() and not d.name.startswith('.'):
                    file_count = len(list(d.rglob('*.mp3')))
                    dirs.append({
                        'name': d.name,
                        'display_name': playlist_map.get(d.name, d.name),
                        'files': file_count,
                    })
        return jsonify(dirs)

    # ── API: Pipeline ────────────────────────────────────────────

    @app.route('/api/pipeline/run', methods=['POST'])
    def api_pipeline_run():
        data = request.get_json(force=True)
        playlist_key = data.get('playlist')
        url = data.get('url')
        auto = data.get('auto', False)
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)
        preset = data.get('preset')
        copy_to_usb = data.get('copy_to_usb', False)
        # USB sync is not available in server mode — force off
        if not app.config.get('NO_AUTH'):
            copy_to_usb = False
        dir_structure = data.get('dir_structure')
        filename_format = data.get('filename_format')

        if not auto and not playlist_key and not url:
            return jsonify({'error': 'Specify playlist, url, or auto'}), 400

        desc = 'Pipeline: all playlists' if auto else f'Pipeline: {playlist_key or url}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            # Apply dir_structure/filename_format overrides
            if dir_structure or filename_format:
                from dataclasses import replace
                overrides = {}
                if dir_structure:
                    overrides['directory_structure'] = dir_structure
                if filename_format:
                    overrides['filename_format'] = filename_format
                profile = replace(profile, **overrides)
            usb_dir = config.get_setting('usb_dir', mp.DEFAULT_USB_DIR)
            workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

            # DependencyChecker just for venv_python path — skip check_all()
            # to avoid pip subprocess / os.execv() in background threads.
            deps = mp.DependencyChecker(logger)

            quality_preset = preset or profile.quality_preset
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            orchestrator = mp.PipelineOrchestrator(
                logger, deps, config,
                quality_preset=quality_preset,
                workers=workers,
                output_profile=profile,
                display_handler=display,
                cancel_event=task.cancel_event,
            )

            if auto:
                logger.info("Auto mode: processing all playlists")
                aggregate = mp.AggregateStatistics()
                for i, pl in enumerate(config.playlists):
                    logger.info(f"\n{'=' * 60}")
                    logger.info(f"Processing {i+1}/{len(config.playlists)}: {pl.name}")
                    logger.info(f"{'=' * 60}")
                    orchestrator.run_full_pipeline(
                        playlist=str(i + 1), auto=True,
                        copy_to_usb=copy_to_usb, usb_dir=usb_dir,
                        dry_run=dry_run, verbose=verbose,
                        quality_preset=quality_preset,
                    )
                    aggregate.add_playlist_result(orchestrator.stats)
                return {'success': True, 'playlists': len(config.playlists)}
            else:
                pipeline_result = orchestrator.run_full_pipeline(
                    playlist=playlist_key, url=url, auto=False,
                    copy_to_usb=copy_to_usb, usb_dir=usb_dir,
                    dry_run=dry_run, verbose=verbose,
                    quality_preset=quality_preset,
                )
                return {'success': pipeline_result.success}

        task_id = task_manager.submit('pipeline', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: Convert ─────────────────────────────────────────────

    @app.route('/api/convert/run', methods=['POST'])
    def api_convert_run():
        data = request.get_json(force=True)
        input_dir = data.get('input_dir', '')
        output_dir = data.get('output_dir', '')
        force = data.get('force', False)
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)
        preset = data.get('preset', 'lossless')
        no_cover_art = data.get('no_cover_art', False)
        dir_structure = data.get('dir_structure')
        filename_format = data.get('filename_format')

        if not input_dir:
            return jsonify({'error': 'input_dir is required'}), 400

        safe_input = _safe_dir(project_root / input_dir)
        if not safe_input:
            return jsonify({'error': 'Invalid input directory'}), 400

        desc = f'Convert: {Path(input_dir).name}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            # Apply dir_structure/filename_format overrides
            if dir_structure or filename_format:
                from dataclasses import replace
                overrides = {}
                if dir_structure:
                    overrides['directory_structure'] = dir_structure
                if filename_format:
                    overrides['filename_format'] = filename_format
                profile = replace(profile, **overrides)
            workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

            out = output_dir if output_dir else mp.get_export_dir(profile.name)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            converter = mp.Converter(
                logger, quality_preset=preset, workers=workers,
                embed_cover_art=not no_cover_art, output_profile=profile,
                display_handler=display,
                cancel_event=task.cancel_event,
            )
            convert_result = converter.convert(safe_input, out, force=force,
                                               dry_run=dry_run, verbose=verbose)
            return {'success': convert_result.success}

        task_id = task_manager.submit('convert', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: Tags ────────────────────────────────────────────────

    @app.route('/api/tags/update', methods=['POST'])
    def api_tags_update():
        data = request.get_json(force=True)
        directory = data.get('directory', '')
        album = data.get('album')
        artist = data.get('artist')
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)

        if not directory:
            return jsonify({'error': 'directory is required'}), 400

        safe = _safe_dir(project_root / directory)
        if not safe:
            return jsonify({'error': 'Invalid directory'}), 400

        desc = f'Tag update: {Path(directory).name}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            tagger = mp.TaggerManager(logger, output_profile=profile,
                                      display_handler=display,
                                      cancel_event=task.cancel_event)
            tag_result = tagger.update_tags(safe, new_album=album, new_artist=artist,
                                            dry_run=dry_run, verbose=verbose)
            return {'success': tag_result.success}

        task_id = task_manager.submit('tag_update', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    @app.route('/api/tags/restore', methods=['POST'])
    def api_tags_restore():
        data = request.get_json(force=True)
        directory = data.get('directory', '')
        restore_all = data.get('all', False)
        restore_album = data.get('album', False)
        restore_title = data.get('title', False)
        restore_artist = data.get('artist', False)
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)

        if not directory:
            return jsonify({'error': 'directory is required'}), 400

        safe = _safe_dir(project_root / directory)
        if not safe:
            return jsonify({'error': 'Invalid directory'}), 400

        desc = f'Tag restore: {Path(directory).name}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            tagger = mp.TaggerManager(logger, output_profile=profile,
                                      display_handler=display,
                                      cancel_event=task.cancel_event)
            restore_result = tagger.restore_tags(
                safe,
                restore_album=restore_all or restore_album,
                restore_title=restore_all or restore_title,
                restore_artist=restore_all or restore_artist,
                dry_run=dry_run, verbose=verbose,
            )
            return {'success': restore_result.success}

        task_id = task_manager.submit('tag_restore', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    @app.route('/api/tags/reset', methods=['POST'])
    def api_tags_reset():
        data = request.get_json(force=True)
        input_dir = data.get('input_dir', '')
        output_dir = data.get('output_dir', '')
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)

        if not input_dir or not output_dir:
            return jsonify({'error': 'input_dir and output_dir are required'}), 400

        safe_in = _safe_dir(project_root / input_dir)
        safe_out = _safe_dir(project_root / output_dir)
        if not safe_in or not safe_out:
            return jsonify({'error': 'Invalid directory'}), 400

        desc = f'Tag reset: {Path(output_dir).name}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            tagger = mp.TaggerManager(logger, output_profile=profile,
                                      prompt_handler=WebPromptHandler(),
                                      display_handler=display,
                                      cancel_event=task.cancel_event)
            success = tagger.reset_tags_from_source(safe_in, safe_out,
                                                     dry_run=dry_run, verbose=verbose)
            return {'success': success}

        task_id = task_manager.submit('tag_reset', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: Cover Art ───────────────────────────────────────────

    @app.route('/api/cover-art/<action>', methods=['POST'])
    def api_cover_art(action):
        if action not in ('embed', 'extract', 'update', 'strip', 'resize'):
            return jsonify({'error': f'Unknown action: {action}'}), 400

        data = request.get_json(silent=True) or {}
        directory = data.get('directory', '')
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)

        if not directory:
            return jsonify({'error': 'directory is required'}), 400

        safe = _safe_dir(project_root / directory)
        if not safe:
            return jsonify({'error': 'Invalid directory'}), 400

        desc = f'Cover art {action}: {Path(directory).name}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            cam = mp.CoverArtManager(logger, output_profile=profile,
                                     display_handler=display,
                                     cancel_event=task.cancel_event)

            if action == 'embed':
                source = data.get('source')
                force = data.get('force', False)
                if source:
                    source = _safe_dir(project_root / source)
                r = cam.embed(safe, source_dir=source, force=force,
                              dry_run=dry_run, verbose=verbose)
                return {'success': r.success}
            elif action == 'extract':
                r = cam.extract(safe, dry_run=dry_run, verbose=verbose)
                return {'success': r.success}
            elif action == 'update':
                image = data.get('image', '')
                if not image:
                    return {'success': False, 'error': 'image path required'}
                safe_img = _safe_dir(project_root / image)
                if not safe_img:
                    return {'success': False, 'error': 'invalid image path'}
                r = cam.update(safe, safe_img,
                               dry_run=dry_run, verbose=verbose)
                return {'success': r.success}
            elif action == 'strip':
                r = cam.strip(safe, dry_run=dry_run, verbose=verbose)
                return {'success': r.success}
            elif action == 'resize':
                max_size = data.get('max_size', 100)
                r = cam.resize(safe, max_size,
                               dry_run=dry_run, verbose=verbose)
                return {'success': r.success}

        task_id = task_manager.submit(f'cover_art_{action}', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: File Serving (for iOS companion app) ─────────────────

    @app.route('/api/files/<playlist_key>')
    def api_files_list(playlist_key):
        """List MP3 files in a playlist with ID3 metadata."""
        config = _get_config()
        profile = _get_output_profile(config)
        playlist_dir = project_root / mp.get_export_dir(profile.name, playlist_key)
        safe = _safe_dir(playlist_dir)
        if not safe or not Path(safe).is_dir():
            return jsonify({'error': f'Playlist directory not found: {playlist_key}'}), 404

        from mutagen.id3 import ID3
        from mutagen.mp3 import MP3

        files = []
        for f in sorted(Path(safe).glob('*.mp3')):
            entry = {
                'filename': f.name,
                'size': f.stat().st_size,
            }
            try:
                audio = MP3(str(f))
                entry['duration'] = round(audio.info.length, 1) if audio.info else 0
                tags = ID3(str(f))
                entry['title'] = str(tags.get('TIT2', ''))
                entry['artist'] = str(tags.get('TPE1', ''))
                entry['album'] = str(tags.get('TALB', ''))
                entry['has_cover_art'] = any(
                    key.startswith('APIC') for key in tags)
                entry['has_protection_tags'] = any(
                    hasattr(frame, 'desc') and frame.desc.startswith('Original')
                    for frame in tags.values()
                    if hasattr(frame, 'desc'))
            except Exception:
                entry.setdefault('title', f.stem)
                entry.setdefault('duration', 0)
                entry.setdefault('has_cover_art', False)
                entry.setdefault('has_protection_tags', False)
            files.append(entry)

        return jsonify({
            'playlist': playlist_key,
            'profile': profile.name,
            'file_count': len(files),
            'files': files,
        })

    @app.route('/api/files/<playlist_key>/<filename>')
    def api_files_download(playlist_key, filename):
        """Download a single MP3 file."""
        config = _get_config()
        profile = _get_output_profile(config)
        playlist_dir = project_root / mp.get_export_dir(profile.name, playlist_key)
        safe = _safe_dir(playlist_dir)
        if not safe:
            return jsonify({'error': 'Invalid directory'}), 400

        file_path = Path(safe) / filename
        if not file_path.exists() or file_path.suffix.lower() != '.mp3':
            return jsonify({'error': 'File not found'}), 404

        # Validate the file is within the safe directory
        if not str(file_path.resolve()).startswith(str(Path(safe).resolve())):
            return jsonify({'error': 'Invalid path'}), 400

        return send_from_directory(safe, filename, mimetype='audio/mpeg')

    @app.route('/api/files/<playlist_key>/<filename>/artwork')
    def api_files_artwork(playlist_key, filename):
        """Extract and serve cover art from an MP3 file."""
        config = _get_config()
        profile = _get_output_profile(config)
        playlist_dir = project_root / mp.get_export_dir(profile.name, playlist_key)
        safe = _safe_dir(playlist_dir)
        if not safe:
            return jsonify({'error': 'Invalid directory'}), 400

        file_path = Path(safe) / filename
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404

        try:
            from mutagen.id3 import ID3
            tags = ID3(str(file_path))
            for key, frame in tags.items():
                if key.startswith('APIC'):
                    mime = getattr(frame, 'mime', 'image/jpeg')
                    return Response(frame.data, mimetype=mime)
            return jsonify({'error': 'No cover art found'}), 404
        except Exception as e:
            return jsonify({'error': f'Could not read artwork: {e}'}), 500

    @app.route('/api/files/<playlist_key>/download-all')
    def api_files_download_all(playlist_key):
        """Stream a ZIP archive of all MP3s in a playlist."""
        import io
        import zipfile

        config = _get_config()
        profile = _get_output_profile(config)
        playlist_dir = project_root / mp.get_export_dir(profile.name, playlist_key)
        safe = _safe_dir(playlist_dir)
        if not safe or not Path(safe).is_dir():
            return jsonify({'error': f'Playlist directory not found: {playlist_key}'}), 404

        mp3_files = sorted(Path(safe).glob('*.mp3'))
        if not mp3_files:
            return jsonify({'error': 'No MP3 files found'}), 404

        def generate_zip():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
                for f in mp3_files:
                    zf.write(f, f.name)
            buf.seek(0)
            while True:
                chunk = buf.read(65536)
                if not chunk:
                    break
                yield chunk

        zip_name = f"{playlist_key}.zip"
        return Response(
            generate_zip(),
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{zip_name}"',
            }
        )

    # ── API: USB ─────────────────────────────────────────────────

    @app.route('/api/usb/drives')
    def api_usb_drives():
        if not app.config.get('NO_AUTH'):
            return jsonify({'error': 'USB sync is not available in server mode'}), 403
        usb_mgr = mp.USBManager(mp.Logger(verbose=False))
        drives = usb_mgr.find_usb_drives()
        return jsonify(drives)

    @app.route('/api/usb/sync', methods=['POST'])
    def api_usb_sync():
        if not app.config.get('NO_AUTH'):
            return jsonify({'error': 'USB sync is not available in server mode'}), 403
        data = request.get_json(force=True)
        source_dir = data.get('source_dir', '')
        volume = data.get('volume', '')
        usb_dir = data.get('usb_dir', mp.DEFAULT_USB_DIR)
        dry_run = data.get('dry_run', False)
        verbose = data.get('verbose', False)

        if not source_dir or not volume:
            return jsonify({'error': 'source_dir and volume are required'}), 400

        desc = f'USB sync: {Path(source_dir).name} → {volume}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            display = _make_display_handler(task_id)
            task = task_manager.get(task_id)
            usb_mgr = mp.USBManager(logger, display_handler=display,
                                    cancel_event=task.cancel_event)
            usb_result = usb_mgr.sync_to_usb(
                source_dir, usb_dir=usb_dir, dry_run=dry_run, volume=volume,
            )
            return {
                'success': usb_result.success,
                'files_found': usb_result.files_found,
                'files_copied': usb_result.files_copied,
                'files_skipped': usb_result.files_skipped,
                'files_failed': usb_result.files_failed,
            }

        task_id = task_manager.submit('usb_sync', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: Tasks ───────────────────────────────────────────────

    @app.route('/api/tasks')
    def api_tasks_list():
        return jsonify(task_manager.list_all())

    @app.route('/api/tasks/<task_id>')
    def api_tasks_get(task_id):
        task = task_manager.get(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        return jsonify(task.to_dict())

    @app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
    def api_tasks_cancel(task_id):
        if task_manager.cancel(task_id):
            return jsonify({'ok': True})
        return jsonify({'error': 'Task not found or not running'}), 404

    # ── API: SSE Stream ──────────────────────────────────────────

    @app.route('/api/stream/<task_id>')
    def api_stream(task_id):
        task = task_manager.get(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        def generate():
            while True:
                try:
                    msg = task.log_queue.get(timeout=30)
                    if msg is None:
                        # Task finished
                        yield f"data: {json.dumps({'type': 'done', 'status': task.status, 'result': task.result, 'error': task.error})}\n\n"
                        return
                    if 'type' in msg:
                        # Pre-typed messages (e.g. progress events) — pass through
                        yield f"data: {json.dumps(msg)}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'log', 'level': msg['level'], 'message': msg['message']})}\n\n"
                except queue.Empty:
                    # Heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    if task.status not in ('pending', 'running'):
                        yield f"data: {json.dumps({'type': 'done', 'status': task.status})}\n\n"
                        return

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
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


def _print_pairing_qr(host, port, api_key):
    """Print a QR code to the terminal for iOS app pairing.

    The QR code encodes a JSON payload with the server address and API key:
    {"host": "...", "port": 5555, "key": "..."}
    """
    try:
        import io

        import segno
        payload = json.dumps({"host": host, "port": port, "key": api_key})
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
                  show_api_key=False, enable_bonjour=False):
    """Start the Flask development server.

    Args:
        host: Host to bind.
        port: Port to bind.
        no_auth: If True, skip API key authentication on /api/* routes.
        show_api_key: If True, print the API key at startup.
        enable_bonjour: If True, advertise via mDNS/Bonjour.
    """
    _kill_port_process(port)

    # Determine local network IP for iOS connection info
    local_ip = BonjourAdvertiser._get_local_ip() or host

    if not no_auth:
        config = mp.ConfigManager(logger=mp.Logger(verbose=False))
        api_key = config.ensure_api_key()

        # Always show full API key and connection details for server mode
        print(f"\n  ── Server Mode ({'auth enabled' if not no_auth else 'no auth'}) ──")
        print(f"  Server:    http://{host}:{port}")
        if host == '0.0.0.0':
            print(f"  Local URL: http://{local_ip}:{port}")
        print(f"  API Key:   {api_key}")
        print("  Auth:      Bearer token required on /api/* routes")
        print()
        print("  ── iOS Companion App Connection ──")
        print("  1. Open the Music Porter iOS app")
        print(f"  2. Enter server address: {local_ip}:{port}")
        print(f"  3. Enter API key: {api_key}")
        print("  4. Or scan the QR code below:")
        print()
        _print_pairing_qr(local_ip, port, api_key)
    else:
        print("\n  ── Web Dashboard Mode (no auth) ──")
        print(f"  Server:  http://{host}:{port}")

    print("\n  Press Ctrl+C to stop\n")

    app = create_app(no_auth=no_auth)

    # Bonjour/mDNS advertisement
    bonjour = None
    if enable_bonjour and host != '127.0.0.1':
        bonjour = BonjourAdvertiser(port)
        bonjour.start()

    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    finally:
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

        hostname = socket.gethostname()
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
