"""
web_ui.py - Flask web dashboard for music-porter

Provides a browser-based UI for all music-porter operations with
live log streaming via Server-Sent Events (SSE).
"""

import importlib.machinery
import importlib.util
import json
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

# ── Import music-porter module ──────────────────────────────────────────────
# music-porter has no .py extension, so we need to tell importlib it's Python.
_mp_path = Path(__file__).resolve().parent / 'music-porter'
_loader = importlib.machinery.SourceFileLoader('music_porter', str(_mp_path))
_spec = importlib.util.spec_from_loader('music_porter', _loader, origin=str(_mp_path))
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)

# Initialize third-party imports once at load time.
# The web server runs inside the venv so all packages are already available.
# This avoids DependencyChecker's pip/os.execv() in background threads.
mp._init_third_party()


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
# Flask Application Factory
# ══════════════════════════════════════════════════════════════════

def create_app(project_root=None):
    """Create and configure the Flask application."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent

    project_root = Path(project_root)
    template_dir = project_root / 'templates'

    app = Flask(__name__, template_folder=str(template_dir))
    app.config['PROJECT_ROOT'] = str(project_root)

    task_manager = TaskManager()

    # ── Helper to create a WebLogger for a task ──────────────────
    def _make_logger(task_id, verbose=False):
        task = task_manager.get(task_id)
        return WebLogger(task.log_queue, task.cancel_event, verbose=verbose)

    def _get_config():
        logger = mp.Logger(verbose=False)
        return mp.ConfigManager(logger=logger)

    def _get_output_profile(config):
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

        playlists_json = []
        for p in mgr.stats.playlists:
            playlists_json.append({
                'name': p.name,
                'file_count': p.file_count,
                'size_bytes': p.total_size_bytes,
                'avg_size_mb': round(p.avg_file_size_mb, 1),
                'last_modified': p.last_modified.isoformat() if p.last_modified else None,
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
                   'artwork_size': p.artwork_size, 'id3_version': p.id3_version}
            for name, p in mp.OUTPUT_PROFILES.items()
        }
        return jsonify({
            'settings': config.settings,
            'profiles': profiles,
            'quality_presets': list(mp.QUALITY_PRESETS.keys()),
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
        dirs = []
        if export_dir.exists():
            for d in sorted(export_dir.iterdir()):
                if d.is_dir() and not d.name.startswith('.'):
                    file_count = len(list(d.glob('*.mp3')))
                    dirs.append({'name': d.name, 'files': file_count})
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

        if not auto and not playlist_key and not url:
            return jsonify({'error': 'Specify playlist, url, or auto'}), 400

        desc = 'Pipeline: all playlists' if auto else f'Pipeline: {playlist_key or url}'

        def _run(task_id):
            logger = _make_logger(task_id, verbose=verbose)
            config = mp.ConfigManager(logger=logger)
            profile = _get_output_profile(config)
            usb_dir = config.get_setting('usb_dir', mp.DEFAULT_USB_DIR)
            workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

            # DependencyChecker just for venv_python path — skip check_all()
            # to avoid pip subprocess / os.execv() in background threads.
            deps = mp.DependencyChecker(logger)

            quality_preset = preset or profile.quality_preset
            orchestrator = mp.PipelineOrchestrator(
                logger, deps, config,
                quality_preset=quality_preset,
                workers=workers,
                output_profile=profile,
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
                success = orchestrator.run_full_pipeline(
                    playlist=playlist_key, url=url, auto=False,
                    copy_to_usb=copy_to_usb, usb_dir=usb_dir,
                    dry_run=dry_run, verbose=verbose,
                    quality_preset=quality_preset,
                )
                return {'success': success}

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
            workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

            out = output_dir if output_dir else mp.get_export_dir(profile.name)
            converter = mp.Converter(
                logger, quality_preset=preset, workers=workers,
                embed_cover_art=not no_cover_art, output_profile=profile,
            )
            success = converter.convert(safe_input, out, force=force,
                                        dry_run=dry_run, verbose=verbose)
            return {'success': success}

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
            tagger = mp.TaggerManager(logger, output_profile=profile)
            success = tagger.update_tags(safe, new_album=album, new_artist=artist,
                                         dry_run=dry_run, verbose=verbose)
            return {'success': success}

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
            tagger = mp.TaggerManager(logger, output_profile=profile)
            success = tagger.restore_tags(
                safe,
                restore_album=restore_all or restore_album,
                restore_title=restore_all or restore_title,
                restore_artist=restore_all or restore_artist,
                dry_run=dry_run, verbose=verbose,
            )
            return {'success': success}

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
            tagger = mp.TaggerManager(logger, output_profile=profile)
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
            cam = mp.CoverArtManager(logger)

            if action == 'embed':
                source = data.get('source')
                force = data.get('force', False)
                if source:
                    source = _safe_dir(project_root / source)
                return {'success': cam.embed(safe, source_dir=source, force=force,
                                             dry_run=dry_run, verbose=verbose)}
            elif action == 'extract':
                return {'success': cam.extract(safe, dry_run=dry_run, verbose=verbose)}
            elif action == 'update':
                image = data.get('image', '')
                if not image:
                    return {'success': False, 'error': 'image path required'}
                safe_img = _safe_dir(project_root / image)
                if not safe_img:
                    return {'success': False, 'error': 'invalid image path'}
                return {'success': cam.update(safe, safe_img,
                                              dry_run=dry_run, verbose=verbose)}
            elif action == 'strip':
                return {'success': cam.strip(safe, dry_run=dry_run, verbose=verbose)}
            elif action == 'resize':
                max_size = data.get('max_size', 100)
                return {'success': cam.resize(safe, max_size,
                                              dry_run=dry_run, verbose=verbose)}

        task_id = task_manager.submit(f'cover_art_{action}', desc, _run)
        if task_id is None:
            return jsonify({'error': 'Another operation is already running'}), 409
        return jsonify({'task_id': task_id})

    # ── API: USB ─────────────────────────────────────────────────

    @app.route('/api/usb/drives')
    def api_usb_drives():
        usb_mgr = mp.USBManager(mp.Logger(verbose=False))
        drives = usb_mgr.find_usb_drives()
        return jsonify(drives)

    @app.route('/api/usb/sync', methods=['POST'])
    def api_usb_sync():
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
            usb_mgr = mp.USBManager(logger)
            success, stats = usb_mgr.sync_to_usb(
                source_dir, usb_dir=usb_dir, dry_run=dry_run, volume=volume,
            )
            return {
                'success': success,
                'files_found': stats.files_found,
                'files_copied': stats.files_copied,
                'files_skipped': stats.files_skipped,
                'files_failed': stats.files_failed,
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

def start_server(host='127.0.0.1', port=5555):
    """Start the Flask development server."""
    print(f"\n  Web Dashboard: http://{host}:{port}")
    print(f"  Press Ctrl+C to stop\n")
    app = create_app()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    start_server()
