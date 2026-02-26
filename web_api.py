"""
web_api.py - Flask Blueprint with all REST API routes for music-porter

Extracted from web_ui.py to separate UI (page routes, templates) from
API endpoints (REST, background tasks, SSE streaming).

All routes are registered on ``api_bp`` and access shared state through
``AppContext`` stored in ``current_app.config['CTX']``.
"""

import json
import queue
import time
from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)

import porter_core as mp
from web_ui import WebPromptHandler, _get_freshness_level

api_bp = Blueprint('api', __name__)


def _ctx():
    """Convenience accessor for the shared AppContext."""
    return current_app.config['CTX']


# ══════════════════════════════════════════════════════════════════
# API: Auth & Server Info
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/auth/validate', methods=['POST'])
def api_auth_validate():
    """Validate API key and return server identity."""
    ctx = _ctx()
    ctx.audit_logger.log('auth_validate', 'API key validated', 'completed',
                         params=ctx.client_info(), source=ctx.detect_source())
    return jsonify({
        'valid': True,
        'version': mp.VERSION,
        'server_name': ctx.get_server_name(),
        'api_version': 1,
    })


@api_bp.route('/api/server-info')
def api_server_info():
    """Return server metadata for client discovery."""
    ctx = _ctx()
    config = ctx.get_config()
    mp.load_output_profiles(config)
    return jsonify({
        'name': ctx.get_server_name(),
        'version': mp.VERSION,
        'platform': mp.get_os_display_name(),
        'profiles': list(mp.OUTPUT_PROFILES.keys()),
        'api_version': 1,
    })


# ══════════════════════════════════════════════════════════════════
# API: Dashboard Status
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/status')
def api_status():
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)

    # Cookie status
    cookie_mgr = mp.CookieManager(mp.DEFAULT_COOKIES, mp.Logger(verbose=False))
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

    scheduler_data = None
    if ctx.scheduler:
        scheduler_data = ctx.scheduler.status()

    return jsonify({
        'version': mp.VERSION,
        'cookies': cookie_data,
        'library': {
            'playlists': playlist_count,
            'files': total_files,
            'size_mb': round(total_size / (1024 * 1024), 1) if total_size else 0,
        },
        'profile': profile.name,
        'busy': ctx.task_manager.is_busy(),
        'scheduler': scheduler_data,
    })


# ══════════════════════════════════════════════════════════════════
# API: Cookie Management
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/cookies/browsers')
def api_cookies_browsers():
    cookie_mgr = mp.CookieManager(mp.DEFAULT_COOKIES, mp.Logger(verbose=False))
    default_browser = cookie_mgr._detect_default_browser()
    installed = cookie_mgr._detect_installed_browsers()
    return jsonify({
        'default': default_browser,
        'installed': installed,
    })


@api_bp.route('/api/cookies/refresh', methods=['POST'])
def api_cookies_refresh():
    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    browser = data.get('browser', 'auto')
    verbose = data.get('verbose', False)

    desc = f'Cookie refresh ({browser})'

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)

        # Log current status first
        cookie_mgr = mp.CookieManager(mp.DEFAULT_COOKIES, logger)
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

    task_id = ctx.task_manager.submit('cookie_refresh', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: Library Summary
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/summary')
def api_summary():
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
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


# ══════════════════════════════════════════════════════════════════
# API: Library Stats (music/ directory)
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/library-stats')
def api_library_stats():
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)

    quiet_logger = mp.Logger(verbose=False)
    mgr = mp.SummaryManager(logger=quiet_logger)
    stats = mgr.scan_music_library(
        music_dir=mp.DEFAULT_MUSIC_DIR,
        export_profile=profile.name,
        output_profile=profile,
    )

    if stats is None:
        return jsonify({
            'total_playlists': 0, 'total_files': 0,
            'total_size_bytes': 0, 'total_exported': 0,
            'total_unconverted': 0, 'scan_duration': 0,
            'playlists': [],
        })

    return jsonify({
        'total_playlists': stats.total_playlists,
        'total_files': stats.total_files,
        'total_size_bytes': stats.total_size_bytes,
        'total_exported': stats.total_exported,
        'total_unconverted': stats.total_unconverted,
        'scan_duration': round(stats.scan_duration, 2),
        'playlists': stats.playlists,
    })


@api_bp.route('/api/library-stats/<playlist_key>/unconverted')
def api_library_stats_unconverted(playlist_key):
    """Return file-level unconverted details for one playlist."""
    if '/' in playlist_key or '..' in playlist_key:
        return jsonify({'error': 'Invalid playlist key'}), 400

    music_path = Path(mp.DEFAULT_MUSIC_DIR) / playlist_key
    if not music_path.exists():
        return jsonify({'error': 'Playlist not found in music/'}), 404

    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    quiet_logger = mp.Logger(verbose=False)
    mgr = mp.SummaryManager(logger=quiet_logger)
    files = mgr.get_unconverted_files(
        playlist_key, mp.DEFAULT_MUSIC_DIR, profile.name, profile,
    )

    return jsonify({
        'playlist': playlist_key,
        'unconverted_count': len(files),
        'files': files,
    })


@api_bp.route('/api/list/unconverted')
def api_list_unconverted():
    """List unconverted M4A files across playlists."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    quiet_logger = mp.Logger(verbose=False)
    mgr = mp.SummaryManager(logger=quiet_logger)

    playlist_filter = request.args.get('playlist')
    if playlist_filter and ('/' in playlist_filter or '..' in playlist_filter):
        return jsonify({'error': 'Invalid playlist name'}), 400

    result = mgr.list_unconverted(
        music_dir=mp.DEFAULT_MUSIC_DIR,
        export_profile=profile.name,
        output_profile=profile,
        playlist_filter=playlist_filter,
    )
    return jsonify(result.to_dict())


@api_bp.route('/api/list/diff')
def api_list_diff():
    """List unconverted and orphaned files across playlists."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    quiet_logger = mp.Logger(verbose=False)
    mgr = mp.SummaryManager(logger=quiet_logger)

    playlist_filter = request.args.get('playlist')
    if playlist_filter and ('/' in playlist_filter or '..' in playlist_filter):
        return jsonify({'error': 'Invalid playlist name'}), 400

    result = mgr.list_diff(
        music_dir=mp.DEFAULT_MUSIC_DIR,
        export_profile=profile.name,
        output_profile=profile,
        playlist_filter=playlist_filter,
    )
    return jsonify(result.to_dict())


@api_bp.route('/api/convert/batch', methods=['POST'])
def api_convert_batch():
    """Convert multiple playlists in a single background task."""
    ctx = _ctx()
    data = request.get_json(force=True)
    playlists = data.get('playlists', [])
    force = data.get('force', False)
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)
    preset = data.get('preset', 'lossless')
    no_cover_art = data.get('no_cover_art', False)

    if not playlists:
        return jsonify({'error': 'playlists list is required'}), 400

    # Validate all playlist directories
    for key in playlists:
        if '/' in key or '..' in key:
            return jsonify({'error': f'Invalid playlist key: {key}'}), 400
        input_path = ctx.project_root / mp.DEFAULT_MUSIC_DIR / key
        if not input_path.exists():
            return jsonify({'error': f'Playlist not found: {key}'}), 404

    names = ', '.join(playlists[:3])
    if len(playlists) > 3:
        names += f' (+{len(playlists) - 3} more)'
    desc = f'Batch convert: {names}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
        workers = config.get_setting('workers', mp.DEFAULT_WORKERS)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)

        total_success = 0
        total_failed = 0

        for i, key in enumerate(playlists):
            if task.cancel_event.is_set():
                break
            logger.info(f"[{i+1}/{len(playlists)}] Converting {key}...")
            input_dir = str(ctx.project_root / mp.DEFAULT_MUSIC_DIR / key)
            out = mp.get_export_dir(profile.name, key)
            converter = mp.Converter(
                logger, quality_preset=preset, workers=workers,
                embed_cover_art=not no_cover_art, output_profile=profile,
                display_handler=display,
                cancel_event=task.cancel_event,
                audit_logger=ctx.audit_logger,
                audit_source=source,
            )
            result = converter.convert(input_dir, out, force=force,
                                       dry_run=dry_run, verbose=verbose)
            if result.success:
                total_success += 1
            else:
                total_failed += 1

        return {
            'success': total_failed == 0,
            'playlists_converted': total_success,
            'playlists_failed': total_failed,
        }

    task_id = ctx.task_manager.submit('convert_batch', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: Playlists CRUD
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/playlists', methods=['GET'])
def api_playlists_list():
    ctx = _ctx()
    config = ctx.get_config()
    return jsonify([
        {'key': p.key, 'url': p.url, 'name': p.name}
        for p in config.playlists
    ])


@api_bp.route('/api/playlists', methods=['POST'])
def api_playlists_add():
    ctx = _ctx()
    data = request.get_json(force=True)
    key = data.get('key', '').strip()
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()

    if not key or not url or not name:
        return jsonify({'error': 'key, url, and name are required'}), 400

    config = ctx.get_config()
    if config.add_playlist(key, url, name):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist key '{key}' already exists"}), 409


@api_bp.route('/api/playlists/<key>', methods=['PUT'])
def api_playlists_update(key):
    ctx = _ctx()
    data = request.get_json(force=True)
    config = ctx.get_config()
    if config.update_playlist(key, url=data.get('url'), name=data.get('name')):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist '{key}' not found"}), 404


@api_bp.route('/api/playlists/<key>', methods=['DELETE'])
def api_playlists_delete(key):
    ctx = _ctx()
    config = ctx.get_config()
    if config.remove_playlist(key):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist '{key}' not found"}), 404


@api_bp.route('/api/playlists/<key>/delete-data', methods=['POST'])
def api_playlist_delete_data(key):
    ctx = _ctx()
    data = request.get_json(force=True) if request.data else {}
    delete_source = data.get('delete_source', True)
    delete_export = data.get('delete_export', True)
    remove_config = data.get('remove_config', False)
    dry_run = data.get('dry_run', False)

    config = ctx.get_config()
    profile = ctx.get_output_profile(config)

    # Validate playlist exists in config or has data on disk
    source_dir = ctx.project_root / mp.DEFAULT_MUSIC_DIR / key
    export_dir = ctx.project_root / mp.get_export_dir(profile.name, key)
    playlist_exists = config.get_playlist_by_key(key) is not None
    data_exists = source_dir.exists() or export_dir.exists()

    if not playlist_exists and not data_exists:
        return jsonify({'error': f"Playlist '{key}' not found and has no data on disk"}), 404

    logger = mp.Logger(verbose=False)
    prompt = WebPromptHandler()
    data_manager = mp.DataManager(logger, config, prompt_handler=prompt,
                                  output_profile=profile,
                                  audit_logger=ctx.audit_logger,
                                  audit_source=ctx.detect_source())
    result = data_manager.delete_playlist_data(
        key,
        delete_source=delete_source,
        delete_export=delete_export,
        remove_config=remove_config,
        dry_run=dry_run,
    )
    return jsonify(result.to_dict())


# ══════════════════════════════════════════════════════════════════
# API: Settings
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/settings', methods=['GET'])
def api_settings_get():
    ctx = _ctx()
    config = ctx.get_config()
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


@api_bp.route('/api/settings', methods=['POST'])
def api_settings_update():
    ctx = _ctx()
    data = request.get_json(force=True)
    config = ctx.get_config()
    for key, value in data.items():
        config.update_setting(key, value)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════════
# API: Config
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/config/verify')
def api_config_verify():
    """Validate config.yaml and return structured report."""
    results = mp.validate_config(mp.DEFAULT_CONFIG_FILE)
    errors = sum(1 for level, _ in results if level == "error")
    warnings = sum(1 for level, _ in results if level == "warning")
    return jsonify({
        'results': [{'level': level, 'message': msg} for level, msg in results],
        'errors': errors,
        'warnings': warnings,
        'valid': errors == 0,
    })


@api_bp.route('/api/config/reset', methods=['POST'])
def api_config_reset():
    """Back up config.yaml and recreate with defaults."""
    import shutil

    ctx = _ctx()
    config_path = ctx.project_root / mp.DEFAULT_CONFIG_FILE
    backup_path = None

    if config_path.exists():
        backup_path = ctx.project_root / f"{mp.DEFAULT_CONFIG_FILE}.backup"
        shutil.copy2(config_path, backup_path)
        config_path.unlink()

    # Recreate with defaults
    logger = mp.Logger(verbose=False)
    mp.ConfigManager(logger=logger)

    return jsonify({
        'ok': True,
        'backup': str(backup_path) if backup_path else None,
    })


# ══════════════════════════════════════════════════════════════════
# API: Scheduler
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/scheduler/status')
def api_scheduler_status():
    """Return current scheduler status and configuration."""
    ctx = _ctx()
    if ctx.scheduler is None:
        return jsonify({'error': 'Scheduler not available'}), 404
    return jsonify(ctx.scheduler.status())


@api_bp.route('/api/scheduler/config', methods=['POST'])
def api_scheduler_config():
    """Update scheduler configuration.

    Body: {enabled, interval_hours, playlists, preset, retry_minutes, max_retries}
    All fields optional — only provided fields are updated.
    """
    ctx = _ctx()
    if ctx.scheduler is None:
        return jsonify({'error': 'Scheduler not available'}), 404

    data = request.get_json(force=True)

    interval = data.get('interval_hours')
    if interval is not None:
        if not isinstance(interval, (int, float)) or interval < 0.5:
            return jsonify({'error': 'interval_hours must be >= 0.5'}), 400

    playlists = data.get('playlists')
    if playlists is not None:
        if not isinstance(playlists, list):
            return jsonify({'error': 'playlists must be a list of keys'}), 400

    preset = data.get('preset')
    if preset is not None and preset != '':
        if preset not in mp.QUALITY_PRESETS:
            return jsonify({'error': f'Invalid preset: {preset}'}), 400

    # Merge with current config
    current = ctx.scheduler.status()
    new_settings = {
        'enabled': data.get('enabled', current['enabled']),
        'interval_hours': data.get('interval_hours', current['interval_hours']),
        'playlists': data.get('playlists', current['playlists']),
        'preset': data.get('preset', current['preset']) or None,
        'retry_minutes': data.get('retry_minutes', current['retry_minutes']),
        'max_retries': data.get('max_retries', current['max_retries']),
    }

    ctx.scheduler.reconfigure(new_settings)

    ctx.audit_logger.log(
        'scheduler_config',
        f"Scheduler {'enabled' if new_settings['enabled'] else 'disabled'}",
        'completed',
        params=new_settings,
        source=ctx.detect_source(),
    )

    return jsonify({'ok': True, 'status': ctx.scheduler.status()})


@api_bp.route('/api/scheduler/run-now', methods=['POST'])
def api_scheduler_run_now():
    """Trigger an immediate scheduled pipeline execution."""
    ctx = _ctx()
    if ctx.scheduler is None:
        return jsonify({'error': 'Scheduler not available'}), 404

    status = ctx.scheduler.status()
    if not status['enabled']:
        return jsonify({'error': 'Scheduler is not enabled'}), 400

    success = ctx.scheduler.run_now()
    if not success:
        return jsonify({'error': 'Another operation is already running'}), 409

    return jsonify({'ok': True, 'status': ctx.scheduler.status()})


# ══════════════════════════════════════════════════════════════════
# API: Directory Listings
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/directories/music')
def api_dirs_music():
    ctx = _ctx()
    music_dir = ctx.project_root / mp.DEFAULT_MUSIC_DIR
    dirs = []
    if music_dir.exists():
        for d in sorted(music_dir.iterdir()):
            if d.is_dir() and not d.name.startswith('.'):
                dirs.append(d.name)
    return jsonify(dirs)


@api_bp.route('/api/directories/export')
def api_dirs_export():
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    export_dir = ctx.project_root / mp.get_export_dir(profile.name)
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


# ══════════════════════════════════════════════════════════════════
# Pipeline result serialization helpers
# ══════════════════════════════════════════════════════════════════

def _serialize_pipeline_result(r):
    """Serialize PipelineResult (dataclass) for frontend consumption."""
    d = r.to_dict()
    d['type'] = 'single'
    return d


def _serialize_playlist_result(pr):
    """Serialize a PlaylistResult (plain class) to dict."""
    d = {
        'key': pr.key,
        'name': pr.name,
        'success': pr.success,
        'failed_stage': pr.failed_stage,
        'sync_success': pr.sync_success,
        'duration': pr.duration,
        'download_stats': None,
        'conversion_stats': None,
        'tagging_stats': None,
    }
    if pr.download_stats:
        d['download_stats'] = {
            'playlist_total': pr.download_stats.playlist_total,
            'downloaded': pr.download_stats.downloaded,
            'skipped': pr.download_stats.skipped,
            'failed': pr.download_stats.failed,
        }
    if pr.conversion_stats:
        d['conversion_stats'] = {
            'total_found': pr.conversion_stats.total_found,
            'converted': pr.conversion_stats.converted,
            'overwritten': pr.conversion_stats.overwritten,
            'skipped': pr.conversion_stats.skipped,
            'errors': pr.conversion_stats.errors,
            'mp3_total': pr.conversion_stats.mp3_total,
        }
    if pr.tagging_stats:
        d['tagging_stats'] = {
            'title_updated': pr.tagging_stats.title_updated,
            'album_updated': pr.tagging_stats.album_updated,
            'artist_updated': pr.tagging_stats.artist_updated,
            'title_stored': pr.tagging_stats.title_stored,
            'artist_stored': pr.tagging_stats.artist_stored,
            'album_stored': pr.tagging_stats.album_stored,
        }
    return d


def _serialize_aggregate_result(r):
    """Serialize AggregateResult for frontend consumption."""
    return {
        'type': 'aggregate',
        'success': r.success,
        'duration': r.duration,
        'total_playlists': r.total_playlists,
        'successful_playlists': r.successful_playlists,
        'failed_playlists': r.failed_playlists,
        'cumulative': r.cumulative_stats,
        'sync_destination': r.sync_destination,
        'playlists': [_serialize_playlist_result(pr) for pr in r.playlist_results],
    }


# ══════════════════════════════════════════════════════════════════
# API: Pipeline
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/pipeline/run', methods=['POST'])
def api_pipeline_run():
    ctx = _ctx()
    data = request.get_json(force=True)
    playlist_key = data.get('playlist')
    url = data.get('url')
    auto = data.get('auto', False)
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)
    preset = data.get('preset')
    sync_dest_name = data.get('sync_destination')
    dir_structure = data.get('dir_structure')
    filename_format = data.get('filename_format')

    if not auto and not playlist_key and not url:
        return jsonify({'error': 'Specify playlist, url, or auto'}), 400

    desc = 'Pipeline: all playlists' if auto else f'Pipeline: {playlist_key or url}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
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

        # DependencyChecker just for venv_python path — skip check_all()
        # to avoid pip subprocess / os.execv() in background threads.
        deps = mp.DependencyChecker(logger)

        quality_preset = preset or profile.quality_preset
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        orchestrator = mp.PipelineOrchestrator(
            logger, deps, config,
            quality_preset=quality_preset,
            workers=workers,
            output_profile=profile,
            display_handler=display,
            cancel_event=task.cancel_event,
            audit_logger=ctx.audit_logger,
            audit_source=source,
            sync_tracker=ctx.sync_tracker,
        )

        # Resolve sync destination by name
        sync_destination = None
        if sync_dest_name:
            saved = config.get_destination(sync_dest_name)
            if saved:
                sync_destination = saved

        if auto:
            logger.info("Auto mode: processing all playlists")
            aggregate = mp.AggregateStatistics()
            for i, pl in enumerate(config.playlists):
                logger.info(f"\n{'=' * 60}")
                logger.info(f"Processing {i+1}/{len(config.playlists)}: {pl.name}")
                logger.info(f"{'=' * 60}")
                orchestrator.run_full_pipeline(
                    playlist=str(i + 1), auto=True,
                    sync_destination=sync_destination,
                    dry_run=dry_run, verbose=verbose,
                    quality_preset=quality_preset,
                )
                aggregate.add_playlist_result(orchestrator.stats)
            aggregate.end_time = time.time()
            agg_result = aggregate.to_result()
            result_dict = _serialize_aggregate_result(agg_result)
            result_dict['success'] = agg_result.success
            return result_dict
        else:
            pipeline_result = orchestrator.run_full_pipeline(
                playlist=playlist_key, url=url, auto=True,
                sync_destination=sync_destination,
                dry_run=dry_run, verbose=verbose,
                quality_preset=quality_preset,
            )
            result_dict = _serialize_pipeline_result(pipeline_result)
            result_dict['success'] = pipeline_result.success
            return result_dict

    task_id = ctx.task_manager.submit('pipeline', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: Convert
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/convert/run', methods=['POST'])
def api_convert_run():
    ctx = _ctx()
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

    safe_input = ctx.safe_dir(ctx.project_root / input_dir)
    if not safe_input:
        return jsonify({'error': 'Invalid input directory'}), 400

    desc = f'Convert: {Path(input_dir).name}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
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
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        converter = mp.Converter(
            logger, quality_preset=preset, workers=workers,
            embed_cover_art=not no_cover_art, output_profile=profile,
            display_handler=display,
            cancel_event=task.cancel_event,
            audit_logger=ctx.audit_logger,
            audit_source=source,
        )
        convert_result = converter.convert(safe_input, out, force=force,
                                           dry_run=dry_run, verbose=verbose)
        return {'success': convert_result.success}

    task_id = ctx.task_manager.submit('convert', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: Tags
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/tags/update', methods=['POST'])
def api_tags_update():
    ctx = _ctx()
    data = request.get_json(force=True)
    directory = data.get('directory', '')
    album = data.get('album')
    artist = data.get('artist')
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)

    if not directory:
        return jsonify({'error': 'directory is required'}), 400

    safe = ctx.safe_dir(ctx.project_root / directory)
    if not safe:
        return jsonify({'error': 'Invalid directory'}), 400

    desc = f'Tag update: {Path(directory).name}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        tagger = mp.TaggerManager(logger, output_profile=profile,
                                  display_handler=display,
                                  cancel_event=task.cancel_event,
                                  audit_logger=ctx.audit_logger,
                                  audit_source=source)
        tag_result = tagger.update_tags(safe, new_album=album, new_artist=artist,
                                        dry_run=dry_run, verbose=verbose)
        return {'success': tag_result.success}

    task_id = ctx.task_manager.submit('tag_update', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


@api_bp.route('/api/tags/restore', methods=['POST'])
def api_tags_restore():
    ctx = _ctx()
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

    safe = ctx.safe_dir(ctx.project_root / directory)
    if not safe:
        return jsonify({'error': 'Invalid directory'}), 400

    desc = f'Tag restore: {Path(directory).name}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        tagger = mp.TaggerManager(logger, output_profile=profile,
                                  display_handler=display,
                                  cancel_event=task.cancel_event,
                                  audit_logger=ctx.audit_logger,
                                  audit_source=source)
        restore_result = tagger.restore_tags(
            safe,
            restore_album=restore_all or restore_album,
            restore_title=restore_all or restore_title,
            restore_artist=restore_all or restore_artist,
            dry_run=dry_run, verbose=verbose,
        )
        return {'success': restore_result.success}

    task_id = ctx.task_manager.submit('tag_restore', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


@api_bp.route('/api/tags/reset', methods=['POST'])
def api_tags_reset():
    ctx = _ctx()
    data = request.get_json(force=True)
    input_dir = data.get('input_dir', '')
    output_dir = data.get('output_dir', '')
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)

    if not input_dir or not output_dir:
        return jsonify({'error': 'input_dir and output_dir are required'}), 400

    safe_in = ctx.safe_dir(ctx.project_root / input_dir)
    safe_out = ctx.safe_dir(ctx.project_root / output_dir)
    if not safe_in or not safe_out:
        return jsonify({'error': 'Invalid directory'}), 400

    desc = f'Tag reset: {Path(output_dir).name}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        profile = ctx.get_output_profile(config)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        tagger = mp.TaggerManager(logger, output_profile=profile,
                                  prompt_handler=WebPromptHandler(),
                                  display_handler=display,
                                  cancel_event=task.cancel_event,
                                  audit_logger=ctx.audit_logger,
                                  audit_source=source)
        success = tagger.reset_tags_from_source(safe_in, safe_out,
                                                 dry_run=dry_run, verbose=verbose)
        return {'success': success}

    task_id = ctx.task_manager.submit('tag_reset', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: Cover Art
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/cover-art/<action>', methods=['POST'])
def api_cover_art(action):
    if action not in ('embed', 'extract', 'update', 'strip', 'resize'):
        return jsonify({'error': f'Unknown action: {action}'}), 400

    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    directory = data.get('directory', '')
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)

    if not directory:
        return jsonify({'error': 'directory is required'}), 400

    safe = ctx.safe_dir(ctx.project_root / directory)
    if not safe:
        return jsonify({'error': 'Invalid directory'}), 400

    desc = f'Cover art {action}: {Path(directory).name}'
    audit_source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=audit_source)
        profile = ctx.get_output_profile(config)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        cam = mp.CoverArtManager(logger, output_profile=profile,
                                 display_handler=display,
                                 cancel_event=task.cancel_event,
                                 audit_logger=ctx.audit_logger,
                                 audit_source=audit_source)

        if action == 'embed':
            source_dir = data.get('source')
            force = data.get('force', False)
            if source_dir:
                source_dir = ctx.safe_dir(ctx.project_root / source_dir)
            r = cam.embed(safe, source_dir=source_dir, force=force,
                          dry_run=dry_run, verbose=verbose)
            return {'success': r.success}
        elif action == 'extract':
            r = cam.extract(safe, dry_run=dry_run, verbose=verbose)
            return {'success': r.success}
        elif action == 'update':
            image = data.get('image', '')
            if not image:
                return {'success': False, 'error': 'image path required'}
            safe_img = ctx.safe_dir(ctx.project_root / image)
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

    task_id = ctx.task_manager.submit(f'cover_art_{action}', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: File Serving (for iOS companion app)
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/files/<playlist_key>')
def api_files_list(playlist_key):
    """List MP3 files in a playlist with ID3 metadata."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    playlist_dir = ctx.project_root / mp.get_export_dir(profile.name, playlist_key)
    safe = ctx.safe_dir(playlist_dir)
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

    include_sync = request.args.get('include_sync', '').lower() == 'true'
    if include_sync and ctx.sync_tracker:
        sync_map = ctx.sync_tracker.get_file_sync_map(playlist_key)
        for entry in files:
            entry['synced_to'] = sync_map.get(entry['filename'], [])

    return jsonify({
        'playlist': playlist_key,
        'profile': profile.name,
        'file_count': len(files),
        'files': files,
    })


# TODO: Add a web file browser page (template + route) that shows per-file
# sync indicators using the sync-status endpoint below. Currently only
# exposed via API for the iOS companion app.

@api_bp.route('/api/files/<playlist_key>/sync-status')
def api_files_sync_status(playlist_key):
    """Return sync map for files in a playlist (lightweight, no ID3 reads)."""
    ctx = _ctx()
    if not ctx.sync_tracker:
        return jsonify({})
    return jsonify(ctx.sync_tracker.get_file_sync_map(playlist_key))


@api_bp.route('/api/files/<playlist_key>/<filename>')
def api_files_download(playlist_key, filename):
    """Download a single MP3 file."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    playlist_dir = ctx.project_root / mp.get_export_dir(profile.name, playlist_key)
    safe = ctx.safe_dir(playlist_dir)
    if not safe:
        return jsonify({'error': 'Invalid directory'}), 400

    file_path = Path(safe) / filename
    if not file_path.exists() or file_path.suffix.lower() != '.mp3':
        return jsonify({'error': 'File not found'}), 404

    # Validate the file is within the safe directory
    if not str(file_path.resolve()).startswith(str(Path(safe).resolve())):
        return jsonify({'error': 'Invalid path'}), 400

    return send_from_directory(safe, filename, mimetype='audio/mpeg', conditional=True)


@api_bp.route('/api/files/<playlist_key>/<filename>/artwork')
def api_files_artwork(playlist_key, filename):
    """Extract and serve cover art from an MP3 file."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    playlist_dir = ctx.project_root / mp.get_export_dir(profile.name, playlist_key)
    safe = ctx.safe_dir(playlist_dir)
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


@api_bp.route('/api/files/<playlist_key>/download-all')
def api_files_download_all(playlist_key):
    """Stream a ZIP archive of all MP3s in a playlist."""
    import io
    import zipfile

    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    playlist_dir = ctx.project_root / mp.get_export_dir(profile.name, playlist_key)
    safe = ctx.safe_dir(playlist_dir)
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


@api_bp.route('/api/files/download-zip', methods=['POST'])
def api_files_download_zip():
    """Stream a ZIP archive of MP3s from multiple playlists."""
    import io
    import zipfile

    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    playlists = data.get('playlists', [])
    if not playlists:
        return jsonify({'error': 'playlists array is required'}), 400

    config = ctx.get_config()
    profile = ctx.get_output_profile(config)

    # Collect files per playlist, validate directories, enforce limit
    playlist_files = []  # [(playlist_key, [Path, ...])]
    total_count = 0
    for key in playlists:
        playlist_dir = ctx.project_root / mp.get_export_dir(profile.name, key)
        safe = ctx.safe_dir(playlist_dir)
        if not safe or not Path(safe).is_dir():
            continue  # skip missing playlists silently
        mp3s = sorted(Path(safe).glob('*.mp3'))
        if not mp3s:
            continue
        total_count += len(mp3s)
        if total_count > 2000:
            return jsonify({'error': 'Too many files (limit 2000)'}), 413
        playlist_files.append((key, mp3s))

    if not playlist_files:
        return jsonify({'error': 'No MP3 files found in selected playlists'}), 404

    def generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            for key, files in playlist_files:
                for f in files:
                    zf.write(f, f'{key}/{f.name}')
        buf.seek(0)
        while True:
            chunk = buf.read(65536)
            if not chunk:
                break
            yield chunk

    return Response(
        generate_zip(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': 'attachment; filename="music-porter-export.zip"',
        },
    )


# ══════════════════════════════════════════════════════════════════
# API: USB
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# API: Sync Destinations
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/sync/destinations')
def api_sync_destinations():
    """List all sync destinations (saved + auto-detected USB) as a flat list."""
    ctx = _ctx()
    config = ctx.get_config()
    destinations = []
    saved_names = set()

    # Saved destinations (use to_api_dict for scheme-aware serialization)
    for d in config.destinations:
        destinations.append(d.to_api_dict())
        saved_names.add(d.name)

    # Auto-detected USB drives (only in web mode, not server mode)
    # Deduplicate: skip USB drives already saved as destinations
    if current_app.config.get('NO_AUTH'):
        profile = ctx.get_output_profile(config)
        usb_dir = profile.usb_dir if profile else mp.DEFAULT_USB_DIR
        usb_mgr = mp.SyncManager(mp.Logger(verbose=False))
        for vol in usb_mgr.find_usb_drives():
            if vol in saved_names:
                continue
            base = usb_mgr._get_usb_base_path(vol)
            usb_path = f"usb://{base / usb_dir}" if usb_dir else f"usb://{base}"
            dest = mp.SyncDestination(name=vol, path=usb_path)
            destinations.append(dest.to_api_dict())

    return jsonify({'destinations': destinations})


@api_bp.route('/api/sync/destinations', methods=['POST'])
def api_sync_destination_add():
    """Add a saved sync destination."""
    ctx = _ctx()
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    path = data.get('path', '').strip()
    sync_key = data.get('sync_key', '').strip() or None
    if not name or not path:
        return jsonify({'error': 'name and path are required'}), 400
    config = ctx.get_config()
    ok = config.add_destination(name, path, sync_key=sync_key)
    if not ok:
        return jsonify({'error': f"Failed to add destination '{name}'"}), 400
    result = {'ok': True, 'name': name, 'path': path}
    if sync_key:
        result['sync_key'] = sync_key
    return jsonify(result)


@api_bp.route('/api/sync/destinations/<name>', methods=['DELETE'])
def api_sync_destination_delete(name):
    """Remove a saved sync destination."""
    ctx = _ctx()
    config = ctx.get_config()
    ok = config.remove_destination(name)
    if not ok:
        return jsonify({'error': f"Destination '{name}' not found"}), 404
    return jsonify({'ok': True})


@api_bp.route('/api/sync/destinations/<name>/link', methods=['PUT'])
def api_sync_destination_link(name):
    """Link or unlink a destination's sync_key."""
    ctx = _ctx()
    data = request.get_json(force=True)
    new_sync_key = data.get('sync_key', '').strip() or None

    config = ctx.get_config()
    dest = config.get_destination(name)
    if not dest:
        return jsonify({'error': f"Destination '{name}' not found"}), 404

    merge_stats = None

    # If linking and old tracking data exists under the dest name, merge it
    if new_sync_key and ctx.sync_tracker:
        old_effective = dest.effective_key
        if old_effective != new_sync_key:
            merge_stats = ctx.sync_tracker.merge_key(old_effective, new_sync_key)

    ok = config.update_destination_link(name, new_sync_key)
    if not ok:
        return jsonify({'error': f"Failed to update destination '{name}'"}), 400

    result = {'ok': True, 'sync_key': new_sync_key}
    if merge_stats:
        result['merge_stats'] = merge_stats
    return jsonify(result)


@api_bp.route('/api/sync/run', methods=['POST'])
def api_sync_run():
    """Run sync to a named destination."""
    ctx = _ctx()
    data = request.get_json(force=True)
    source_dir = data.get('source_dir', '')
    dest_name = data.get('destination', '')
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)

    if not source_dir:
        return jsonify({'error': 'source_dir is required'}), 400
    if not dest_name:
        return jsonify({'error': 'destination is required'}), 400

    # Look up destination from config
    config = ctx.get_config()
    dest = config.get_destination(dest_name)

    # If not a saved destination, check auto-detected USB drives (web mode only)
    if not dest and current_app.config.get('NO_AUTH'):
        profile = ctx.get_output_profile(config)
        usb_dir = profile.usb_dir if profile else mp.DEFAULT_USB_DIR
        usb_mgr = mp.SyncManager(mp.Logger(verbose=False))
        drives = usb_mgr.find_usb_drives()
        if dest_name in drives:
            base = usb_mgr._get_usb_base_path(dest_name)
            usb_path = f"usb://{base / usb_dir}" if usb_dir else f"usb://{base}"
            dest = mp.SyncDestination(name=dest_name, path=usb_path)

    if not dest:
        return jsonify({'error': f"Destination '{dest_name}' not found"}), 404

    if dest.is_web_client:
        return jsonify({'error': 'web-client destinations can only be synced from the browser'}), 400

    desc = f'Sync: {Path(source_dir).name} → {dest.name}'

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        sync_mgr = mp.SyncManager(logger, display_handler=display,
                                  cancel_event=task.cancel_event,
                                  sync_tracker=ctx.sync_tracker)
        result = sync_mgr.sync_to_destination(
            source_dir, dest_path=dest.path, dest_key=dest.effective_key,
            dry_run=dry_run)
        return {
            'success': result.success,
            'files_found': result.files_found,
            'files_copied': result.files_copied,
            'files_skipped': result.files_skipped,
            'files_failed': result.files_failed,
        }

    task_id = ctx.task_manager.submit('sync', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


@api_bp.route('/api/sync/status')
def api_sync_status():
    """Summary of all tracked sync keys."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    export_dir = str(ctx.project_root / mp.get_export_dir(profile.name))
    results = ctx.sync_tracker.get_all_keys_summary(export_dir)
    return jsonify(results)


@api_bp.route('/api/sync/status/<key>')
def api_sync_status_detail(key):
    """Per-playlist breakdown for one sync key."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    export_dir = str(ctx.project_root / mp.get_export_dir(profile.name))
    status = ctx.sync_tracker.get_sync_status(key, export_dir)
    return jsonify(status.to_dict())


@api_bp.route('/api/sync/keys')
def api_sync_keys():
    """List all tracked sync keys."""
    return jsonify(_ctx().sync_tracker.get_keys())


@api_bp.route('/api/sync/keys/<key>', methods=['DELETE'])
def api_sync_key_delete(key):
    """Delete a sync key and all tracking data."""
    ctx = _ctx()
    ctx.sync_tracker.delete_key(key)
    if ctx.audit_logger:
        ctx.audit_logger.log(
            'sync_key_delete',
            f"Deleted sync tracking for key '{key}'",
            'completed',
            params={'key': key},
            source=ctx.detect_source(),
        )
    return jsonify({'ok': True})


@api_bp.route('/api/sync/keys/<key>/playlists/<playlist>', methods=['DELETE'])
def api_sync_playlist_delete(key, playlist):
    """Delete tracking for one playlist on a sync key."""
    ctx = _ctx()
    count = ctx.sync_tracker.delete_playlist(key, playlist)
    if ctx.audit_logger:
        ctx.audit_logger.log(
            'sync_playlist_delete',
            f"Deleted {count} tracking record(s) for playlist '{playlist}' on key '{key}'",
            'completed',
            params={'key': key, 'playlist': playlist, 'deleted': count},
            source=ctx.detect_source(),
        )
    return jsonify({'ok': True, 'deleted': count})


@api_bp.route('/api/sync/keys/<key>/prune', methods=['POST'])
def api_sync_key_prune(key):
    """Prune stale tracking records for a sync key."""
    ctx = _ctx()
    config = ctx.get_config()
    profile = ctx.get_output_profile(config)
    export_dir = str(ctx.project_root / mp.get_export_dir(profile.name))
    result = ctx.sync_tracker.prune_stale(key, export_dir)
    if ctx.audit_logger:
        ctx.audit_logger.log(
            'sync_key_prune',
            f"Pruned {result['pruned_count']} stale record(s) for key '{key}'",
            'completed',
            params={'key': key, **result},
            source=ctx.detect_source(),
        )
    return jsonify(result)


@api_bp.route('/api/sync/client-record', methods=['POST'])
def api_sync_client_record():
    """Record files synced via client-side (browser) sync for tracking."""
    ctx = _ctx()
    if not ctx.sync_tracker:
        return jsonify({'error': 'Sync tracker not available'}), 400

    data = request.get_json(silent=True) or {}
    sync_key = data.get('sync_key', '')
    playlist = data.get('playlist', '')
    files = data.get('files', [])

    if not sync_key or not playlist or not files:
        return jsonify({'error': 'sync_key, playlist, and files are required'}), 400

    ctx.sync_tracker.record_batch(sync_key, playlist, files)

    if ctx.audit_logger:
        ctx.audit_logger.log(
            'client_sync_record',
            f"Recorded {len(files)} file(s) for '{playlist}' on key '{sync_key}'",
            'completed',
            params={'sync_key': sync_key, 'playlist': playlist,
                    'file_count': len(files)},
            source=ctx.detect_source(),
        )

    # Auto-register web-client:// destination if not already saved
    folder_name = data.get('folder_name', '')
    if folder_name:
        config = ctx.get_config()
        if not config.get_destination(sync_key):
            config.add_destination(sync_key, f'web-client://{folder_name}')

    return jsonify({'ok': True, 'recorded': len(files)})


# ══════════════════════════════════════════════════════════════════
# API: Tasks
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/tasks')
def api_tasks_list():
    return jsonify(_ctx().task_manager.list_all())


@api_bp.route('/api/tasks/history')
def api_tasks_history():
    """Paginated task history with optional filters."""
    ctx = _ctx()
    db = ctx.task_manager._db
    if not db:
        return jsonify({'entries': [], 'total': 0, 'limit': 50, 'offset': 0})
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    operation = request.args.get('operation') or None
    status = request.args.get('status') or None
    date_from = request.args.get('from') or None
    date_to = request.args.get('to') or None
    entries, total = db.get_entries(
        limit=limit, offset=offset,
        operation=operation, status=status,
        date_from=date_from, date_to=date_to,
    )
    # Merge live elapsed for running tasks
    for entry in entries:
        live = ctx.task_manager._tasks.get(entry['id'])
        if live and live.status == 'running':
            entry['elapsed'] = round(live.elapsed(), 1)
            entry['status'] = live.status
    return jsonify({
        'entries': entries,
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@api_bp.route('/api/tasks/stats')
def api_tasks_stats():
    """Aggregate task history statistics."""
    db = _ctx().task_manager._db
    if not db:
        return jsonify({'total': 0, 'today': 0, 'by_operation': {}, 'by_status': {}})
    return jsonify(db.get_stats())


@api_bp.route('/api/tasks/clear', methods=['POST'])
def api_tasks_clear():
    """Delete old task history entries."""
    ctx = _ctx()
    db = ctx.task_manager._db
    if not db:
        return jsonify({'error': 'Task history not available'}), 503
    data = request.get_json(silent=True) or {}
    if not data.get('confirm'):
        return jsonify({'error': 'Set confirm: true to clear'}), 400
    before_date = data.get('before_date')
    count = db.clear(before_date=before_date)
    return jsonify({'deleted': count})


@api_bp.route('/api/tasks/<task_id>')
def api_tasks_get(task_id):
    ctx = _ctx()
    # Check in-memory first (has thread/queue for active tasks)
    task = ctx.task_manager._tasks.get(task_id)
    if task:
        return jsonify(task.to_dict())
    # Fall back to DB for historical tasks
    if ctx.task_manager._db:
        entry = ctx.task_manager._db.get(task_id)
        if entry:
            return jsonify(entry)
    return jsonify({'error': 'Task not found'}), 404


@api_bp.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def api_tasks_cancel(task_id):
    if _ctx().task_manager.cancel(task_id):
        return jsonify({'ok': True})
    return jsonify({'error': 'Task not found or not running'}), 404


# ══════════════════════════════════════════════════════════════════
# API: SSE Stream
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/stream/<task_id>')
def api_stream(task_id):
    task = _ctx().task_manager.get(task_id)
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


# ══════════════════════════════════════════════════════════════════
# iOS Pairing QR Code
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/pairing-qr')
def api_pairing_qr():
    """Return QR code as SVG image for iOS app pairing."""
    ctx = _ctx()
    if current_app.config.get('NO_AUTH'):
        return jsonify({'error': 'Not available in web mode'}), 404
    host = current_app.config.get('SERVER_HOST')
    port = current_app.config.get('SERVER_PORT')
    if not host or not port:
        return jsonify({'error': 'Server info not available'}), 500
    try:
        import io

        import segno
    except ImportError:
        return jsonify({'error': 'segno not installed'}), 503
    qr_data = {"host": host, "port": port, "key": ctx.api_key}
    external_url = current_app.config.get('EXTERNAL_URL')
    if external_url:
        qr_data["url"] = external_url
    payload = json.dumps(qr_data)
    qr = segno.make(payload)
    buf = io.BytesIO()
    qr.save(buf, kind='svg', dark='#ffffff', light='#1a1a2e',
            scale=4, xmldecl=False)
    return Response(buf.getvalue(), mimetype='image/svg+xml',
                    headers={'Cache-Control': 'no-store'})


@api_bp.route('/api/pairing-info')
def api_pairing_info():
    """Return server pairing details as JSON."""
    ctx = _ctx()
    if current_app.config.get('NO_AUTH'):
        return jsonify({'error': 'Not available in web mode'}), 404
    host = current_app.config.get('SERVER_HOST')
    port = current_app.config.get('SERVER_PORT')
    if not host or not port:
        return jsonify({'error': 'Server info not available'}), 500
    external_url = current_app.config.get('EXTERNAL_URL')
    return jsonify({
        'api_key': ctx.api_key,
        'host': host,
        'port': port,
        'address': external_url if external_url else f"{host}:{port}",
    })


# ══════════════════════════════════════════════════════════════════
# API: About / Release Notes
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/about')
def api_about():
    """Return version info and release notes."""
    notes_path = _ctx().project_root / 'release-notes.txt'
    notes = notes_path.read_text() if notes_path.exists() else ''
    return jsonify({'version': mp.VERSION, 'release_notes': notes})


# ══════════════════════════════════════════════════════════════════
# Audit Log
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/audit')
def api_audit_list():
    """Paginated audit entries with optional filters."""
    ctx = _ctx()
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    operation = request.args.get('operation') or None
    status = request.args.get('status') or None
    date_from = request.args.get('from') or None
    date_to = request.args.get('to') or None
    entries, total = ctx.audit_logger.get_entries(
        limit=limit, offset=offset,
        operation=operation, status=status,
        date_from=date_from, date_to=date_to,
    )
    return jsonify({
        'entries': entries,
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@api_bp.route('/api/audit/stats')
def api_audit_stats():
    return jsonify(_ctx().audit_logger.get_stats())


@api_bp.route('/api/audit/clear', methods=['POST'])
def api_audit_clear():
    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    if not data.get('confirm'):
        return jsonify({'error': 'Set confirm: true to clear'}), 400
    before_date = data.get('before_date')
    count = ctx.audit_logger.clear(before_date=before_date)
    ctx.audit_logger.log('audit_clear', f'Cleared {count} audit entries',
                         'completed', params={'count': count,
                                              'before_date': before_date},
                         source=ctx.detect_source())
    return jsonify({'deleted': count})
