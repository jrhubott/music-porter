"""
web_api.py - Flask Blueprint with all REST API routes for music-porter

Extracted from web_ui.py to separate UI (page routes, templates) from
API endpoints (REST, background tasks, SSE streaming).

All routes are registered on ``api_bp`` and access shared state through
``AppContext`` stored in ``current_app.config['CTX']``.
"""

import hashlib
import json
import queue
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

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


def _build_display_filename(track):
    """Build a human-readable filename from track metadata.

    Returns 'Artist - Title.mp3' or 'Title.mp3' if artist is empty.
    """
    artist = track.get('artist', '')
    title = track.get('title', '') or track.get('filename', 'Unknown')
    if artist:
        return f"{mp.sanitize_filename(artist)} - {mp.sanitize_filename(title)}.mp3"
    return f"{mp.sanitize_filename(title)}.mp3"


def _content_disposition(filename):
    """Build RFC 5987 Content-Disposition for non-ASCII filenames."""
    try:
        filename.encode('latin-1')
        return f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        ascii_fallback = filename.encode('ascii', 'replace').decode('ascii')
        utf8_quoted = quote(filename)
        return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_quoted}"


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
        'api_version': 2,
    })


@api_bp.route('/api/server-info')
def api_server_info():
    """Return server metadata for client discovery."""
    ctx = _ctx()
    config = ctx.get_config()
    mp.load_output_profiles(config)
    result = {
        'name': ctx.get_server_name(),
        'version': mp.VERSION,
        'platform': mp.get_os_display_name(),
        'profiles': list(mp.OUTPUT_PROFILES.keys()),
        'api_version': 2,
    }
    external_url = current_app.config.get('EXTERNAL_URL')
    if external_url:
        result['external_url'] = external_url
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════
# API: Dashboard Status
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/status')
def api_status():
    ctx = _ctx()

    # Cookie status
    cookie_mgr = mp.CookieManager(mp.DEFAULT_COOKIES, mp.Logger(verbose=False))
    cs = cookie_mgr.validate()
    cookie_data = {
        'valid': cs.valid,
        'exists': cs.exists,
        'reason': cs.reason,
        'days_remaining': round(cs.days_until_expiration) if cs.days_until_expiration else None,
    }

    # Library stats from TrackDB
    if ctx.track_db:
        stats = ctx.track_db.get_playlist_stats()
        playlist_count = len(stats)
        total_files = sum(s['track_count'] for s in stats)
        total_size = sum(s['total_size_bytes'] for s in stats)
    else:
        # Fallback: scan flat MP3 directory
        mp3_path = Path(mp.get_audio_dir())
        total_files = 0
        total_size = 0
        playlist_count = 0
        if mp3_path.exists():
            for f in mp3_path.glob('*.mp3'):
                total_files += 1
                total_size += f.stat().st_size
            if total_files > 0:
                playlist_count = 1  # Can't determine per-playlist without DB

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


@api_bp.route('/api/cookies/upload', methods=['POST'])
def api_cookies_upload():
    """Accept Netscape-format cookies from a remote client and validate them."""
    import shutil

    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    cookie_text = data.get('cookies', '').strip()

    if not cookie_text:
        return jsonify({'error': 'Missing or empty "cookies" field'}), 400

    cookie_path = Path(mp.DEFAULT_COOKIES)

    # Backup existing cookies before overwriting
    if cookie_path.exists():
        backup_path = Path(str(cookie_path) + '.backup')
        shutil.copy2(cookie_path, backup_path)

    # Write the uploaded cookie text
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(cookie_text, encoding='utf-8')

    # Clean non-Apple cookies and validate
    cookie_mgr = mp.CookieManager(mp.DEFAULT_COOKIES, mp.Logger(verbose=False))
    cookie_mgr.clean_cookies()
    status = cookie_mgr.validate()

    days_remaining = (round(status.days_until_expiration)
                      if status.days_until_expiration else None)

    # Audit trail
    if ctx.audit_logger:
        ctx.audit_logger.log(
            operation='cookie_upload',
            description=f'Cookies uploaded via sync client — '
                        f'{"valid" if status.valid else "invalid"}: {status.reason}',
            params={'valid': status.valid, 'days_remaining': days_remaining},
            status='success' if status.valid else 'warning',
            source=ctx.detect_source(),
        )

    return jsonify({
        'valid': status.valid,
        'reason': status.reason,
        'days_remaining': days_remaining,
    })


# ══════════════════════════════════════════════════════════════════
# API: Library Summary
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/summary')
def api_summary():
    ctx = _ctx()
    start_time = time.time()

    # Use TrackDB for library summary instead of scanning ID3 tags
    playlist_stats = ctx.track_db.get_playlist_stats()

    if not playlist_stats:
        return jsonify({
            'total_playlists': 0, 'total_files': 0,
            'total_size_bytes': 0, 'scan_duration': 0,
            'playlists': [],
        })

    total_files = 0
    total_size = 0
    total_cover_with = 0
    total_cover_without = 0
    today = date.today()
    freshness_counts = {"current": 0, "recent": 0, "stale": 0, "outdated": 0}

    playlists_json = []
    for ps in playlist_stats:
        track_count = ps['track_count']
        size_bytes = ps['total_size_bytes']
        cover_with = ps['cover_with']
        cover_without = ps['cover_without']

        total_files += track_count
        total_size += size_bytes
        total_cover_with += cover_with
        total_cover_without += cover_without

        # Get last modified from track DB updated_at
        last_modified = None
        tracks_for_pl = ctx.track_db.get_tracks_by_playlist(ps['playlist'])
        if tracks_for_pl:
            last_mod_ts = max(t['updated_at'] for t in tracks_for_pl)
            last_modified = datetime.fromtimestamp(last_mod_ts)

        freshness = _get_freshness_level(last_modified, today)
        freshness_counts[freshness] += 1

        avg_size_mb = (size_bytes / track_count / (1024 * 1024)
                       if track_count > 0 else 0)

        playlists_json.append({
            'name': ps['playlist'],
            'file_count': track_count,
            'size_bytes': size_bytes,
            'avg_size_mb': round(avg_size_mb, 1),
            'last_modified': last_modified.isoformat() if last_modified else None,
            'freshness': freshness,
            'tags_checked': track_count,
            'tags_protected': track_count,
            'cover_with': cover_with,
            'cover_without': cover_without,
        })

    scan_duration = round(time.time() - start_time, 2)

    return jsonify({
        'total_playlists': len(playlist_stats),
        'total_files': total_files,
        'total_size_bytes': total_size,
        'scan_duration': scan_duration,
        'freshness': freshness_counts,
        'tag_integrity': {
            'protected': total_files,
            'checked': total_files,
            'missing': 0,
        },
        'cover_art': {
            'with_art': total_cover_with,
            'without_art': total_cover_without,
            'original': total_cover_with,
            'resized': 0,
        },
        'playlists': playlists_json,
    })


# ══════════════════════════════════════════════════════════════════
# API: Library Stats (music/ directory)
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/library-stats')
def api_library_stats():
    ctx = _ctx()
    quiet_logger = mp.Logger(verbose=False)
    mgr = mp.SummaryManager(logger=quiet_logger)
    stats = mgr.scan_music_library(track_db=ctx.track_db)

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
def api_library_unconverted(playlist_key):
    """List M4A source files that have no matching TrackDB record."""
    ctx = _ctx()

    if '/' in playlist_key or '..' in playlist_key:
        return jsonify({'error': 'Invalid playlist key'}), 400

    source_dir = ctx.project_root / mp.get_source_dir(playlist_key)
    if not source_dir.exists():
        return jsonify({'files': []})

    unconverted = []
    for m4a_file in sorted(source_dir.rglob('*.m4a')):
        if m4a_file.name.startswith('._'):
            continue
        rel_source = str(
            Path(mp.get_source_dir(playlist_key))
            / m4a_file.relative_to(source_dir)
        )
        existing = ctx.track_db.get_track_by_source_m4a(rel_source)
        if existing:
            continue
        # Extract artist/title from gamdl directory structure
        rel_parts = m4a_file.relative_to(source_dir).parts
        artist = rel_parts[0] if len(rel_parts) > 1 else 'Unknown'
        title = m4a_file.stem
        unconverted.append({
            'artist': artist,
            'title': title,
            'display_name': f"{artist} - {title}",
        })

    return jsonify({'files': unconverted})


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
    eq_data = data.get('eq', {})
    no_eq = data.get('no_eq', False)

    if not playlists:
        return jsonify({'error': 'playlists list is required'}), 400

    # Validate all playlist directories
    for key in playlists:
        if '/' in key or '..' in key:
            return jsonify({'error': f'Invalid playlist key: {key}'}), 400
        input_path = ctx.project_root / mp.get_source_dir(key)
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
        quality_preset = config.get_setting('quality_preset', preset) or mp.DEFAULT_QUALITY_PRESET
        workers = config.get_setting('workers', mp.DEFAULT_WORKERS)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)

        total_success = 0
        total_failed = 0
        eq_mgr = mp.EQConfigManager()

        total_pl = len(playlists)
        for i, key in enumerate(playlists):
            if task.cancel_event.is_set():
                break
            display.show_overall_progress(
                i + 1, total_pl,
                f"Playlist {i + 1} of {total_pl}: {key}")
            logger.info(f"[{i+1}/{total_pl}] Converting {key}...")
            input_dir = str(ctx.project_root / mp.get_source_dir(key))
            out = mp.get_audio_dir()

            # Resolve EQ per playlist
            if no_eq:
                eq_config = mp.EQConfig()
            elif eq_data and any(eq_data.values()):
                eq_config = mp.EQConfig.from_dict(eq_data)
            else:
                eq_config = eq_mgr.get_eq('default', key)

            converter = mp.Converter(
                logger, quality_preset=quality_preset, workers=workers,
                track_db=ctx.track_db,
                display_handler=display,
                cancel_event=task.cancel_event,
                audit_logger=ctx.audit_logger,
                audit_source=source,
                eq_config=eq_config,
            )
            result = converter.convert(input_dir, out, force=force,
                                       dry_run=dry_run, verbose=verbose,
                                       playlist_key=key)
            if result.success:
                total_success += 1
            else:
                total_failed += 1

        if playlists:
            display.show_overall_progress(
                total_pl, total_pl,
                f"All {total_pl} playlists complete")

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
    playlists = ctx.playlist_db.get_all()
    stats = {s['playlist']: s
             for s in ctx.track_db.get_playlist_stats()} if ctx.track_db else {}

    today = date.today()

    # Build ETag from playlist data + file counts + size + duration + freshness
    etag_parts = [
        (p['key'], p['name'],
         stats.get(p['key'], {}).get('track_count', 0),
         stats.get(p['key'], {}).get('total_size_bytes', 0),
         stats.get(p['key'], {}).get('total_duration_s', 0),
         stats.get(p['key'], {}).get('max_updated_at', 0))
        for p in playlists
    ]
    etag_hash = hashlib.md5(
        json.dumps(etag_parts, sort_keys=True).encode()
    ).hexdigest()
    etag = f'"{etag_hash}"'

    if_none_match = request.headers.get('If-None-Match')
    if if_none_match == etag:
        return Response(status=304)

    def _playlist_freshness(key):
        max_ts = stats.get(key, {}).get('max_updated_at', 0)
        last_mod = datetime.fromtimestamp(max_ts) if max_ts > 0 else None
        return _get_freshness_level(last_mod, today)

    resp = jsonify([
        {'key': p['key'], 'url': p['url'], 'name': p['name'],
         'file_count': stats.get(p['key'], {}).get('track_count', 0),
         'size_bytes': stats.get(p['key'], {}).get('total_size_bytes', 0),
         'duration_s': stats.get(p['key'], {}).get('total_duration_s', 0),
         'freshness': _playlist_freshness(p['key'])}
        for p in playlists
    ])
    resp.headers['ETag'] = etag
    return resp


@api_bp.route('/api/playlists', methods=['POST'])
def api_playlists_add():
    ctx = _ctx()
    data = request.get_json(force=True)
    key = data.get('key', '').strip()
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()

    if not key or not url or not name:
        return jsonify({'error': 'key, url, and name are required'}), 400

    if ctx.playlist_db.add(key, url, name):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist key '{key}' already exists"}), 409


@api_bp.route('/api/playlists/<key>', methods=['PUT'])
def api_playlists_update(key):
    ctx = _ctx()
    data = request.get_json(force=True)
    if ctx.playlist_db.update(key, url=data.get('url'), name=data.get('name')):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist '{key}' not found"}), 404


@api_bp.route('/api/playlists/<key>', methods=['DELETE'])
def api_playlists_delete(key):
    ctx = _ctx()
    if ctx.playlist_db.remove(key):
        return jsonify({'ok': True})
    return jsonify({'error': f"Playlist '{key}' not found"}), 404


@api_bp.route('/api/playlists/<key>/delete-data', methods=['POST'])
def api_playlist_delete_data(key):
    ctx = _ctx()
    data = request.get_json(force=True) if request.data else {}
    delete_source = data.get('delete_source', True)
    delete_library = data.get('delete_library', data.get('delete_export', True))
    remove_config = data.get('remove_config', False)
    dry_run = data.get('dry_run', False)

    config = ctx.get_config()

    # Validate playlist exists in DB or has data on disk
    source_dir = ctx.project_root / mp.get_source_dir(key)
    playlist_exists = ctx.playlist_db.get(key) is not None
    has_tracks = ctx.track_db.get_tracks_by_playlist(key) if ctx.track_db else []
    data_exists = source_dir.exists() or bool(has_tracks)

    if not playlist_exists and not data_exists:
        return jsonify({'error': f"Playlist '{key}' not found and has no data on disk"}), 404

    logger = mp.Logger(verbose=False)
    prompt = WebPromptHandler()
    data_manager = mp.DataManager(logger, config, prompt_handler=prompt,
                                  audit_logger=ctx.audit_logger,
                                  audit_source=ctx.detect_source(),
                                  track_db=ctx.track_db,
                                  playlist_db=ctx.playlist_db)
    result = data_manager.delete_playlist_data(
        key,
        delete_source=delete_source,
        delete_library=delete_library,
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
        name: {
            'description': p.description,
            'id3_title': p.id3_title,
            'id3_artist': p.id3_artist,
            'id3_album': p.id3_album,
            'id3_genre': p.id3_genre,
            'id3_extra': p.id3_extra,
            'filename': p.filename,
            'directory': p.directory,
            'id3_versions': p.id3_versions,
            'artwork_size': p.artwork_size,
            'usb_dir': p.usb_dir,
        }
        for name, p in mp.OUTPUT_PROFILES.items()
    }
    return jsonify({
        'settings': config.settings,
        'profiles': profiles,
        'quality_presets': list(mp.QUALITY_PRESETS.keys()),
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
    ctx.invalidate_config()

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

    Body: {enabled, interval_hours, playlists, preset, retry_minutes,
           max_retries, run_at, on_missed}
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

    run_at = data.get('run_at')
    if run_at is not None and run_at != '':
        if not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', run_at):
            return jsonify({'error': 'run_at must be HH:MM (00:00-23:59)'}), 400

    on_missed = data.get('on_missed')
    if on_missed is not None and on_missed not in ('run', 'skip'):
        return jsonify({'error': "on_missed must be 'run' or 'skip'"}), 400

    # Merge with current config
    current = ctx.scheduler.status()
    # Normalize empty run_at string to None
    raw_run_at = data.get('run_at', current.get('run_at'))
    new_settings = {
        'enabled': data.get('enabled', current['enabled']),
        'interval_hours': data.get('interval_hours', current['interval_hours']),
        'playlists': data.get('playlists', current['playlists']),
        'preset': data.get('preset', current['preset']) or None,
        'retry_minutes': data.get('retry_minutes', current['retry_minutes']),
        'max_retries': data.get('max_retries', current['max_retries']),
        'run_at': raw_run_at or None,
        'on_missed': data.get('on_missed', current.get('on_missed', 'run')),
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
    """List playlist keys that have source M4A files."""
    ctx = _ctx()
    source_root = ctx.project_root / mp.DEFAULT_LIBRARY_DIR / mp.SOURCE_SUBDIR / mp.DEFAULT_IMPORTER
    dirs = []
    if source_root.exists():
        for d in sorted(source_root.iterdir()):
            if d.is_dir() and not d.name.startswith('.'):
                dirs.append(d.name)
    return jsonify(dirs)


@api_bp.route('/api/directories/export')
def api_dirs_export():
    """List library playlist directories with output MP3 counts."""
    ctx = _ctx()
    playlist_map = {p['key']: p['name'] for p in ctx.playlist_db.get_all()}
    dirs = []
    if ctx.track_db:
        for ps in ctx.track_db.get_playlist_stats():
            pl = ps['playlist']
            dirs.append({
                'name': pl,
                'display_name': playlist_map.get(pl, pl),
                'files': ps['track_count'],
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
        'sync_destination': r.usb_destination,
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
    eq_data = data.get('eq', {})
    no_eq = data.get('no_eq', False)

    if not auto and not playlist_key and not url:
        return jsonify({'error': 'Specify playlist, url, or auto'}), 400

    desc = 'Pipeline: all playlists' if auto else f'Pipeline: {playlist_key or url}'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        config = mp.ConfigManager(logger=logger, audit_logger=ctx.audit_logger,
                                  audit_source=source)
        workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

        # DependencyChecker just for venv_python path — skip check_all()
        # to avoid pip subprocess / os.execv() in background threads.
        deps = mp.DependencyChecker(logger)

        quality_preset = preset or config.get_setting(
            'quality_preset', mp.DEFAULT_QUALITY_PRESET) or mp.DEFAULT_QUALITY_PRESET
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)

        # Resolve EQ config
        eq_mgr = mp.EQConfigManager()
        eq_cli_override = None
        if no_eq:
            eq_cli_override = mp.EQConfig()
        elif eq_data and any(eq_data.values()):
            eq_cli_override = mp.EQConfig.from_dict(eq_data)

        orchestrator = mp.PipelineOrchestrator(
            logger, deps, config,
            quality_preset=quality_preset,
            workers=workers,
            display_handler=display,
            cancel_event=task.cancel_event,
            audit_logger=ctx.audit_logger,
            audit_source=source,
            sync_tracker=ctx.sync_tracker,
            track_db=ctx.track_db,
            playlist_db=ctx.playlist_db,
            eq_config_manager=eq_mgr,
            eq_config_override=eq_cli_override,
            project_root=ctx.project_root,
        )

        # Resolve sync destination by name
        sync_destination = None
        if sync_dest_name:
            saved = ctx.sync_tracker.get_destination(sync_dest_name)
            if saved:
                sync_destination = saved

        if auto:
            logger.info("Auto mode: processing all playlists")
            aggregate = mp.AggregateStatistics()
            all_playlists = ctx.playlist_db.get_all()
            total_pl = len(all_playlists)
            for i, pl in enumerate(all_playlists):
                display.show_overall_progress(
                    i + 1, total_pl,
                    f"Playlist {i + 1} of {total_pl}: {pl['name']}")
                logger.info(f"\n{'=' * 60}")
                logger.info(f"Processing {i+1}/{total_pl}: {pl['name']}")
                logger.info(f"{'=' * 60}")
                orchestrator.run_full_pipeline(
                    playlist=pl['key'], auto=True,
                    sync_destination=sync_destination,
                    dry_run=dry_run, verbose=verbose,
                    quality_preset=quality_preset,
                )
                aggregate.add_playlist_result(orchestrator.stats)
            if all_playlists:
                display.show_overall_progress(
                    total_pl, total_pl,
                    f"All {total_pl} playlists complete")
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
    eq_data = data.get('eq', {})
    no_eq = data.get('no_eq', False)

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
        workers = config.get_setting('workers', mp.DEFAULT_WORKERS)

        # Resolve EQ config
        eq_mgr = mp.EQConfigManager()
        # input_dir is library/source/gamdl/<key> — playlist key is last part
        playlist_key = Path(input_dir).name
        if no_eq:
            eq_config = mp.EQConfig()
        elif eq_data and any(eq_data.values()):
            eq_config = mp.EQConfig.from_dict(eq_data)
        else:
            eq_config = eq_mgr.get_eq(mp.DEFAULT_OUTPUT_TYPE, playlist_key)

        out = output_dir if output_dir else mp.get_audio_dir()
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        converter = mp.Converter(
            logger, quality_preset=preset, workers=workers,
            track_db=ctx.track_db,
            display_handler=display,
            cancel_event=task.cancel_event,
            audit_logger=ctx.audit_logger,
            audit_source=source,
            eq_config=eq_config,
        )
        convert_result = converter.convert(
            safe_input, out, playlist_key=playlist_key,
            force=force, dry_run=dry_run, verbose=verbose)
        return {'success': convert_result.success}

    task_id = ctx.task_manager.submit('convert', desc, _run,
                                      source=ctx.detect_source())
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})



# ══════════════════════════════════════════════════════════════════
# API: Library Maintenance
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/library/backfill-metadata', methods=['POST'])
def api_library_backfill_metadata():
    """Re-read M4A tags to populate extended metadata columns."""
    ctx = _ctx()
    desc = 'Backfill track metadata from source M4A files'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        result = mp.backfill_track_metadata(
            ctx.track_db, project_root=ctx.project_root,
            logger=logger, display_handler=display,
            cancel_event=task.cancel_event)
        if ctx.audit_logger:
            ctx.audit_logger.log(
                'backfill_metadata', desc, 'completed',
                params=result, source=source)
        return result

    task_id = ctx.task_manager.submit('backfill_metadata', desc, _run,
                                      source=source)
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


@api_bp.route('/api/library/audit', methods=['POST'])
def api_library_audit():
    """Verify DB records match filesystem and clean up orphans."""
    ctx = _ctx()
    data = request.get_json(force=True) if request.data else {}
    allow_updates = data.get('allow_updates', False)
    mode = 'with updates' if allow_updates else 'report only'
    desc = f'Library audit ({mode})'
    source = ctx.detect_source()

    def _run(task_id):
        logger = ctx.make_logger(task_id)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)
        result = mp.audit_library(
            ctx.track_db, project_root=ctx.project_root,
            logger=logger, display_handler=display,
            cancel_event=task.cancel_event,
            sync_tracker=ctx.sync_tracker,
            allow_updates=allow_updates)
        if ctx.audit_logger:
            # Don't log the full details list — just the summary counts
            summary = {k: v for k, v in result.items() if k != 'details'}
            ctx.audit_logger.log(
                'library_audit', desc, 'completed',
                params=summary, source=source)
        return result

    task_id = ctx.task_manager.submit('library_audit', desc, _run,
                                      source=source)
    if task_id is None:
        return jsonify({'error': 'Another operation is already running'}), 409
    return jsonify({'task_id': task_id})


# ══════════════════════════════════════════════════════════════════
# API: File Serving (for iOS companion app)
# ══════════════════════════════════════════════════════════════════

@api_bp.route('/api/files/<playlist_key>')
def api_files_list(playlist_key):
    """List MP3 files in a playlist with metadata from TrackDB.

    Optional query params:
    - ``?profile=X``: use TagApplicator to build profile-specific
      ``display_filename`` and ``output_subdir`` for each file.
    - ``?include_sync=true``: include per-file sync status.

    Supports ETag-based conditional requests: returns 304 when
    ``If-None-Match`` matches the current playlist fingerprint.
    """
    ctx = _ctx()

    # DB-driven file list — all MP3s are in flat library/audio/
    tracks = ctx.track_db.get_tracks_by_playlist(playlist_key)
    if not tracks:
        return jsonify({'error': f'No tracks found for playlist: {playlist_key}'}), 404

    # ETag check — early return before any TagApplicator or serialization work
    profile_name = request.args.get('profile')
    fingerprint = ctx.track_db.get_playlist_fingerprint(playlist_key)
    if fingerprint:
        etag_source = f"{fingerprint}:{profile_name or ''}"
        etag_hash = hashlib.md5(etag_source.encode()).hexdigest()
        etag = f'"{etag_hash}"'
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match == etag:
            return Response(status=304)
    else:
        etag = None

    # Profile-aware naming
    tag_applicator = None
    profile = None
    playlist_display_name = playlist_key
    if profile_name:
        profile = mp.OUTPUT_PROFILES.get(profile_name)
        if profile:
            tag_applicator = mp.TagApplicator(ctx.track_db,
                                              project_root=ctx.project_root)
            # Resolve human-readable playlist name from DB
            pl_rec = ctx.playlist_db.get(playlist_key)
            if pl_rec:
                playlist_display_name = pl_rec['name']

    files = []
    for track in tracks:
        file_path = ctx.project_root / track['file_path']
        if not file_path.exists():
            continue

        filename = file_path.name
        # Profile-aware display_filename and output_subdir
        if tag_applicator and profile:
            disp = tag_applicator.build_output_filename(
                track, profile, playlist_display_name)
            subdir = tag_applicator.build_output_subdir(
                track, profile, playlist_display_name)
        else:
            disp = _build_display_filename(track)
            subdir = None

        entry = {
            'filename': filename,
            'display_filename': disp,
            'size': track['file_size_bytes'] or file_path.stat().st_size,
            'duration': round(track['duration_s'], 1) if track['duration_s'] else 0,
            'title': track['title'],
            'artist': track['artist'],
            'album': track['album'],
            'uuid': track['uuid'],
            'has_cover_art': bool(track['cover_art_path']),
            'created_at': track['created_at'],
            'updated_at': track['updated_at'],
        }
        if subdir is not None:
            entry['output_subdir'] = subdir
        files.append(entry)

    # Deduplicate display_filenames — append (2), (3), etc. for collisions.
    # Scoped per output_subdir so cross-directory names don't collide.
    disp_names = [e['display_filename'] for e in files]
    scopes = [e.get('output_subdir', '') for e in files]
    deduped = mp.deduplicate_filenames(disp_names, scopes)
    for entry, name in zip(files, deduped, strict=True):
        entry['display_filename'] = name

    include_sync = request.args.get('include_sync', '').lower() == 'true'
    if include_sync and ctx.sync_tracker:
        sync_map = ctx.sync_tracker.get_file_sync_map(playlist_key)
        for entry in files:
            entry['synced_to'] = sync_map.get(entry['filename'], [])

    result = {
        'playlist': playlist_key,
        'file_count': len(files),
        'files': files,
    }
    if profile_name:
        result['name'] = playlist_display_name
    resp = jsonify(result)
    if etag:
        resp.headers['ETag'] = etag
    return resp


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
    """Download a single MP3 file.

    Without ``?profile=X``: serves the clean library MP3 (UUID-only tags).
    With ``?profile=X``: streams a tagged copy using TagApplicator.
    """
    ctx = _ctx()
    mp3_dir = ctx.project_root / mp.get_audio_dir()
    safe = ctx.safe_dir(mp3_dir)
    if not safe:
        return jsonify({'error': 'Invalid directory'}), 400

    file_path = Path(safe) / filename
    if not file_path.exists() or file_path.suffix.lower() != '.mp3':
        return jsonify({'error': 'File not found'}), 404

    # Validate the file is within the safe directory
    if not str(file_path.resolve()).startswith(str(Path(safe).resolve())):
        return jsonify({'error': 'Invalid path'}), 400

    # Look up track metadata from DB for human-readable download name
    rel_path = f"{mp.get_audio_dir()}/{filename}"
    track_meta = ctx.track_db.get_track_by_path(rel_path)
    download_name = _build_display_filename(track_meta) if track_meta else filename

    profile_name = request.args.get('profile')
    if not profile_name:
        return send_from_directory(safe, filename, mimetype='audio/mpeg',
                                   conditional=True,
                                   download_name=download_name)

    # Serve with profile-specific tags applied on-the-fly
    config = ctx.get_config()
    mp.load_output_profiles(config)
    if profile_name not in mp.OUTPUT_PROFILES:
        return jsonify({'error': f'Unknown profile: {profile_name}'}), 400
    profile = mp.OUTPUT_PROFILES[profile_name]

    if not track_meta:
        return jsonify({'error': 'Track not found in database'}), 404

    tag_applicator = mp.TagApplicator(ctx.track_db,
                                      project_root=str(ctx.project_root))

    # Resolve human-readable playlist name from DB
    playlist_display_name = playlist_key
    pl_rec = ctx.playlist_db.get(playlist_key)
    if pl_rec:
        playlist_display_name = pl_rec['name']

    # Use profile-formatted filename for Content-Disposition
    profile_download_name = tag_applicator.build_output_filename(
        track_meta, profile, playlist_display_name)

    id3_bytes, audio_offset, total_size = tag_applicator.build_tagged_stream(
        str(file_path), track_meta, profile, playlist_display_name)

    def _generate():
        yield id3_bytes
        with open(str(file_path), 'rb') as f:
            f.seek(audio_offset)
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return Response(
        _generate(),
        mimetype='audio/mpeg',
        headers={
            'Content-Length': str(total_size),
            'Content-Disposition': _content_disposition(profile_download_name),
        },
    )


@api_bp.route('/api/files/<playlist_key>/<filename>/artwork')
def api_files_artwork(playlist_key, filename):
    """Serve cover art from the library artwork directory."""
    ctx = _ctx()

    # Look up track in DB to find cover art path
    rel_path = f"{mp.get_audio_dir()}/{filename}"
    track = ctx.track_db.get_track_by_path(rel_path)
    if not track or not track['cover_art_path']:
        return jsonify({'error': 'No cover art found'}), 404

    art_path = ctx.project_root / track['cover_art_path']
    if not art_path.exists():
        return jsonify({'error': 'Cover art file missing'}), 404

    # Determine mime type from extension
    ext = art_path.suffix.lower()
    mime = 'image/png' if ext == '.png' else 'image/jpeg'

    # Optional resize via ?size=N
    size_param = request.args.get('size', type=int)
    if size_param and size_param > 0:
        try:
            import io

            from PIL import Image
            img = Image.open(str(art_path))
            img.thumbnail((size_param, size_param))
            buf = io.BytesIO()
            fmt = 'PNG' if ext == '.png' else 'JPEG'
            img.save(buf, format=fmt)
            buf.seek(0)
            return Response(buf.getvalue(), mimetype=mime)
        except Exception:
            pass  # Fall through to serve original

    return send_from_directory(str(art_path.parent), art_path.name,
                               mimetype=mime)


def _crc32_of_file(filepath):
    """Compute CRC32 of a file without loading it entirely into memory."""
    import zlib
    crc = 0
    with open(filepath, 'rb') as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def _streaming_zip(file_entries):
    """Yield ZIP_STORED bytes one file at a time, then central directory.

    Each entry in file_entries is (archive_name: str, file_path: Path).
    Since ZIP_STORED has no compression, sizes and CRC32 are known upfront,
    so local headers are complete before file data is written.
    Memory usage: O(64 KB buffer) regardless of total archive size.
    """
    import struct

    entries = []  # (name_bytes, crc, size, local_header_offset)
    offset = 0

    for archive_name, file_path in file_entries:
        name_bytes = archive_name.encode('utf-8')
        size = file_path.stat().st_size
        crc = _crc32_of_file(file_path)

        # Local file header (30 bytes + filename)
        header = struct.pack(
            '<4sHHHHHIIIHH',
            b'PK\x03\x04',   # signature
            20,               # version needed (2.0)
            0,                # flags
            0,                # compression (stored)
            0,                # mod time
            0,                # mod date
            crc,              # crc-32
            size,             # compressed size
            size,             # uncompressed size
            len(name_bytes),  # filename length
            0,                # extra field length
        ) + name_bytes
        yield header

        # File data in 64 KB chunks
        with open(file_path, 'rb') as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                yield chunk

        entries.append((name_bytes, crc, size, offset))
        offset += len(header) + size

    # Central directory
    cd_offset = offset
    for name_bytes, crc, size, local_offset in entries:
        cd_entry = struct.pack(
            '<4sHHHHHHIIIHHHHHII',
            b'PK\x01\x02',   # signature
            20,               # version made by
            20,               # version needed
            0,                # flags
            0,                # compression
            0,                # mod time
            0,                # mod date
            crc,
            size,             # compressed size
            size,             # uncompressed size
            len(name_bytes),  # filename length
            0,                # extra field length
            0,                # file comment length
            0,                # disk number start
            0,                # internal file attributes
            0,                # external file attributes
            local_offset,     # relative offset of local header
        ) + name_bytes
        yield cd_entry
        offset += len(cd_entry)

    # End of central directory record
    cd_size = offset - cd_offset
    num_entries = len(entries)
    yield struct.pack(
        '<4sHHHHIIH',
        b'PK\x05\x06',  # signature
        0,               # disk number
        0,               # disk with central directory
        num_entries,      # entries on this disk
        num_entries,      # total entries
        cd_size,          # size of central directory
        cd_offset,        # offset of central directory
        0,               # comment length
    )


def _streaming_zip_size(file_entries):
    """Pre-compute the total byte size of a streaming ZIP archive.

    Allows setting Content-Length so download clients can show progress.
    """
    total = 0
    num_files = 0
    for archive_name, file_path in file_entries:
        name_len = len(archive_name.encode('utf-8'))
        size = file_path.stat().st_size
        total += 30 + name_len + size   # local header + data
        total += 46 + name_len          # central directory entry
        num_files += 1
    total += 22  # end of central directory record
    return total, num_files


@api_bp.route('/api/files/<playlist_key>/download-all')
def api_files_download_all(playlist_key):
    """Stream a ZIP archive of all MP3s in a playlist."""
    ctx = _ctx()

    # Get tracks from DB, resolve to flat MP3 dir
    tracks = ctx.track_db.get_tracks_by_playlist(playlist_key)
    if not tracks:
        return jsonify({'error': 'No MP3 files found'}), 404

    mp3_files = []
    display_map = {}
    for t in tracks:
        fpath = ctx.project_root / t['file_path']
        if fpath.exists():
            mp3_files.append(fpath)
            display_map[fpath.name] = _build_display_filename(t)

    if not mp3_files:
        return jsonify({'error': 'No MP3 files found'}), 404

    raw_names = [display_map.get(f.name, f.name) for f in mp3_files]
    deduped = mp.deduplicate_filenames(raw_names)
    file_entries = list(zip(deduped, mp3_files, strict=True))
    content_length, _ = _streaming_zip_size(file_entries)

    zip_name = f"{playlist_key}.zip"
    return Response(
        _streaming_zip(file_entries),
        mimetype='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{zip_name}"',
            'Content-Length': str(content_length),
        },
    )


@api_bp.route('/api/files/download-zip', methods=['POST'])
def api_files_download_zip():
    """Stream a ZIP archive of MP3s from multiple playlists."""
    ctx = _ctx()
    data = request.get_json(silent=True) or {}
    playlists = data.get('playlists', [])
    if not playlists:
        return jsonify({'error': 'playlists array is required'}), 400

    # Collect files per playlist from TrackDB, enforce limit
    playlist_files = []  # [(playlist_key, [Path, ...], {display_map})]
    total_count = 0
    for key in playlists:
        tracks = ctx.track_db.get_tracks_by_playlist(key)
        mp3s = []
        dm = {}
        for t in tracks:
            fpath = ctx.project_root / t['file_path']
            if fpath.exists():
                mp3s.append(fpath)
                dm[fpath.name] = _build_display_filename(t)
        if not mp3s:
            continue
        total_count += len(mp3s)
        if total_count > 2000:
            return jsonify({'error': 'Too many files (limit 2000)'}), 413
        playlist_files.append((key, mp3s, dm))

    if not playlist_files:
        return jsonify({'error': 'No MP3 files found in selected playlists'}), 404

    file_entries = []
    for key, files, dm in playlist_files:
        raw_names = [dm.get(f.name, f.name) for f in files]
        deduped = mp.deduplicate_filenames(raw_names)
        for name, f in zip(deduped, files, strict=True):
            file_entries.append((f'{key}/{name}', f))

    content_length, _ = _streaming_zip_size(file_entries)

    return Response(
        _streaming_zip(file_entries),
        mimetype='application/zip',
        headers={
            'Content-Disposition': 'attachment; filename="music-porter-export.zip"',
            'Content-Length': str(content_length),
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

    # Saved destinations from DB
    for d in ctx.sync_tracker.get_all_destinations():
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
            dest_dict = dest.to_api_dict()
            dest_dict['auto_detected'] = True
            destinations.append(dest_dict)

    return jsonify({'destinations': destinations})


@api_bp.route('/api/sync/destinations', methods=['POST'])
def api_sync_destination_add():
    """Add a saved sync destination.

    Optional ``link_to`` field: name of an existing destination to share
    tracking with (instead of creating independent tracking).
    """
    ctx = _ctx()
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    path = data.get('path', '').strip()
    link_to = (data.get('link_to') or '').strip() or None
    if not name or not path:
        return jsonify({'error': 'name and path are required'}), 400

    # If linking, look up target destination's sync_key
    sync_key = None
    if link_to:
        target = ctx.sync_tracker.get_destination(link_to)
        if not target:
            return jsonify({'error': f"Link target '{link_to}' not found"}), 404
        sync_key = target.sync_key

    ok = ctx.sync_tracker.add_destination(name, path, sync_key=sync_key,
                                          audit_source=ctx.detect_source())
    if not ok:
        return jsonify({'error': f"Failed to add destination '{name}'"}), 400
    dest = ctx.sync_tracker.get_destination(name)
    result = dest.to_api_dict() if dest else {'name': name, 'path': path}
    result['ok'] = True
    return jsonify(result)


@api_bp.route('/api/sync/destinations/<name>', methods=['DELETE'])
def api_sync_destination_delete(name):
    """Remove a saved sync destination."""
    ctx = _ctx()
    ok = ctx.sync_tracker.remove_destination(name)
    if not ok:
        return jsonify({'error': f"Destination '{name}' not found"}), 404
    return jsonify({'ok': True})


@api_bp.route('/api/sync/destinations/<name>/link', methods=['PUT'])
def api_sync_destination_link(name):
    """Link or unlink a destination.

    To link: ``{"destination": "other-dest-name"}``
    To unlink: ``{"destination": null}``
    """
    ctx = _ctx()
    data = request.get_json(force=True)
    target_dest = data.get('destination')

    dest = ctx.sync_tracker.get_destination(name)
    if not dest:
        # Auto-create if caller provides a path (e.g. sync-client first-time)
        path = data.get('path', '').strip()
        if not path:
            return jsonify({'error': f"Destination '{name}' not found"}), 404
        # If linking to existing, resolve its sync_key
        sync_key = None
        if target_dest:
            target = ctx.sync_tracker.get_destination(target_dest)
            if target:
                sync_key = target.sync_key
        ok = ctx.sync_tracker.add_destination(
            name, path, sync_key=sync_key,
            audit_source=ctx.detect_source())
        if not ok:
            return jsonify({'error': f"Failed to create destination '{name}'"}), 400
        created_dest = ctx.sync_tracker.get_destination(name)
        result = created_dest.to_api_dict() if created_dest else {'name': name}
        result['ok'] = True
        result['created'] = True
        return jsonify(result)

    if target_dest:
        ok = ctx.sync_tracker.link_destination(name, target_dest)
    else:
        # Unlinking — create new independent tracking
        ok = ctx.sync_tracker.unlink_destination(name)

    if not ok:
        return jsonify({'error': f"Failed to update destination '{name}'"}), 400

    updated_dest = ctx.sync_tracker.get_destination(name)
    result = updated_dest.to_api_dict() if updated_dest else {'name': name}
    result['ok'] = True
    return jsonify(result)


@api_bp.route('/api/sync/destinations/<name>/rename', methods=['POST'])
def api_sync_destination_rename(name):
    """Rename a saved destination."""
    ctx = _ctx()
    data = request.get_json(force=True) or {}
    new_name = (data.get('new_name') or '').strip()
    if not new_name:
        return jsonify({'error': 'new_name is required'}), 400
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+', new_name):
        return jsonify({'error': 'new_name must be alphanumeric, hyphens, or underscores'}), 400
    if new_name.lower() == name.lower():
        return jsonify({'error': 'new_name must be different from the current name'}), 400

    dest = ctx.sync_tracker.get_destination(name)
    if not dest:
        return jsonify({'error': f"Destination '{name}' not found"}), 404
    if ctx.sync_tracker.get_destination(new_name):
        return jsonify({'error': f"Destination '{new_name}' already exists"}), 409

    ok = ctx.sync_tracker.rename_destination(name, new_name)
    if not ok:
        return jsonify({'error': 'Failed to rename destination'}), 400

    return jsonify({'ok': True, 'old_name': name, 'new_name': new_name})


@api_bp.route('/api/sync/destinations/resolve', methods=['POST'])
def api_sync_destination_resolve():
    """Server-side destination resolution.

    Finds or creates a destination from the provided hints.
    Optional ``link_to`` field: name of an existing destination to share
    tracking with.
    Returns the destination, whether it was created, and sync status.
    """
    ctx = _ctx()
    data = request.get_json(force=True) or {}
    path = (data.get('path') or '').strip() or None
    name = (data.get('name') or '').strip() or None
    drive_name = (data.get('drive_name') or '').strip() or None
    link_to = (data.get('link_to') or '').strip() or None

    if not path and not name:
        return jsonify({'error': 'At least path or name is required'}), 400

    result = ctx.sync_tracker.resolve_destination(
        path=path, name=name, drive_name=drive_name,
        link_to=link_to)
    if not result:
        return jsonify({'error': 'Failed to resolve destination'}), 500

    dest = result['destination']
    response = {
        'destination': dest.to_api_dict(),
        'created': result['created'],
    }

    # Include sync status summary
    status = ctx.sync_tracker.get_destination_status(
        dest.name, mp.get_audio_dir())
    response['sync_status'] = status.to_dict()

    return jsonify(response)


@api_bp.route('/api/sync/run', methods=['POST'])
def api_sync_run():
    """Run sync to a named destination.

    Requires ``profile`` in request body to apply profile-specific tags
    during sync. Source is the flat library/audio/ directory.
    Accepts ``source_dir`` (flat MP3 dir) or ``playlist_key`` to identify
    the playlist for display name resolution.
    """
    ctx = _ctx()
    data = request.get_json(force=True)
    source_dir = data.get('source_dir', mp.get_audio_dir())
    dest_name = data.get('destination', '')
    profile_name = data.get('profile', '')
    dry_run = data.get('dry_run', False)
    verbose = data.get('verbose', False)

    # Resolve playlist keys: prefer playlist_keys list; fall back to
    # legacy playlist_key (single string) for backward compatibility.
    raw_keys = data.get('playlist_keys')
    if raw_keys is None:
        legacy = data.get('playlist_key', '')
        raw_keys = [legacy] if legacy else None
    # Normalise: empty list → None (all playlists)
    playlist_keys = raw_keys if raw_keys else None

    if not dest_name:
        return jsonify({'error': 'destination is required'}), 400

    # Resolve output profile for tagging
    config = ctx.get_config()
    mp.load_output_profiles(config)
    if not profile_name:
        profile_name = config.get_setting('output_type', mp.DEFAULT_OUTPUT_TYPE)
    if profile_name not in mp.OUTPUT_PROFILES:
        return jsonify({'error': f'Unknown profile: {profile_name}'}), 400
    profile = mp.OUTPUT_PROFILES[profile_name]

    # Look up destination from DB
    dest = ctx.sync_tracker.get_destination(dest_name)

    if not dest:
        return jsonify({'error': f"Destination '{dest_name}' not found"}), 404

    if dest.is_web_client:
        return jsonify({'error': 'web-client destinations can only be synced from the browser'}), 400

    # Persist playlist prefs before dispatching (so they survive cancellation)
    ctx.sync_tracker.save_playlist_prefs(dest_name, playlist_keys)

    sync_label = (', '.join(playlist_keys) if playlist_keys else 'all')
    desc = f'Sync: {sync_label} → {dest.name}'

    def _run(task_id):
        logger = ctx.make_logger(task_id, verbose=verbose)
        display = ctx.make_display_handler(task_id)
        task = ctx.task_manager.get(task_id)

        tag_applicator = mp.TagApplicator(ctx.track_db,
                                          project_root=str(ctx.project_root))

        # Resolve playlist display name (first key for single-playlist compat)
        first_key = playlist_keys[0] if playlist_keys else ''
        pl_rec = ctx.playlist_db.get(first_key) if first_key else None
        playlist_name = pl_rec['name'] if pl_rec else first_key

        sync_mgr = mp.SyncManager(logger, display_handler=display,
                                  cancel_event=task.cancel_event,
                                  sync_tracker=ctx.sync_tracker)
        result = sync_mgr.sync_to_destination(
            source_dir, dest_path=dest.path, sync_key=dest.sync_key,
            dry_run=dry_run,
            tag_applicator=tag_applicator, profile=profile,
            playlist_name=playlist_name, playlist_keys=playlist_keys)
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
    """Summary of sync status per destination group.

    Uses TrackDB for total file counts and sync_files table for synced
    counts. Groups destinations that share tracking together.
    """
    ctx = _ctx()
    all_dests = ctx.sync_tracker.get_all_destinations()
    playlist_stats = {
        s['playlist']: s['track_count']
        for s in ctx.track_db.get_playlist_stats()
    }
    total_library_files = sum(playlist_stats.values())

    # Group destinations by sync_key; build per-key dest details map
    key_groups = {}
    dest_details_map = {}
    for d in all_dests:
        key_groups.setdefault(d.sync_key, []).append(d.name)
        dest_details_map.setdefault(d.sync_key, []).append({
            'name': d.name,
            'path': d.path,
            'type': d.type,
            'available': d.available,
        })

    keys = ctx.sync_tracker._get_keys()
    key_meta = {k['key_name']: k for k in keys}

    creation_times = ctx.sync_tracker._get_playlist_creation_times()

    results = []
    for sync_key, dest_names in key_groups.items():
        info = key_meta.get(sync_key)
        last_sync = info['last_sync_at'] if info else 0
        group_name = (info.get('name') or '') if info else ''
        playlist_prefs = info.get('playlist_prefs') if info else None

        # Scope total_files to the group's playlists (prefs or all)
        if playlist_prefs:
            group_total = sum(
                playlist_stats.get(p, 0) for p in playlist_prefs
            )
            scope = set(playlist_prefs)
        else:
            group_total = total_library_files
            scope = set(playlist_stats.keys())

        # Synced count scoped to the same playlists
        synced_counts = ctx.sync_tracker.get_synced_counts(
            sync_key, playlist_prefs
        )
        total_synced = sum(synced_counts.values())

        synced_bytes = ctx.sync_tracker.get_synced_bytes(
            sync_key, playlist_prefs
        )

        # New playlists: created after last sync, within scope
        new_playlists = 0
        if last_sync > 0:
            new_playlists = sum(
                1 for p in scope
                if creation_times.get(p, 0) > last_sync
            )

        results.append({
            'destinations': dest_names,
            'last_sync_at': last_sync,
            'total_files': group_total,
            'synced_files': total_synced,
            'new_files': group_total - total_synced,
            'new_playlists': new_playlists,
            'group_name': group_name,
            'playlist_prefs': playlist_prefs,
            'synced_bytes': synced_bytes,
            'destination_details': dest_details_map.get(sync_key, []),
        })
    return jsonify(results)


@api_bp.route('/api/sync/status/<dest_name>')
def api_sync_status_detail(dest_name):
    """Per-playlist sync breakdown for a destination's group.

    Resolves destination name → internal sync_key → DB-based status.
    Returns status for the entire destination group.
    """
    ctx = _ctx()
    dest = ctx.sync_tracker.get_destination(dest_name)
    if not dest:
        return jsonify({'error': 'Destination not found'}), 404

    sync_key = dest.sync_key
    conn = ctx.sync_tracker._connect()
    try:
        rows = conn.execute(
            "SELECT name FROM destinations WHERE sync_key = ?", (sync_key,)
        ).fetchall()
        group_names = [r['name'] for r in rows]
    finally:
        conn.close()

    playlist_stats = {
        s['playlist']: s['track_count']
        for s in ctx.track_db.get_playlist_stats()
    }
    synced_counts = ctx.sync_tracker.get_synced_counts(sync_key)

    keys = ctx.sync_tracker._get_keys()
    key_info = next((k for k in keys if k['key_name'] == sync_key), None)
    last_sync = key_info['last_sync_at'] if key_info else 0
    playlist_prefs = key_info['playlist_prefs'] if key_info else None
    pref_set = set(playlist_prefs) if playlist_prefs else None

    creation_times = ctx.sync_tracker._get_playlist_creation_times()

    playlists = []
    group_total = 0
    group_synced = 0
    for name, total in sorted(playlist_stats.items()):
        synced = synced_counts.get(name, 0)
        new = total - synced
        in_prefs = pref_set is None or name in pref_set

        if not in_prefs:
            status = 'skipped'
        elif last_sync > 0 and creation_times.get(name, 0) > last_sync:
            status = 'new'
        elif new > 0:
            status = 'behind'
        else:
            status = 'synced'

        playlists.append({
            'name': name,
            'total_files': total,
            'synced_files': synced,
            'new_files': new,
            'is_new_playlist': status == 'new',
            'sync_status': status,
        })

        if in_prefs:
            group_total += total
            group_synced += synced

    new_playlist_count = sum(1 for p in playlists if p['sync_status'] == 'new')

    result = mp.SyncStatusResult(
        destinations=group_names,
        last_sync_at=last_sync,
        playlists=playlists,
        total_files=group_total,
        synced_files=group_synced,
        new_files=group_total - group_synced,
        new_playlists=new_playlist_count,
        playlist_prefs=playlist_prefs,
    )
    return jsonify(result.to_dict())


@api_bp.route('/api/sync/destinations/<name>/reset', methods=['POST'])
def api_sync_destination_reset(name):
    """Reset all sync tracking for a destination's group.

    Deletes all sync_files for the group's sync_key and resets
    last_sync_at to 0. The destination and sync_key remain.
    """
    ctx = _ctx()
    dest = ctx.sync_tracker.get_destination(name)
    if not dest:
        return jsonify({'error': f"Destination '{name}' not found"}), 404

    result = ctx.sync_tracker.reset_destination_tracking(name)
    if ctx.audit_logger:
        ctx.audit_logger.log(
            'sync_destination_reset',
            f"Reset sync tracking for destination '{name}' "
            f"({result['files_cleared']} record(s) cleared)",
            'completed',
            params={'destination': name, **result},
            source=ctx.detect_source(),
        )
    return jsonify(result)


@api_bp.route('/api/sync/destinations/<name>/group-name', methods=['PUT'])
def api_sync_destination_group_name(name):
    """Set (or clear) the human-readable label for a destination's group.

    Body: {"name": "My Group Label"}  (empty string clears the name)
    Returns 404 if destination not found, 400 if body is missing.
    """
    ctx = _ctx()
    data = request.get_json(silent=True)
    if data is None or 'name' not in data:
        return jsonify({'error': "'name' field required"}), 400

    ok = ctx.sync_tracker.set_group_name(name, data['name'])
    if not ok:
        return jsonify({'error': f"Destination '{name}' not found"}), 404

    return jsonify({'ok': True})


@api_bp.route('/api/sync/destinations/<name>/playlist-prefs', methods=['PUT'])
def api_sync_destination_playlist_prefs(name):
    """Persist playlist preferences for a destination's sync group.

    Body: {"playlist_keys": ["key1", "key2"]} or {"playlist_keys": null}
    Passing null (or an empty list) resets to "sync all playlists".
    Returns 404 if destination not found, 400 if body is missing.
    """
    ctx = _ctx()
    data = request.get_json(silent=True)
    if data is None or 'playlist_keys' not in data:
        return jsonify({'error': "'playlist_keys' field required"}), 400

    playlist_keys = data['playlist_keys']
    # Normalise: empty list treated same as null (all playlists)
    if isinstance(playlist_keys, list) and len(playlist_keys) == 0:
        playlist_keys = None

    ok = ctx.sync_tracker.save_playlist_prefs(name, playlist_keys)
    if not ok:
        return jsonify({'error': f"Destination '{name}' not found"}), 404

    return jsonify({'ok': True})


@api_bp.route('/api/sync/client-record', methods=['POST'])
def api_sync_client_record():
    """Record files synced via client-side sync for tracking.

    Client sends a destination name; server resolves it to the
    internal sync_key for recording.
    """
    ctx = _ctx()
    if not ctx.sync_tracker:
        return jsonify({'error': 'Sync tracker not available'}), 400

    data = request.get_json(silent=True) or {}
    dest_name = data.get('destination', '')
    playlist = data.get('playlist', '')
    files = data.get('files', [])

    if not dest_name or not playlist or not files:
        return jsonify({
            'error': 'destination, playlist, and files are required',
        }), 400

    # Resolve destination name → internal sync_key
    dest = ctx.sync_tracker.get_destination(dest_name)
    if not dest:
        # Auto-create destination from path if provided
        dest_path = data.get('dest_path', '').strip()
        if dest_path:
            dest_type = data.get('dest_type', 'folder')
            scheme = 'usb://' if dest_type == 'usb' else 'folder://'
            schemed_path = f'{scheme}{dest_path}'
            link_to = data.get('link_to', '')
            sync_key = None
            if link_to:
                target = ctx.sync_tracker.get_destination(link_to)
                if target:
                    sync_key = target.sync_key
            ctx.sync_tracker.add_destination(
                dest_name, schemed_path, sync_key=sync_key,
                validate_path=False, audit_source=ctx.detect_source())
            dest = ctx.sync_tracker.get_destination(dest_name)
        if not dest:
            return jsonify({
                'error': f"Destination '{dest_name}' not found",
            }), 404

    ctx.sync_tracker.record_batch(dest.sync_key, playlist, files)

    if ctx.audit_logger:
        ctx.audit_logger.log(
            'client_sync_record',
            f"Recorded {len(files)} file(s) for '{playlist}' "
            f"on destination '{dest_name}'",
            'completed',
            params={'destination': dest_name, 'playlist': playlist,
                    'file_count': len(files)},
            source=ctx.detect_source(),
        )

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
# EQ Presets
# ══════════════════════════════════════════════════════════════════


@api_bp.route('/api/eq', methods=['GET'])
def api_eq_list():
    """List all EQ configs, optionally filtered by profile."""
    profile = request.args.get('profile')
    eq_mgr = mp.EQConfigManager()
    if profile:
        configs = eq_mgr.list_eq(profile)
    else:
        configs = eq_mgr.list_all()
    return jsonify({'eq_presets': configs})


@api_bp.route('/api/eq', methods=['POST'])
def api_eq_set():
    """Set EQ config for profile (default) or profile+playlist (override)."""
    ctx = _ctx()
    data = request.get_json(force=True)
    profile = data.get('profile')
    playlist = data.get('playlist')  # None for profile default
    if not profile:
        return jsonify({'error': 'profile is required'}), 400

    eq = mp.EQConfig(
        loudnorm=bool(data.get('loudnorm', False)),
        bass_boost=bool(data.get('bass_boost', False)),
        treble_boost=bool(data.get('treble_boost', False)),
        compressor=bool(data.get('compressor', False)),
    )
    eq_mgr = mp.EQConfigManager()
    eq_mgr.set_eq(profile, eq, playlist)

    # Audit
    source = ctx.detect_source()
    if ctx.audit_logger:
        desc = f"EQ updated: {profile}"
        if playlist:
            desc += f"/{playlist}"
        ctx.audit_logger.log('eq_update', desc, 'completed',
                             params={'profile': profile, 'playlist': playlist,
                                     **eq.to_dict()},
                             source=source)

    return jsonify({'success': True, 'eq': eq.to_dict()})


@api_bp.route('/api/eq', methods=['DELETE'])
def api_eq_delete():
    """Delete EQ config for profile default or playlist override."""
    ctx = _ctx()
    data = request.get_json(force=True)
    profile = data.get('profile')
    playlist = data.get('playlist')
    if not profile:
        return jsonify({'error': 'profile is required'}), 400

    eq_mgr = mp.EQConfigManager()
    eq_mgr.delete_eq(profile, playlist)

    # Audit
    source = ctx.detect_source()
    if ctx.audit_logger:
        desc = f"EQ cleared: {profile}"
        if playlist:
            desc += f"/{playlist}"
        ctx.audit_logger.log('eq_update', desc, 'completed',
                             params={'profile': profile, 'playlist': playlist,
                                     'action': 'delete'},
                             source=source)

    return jsonify({'success': True})


@api_bp.route('/api/eq/resolve', methods=['GET'])
def api_eq_resolve():
    """Resolve the effective EQ config for a profile+playlist combination."""
    profile = request.args.get('profile')
    playlist = request.args.get('playlist')
    if not profile:
        return jsonify({'error': 'profile is required'}), 400

    eq_mgr = mp.EQConfigManager()
    eq = eq_mgr.get_eq(profile, playlist)
    return jsonify({
        'eq': eq.to_dict(),
        'any_enabled': eq.any_enabled,
        'filter_chain': eq.build_filter_chain(),
        'effects': eq.enabled_effects,
    })


@api_bp.route('/api/eq/effects', methods=['GET'])
def api_eq_effects():
    """Return list of available EQ effects with descriptions."""
    return jsonify({'effects': mp.EQ_EFFECTS})


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
