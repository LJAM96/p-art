from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)
import json
import os
import queue
import threading
import time

from flask_wtf.csrf import CSRFProtect
from health_checks import run_checks
from p_art import PArt
from auth import AuthManager
from scheduler import ArtworkScheduler

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())

# CSRF Protection
csrf = CSRFProtect(app)

# Initialize PArt
part = PArt()

# Initialize authentication
auth_enabled = os.getenv('ENABLE_AUTH', '').lower() in ('true', '1', 'y', 'yes') or part.config.get('enable_auth', False)
auth_username = os.getenv('AUTH_USERNAME') or part.config.get('auth_username', 'admin')
auth_password = os.getenv('AUTH_PASSWORD') or part.config.get('auth_password', '')
auth_manager = AuthManager(enabled=auth_enabled, username=auth_username, password=auth_password)

# Initialize scheduler
scheduler_enabled = os.getenv('ENABLE_SCHEDULER', '').lower() in ('true', '1', 'y', 'yes') or part.config.get('enable_scheduler', False)
schedule_cron = os.getenv('SCHEDULE_CRON') or part.config.get('schedule_cron', '0 2 * * *')
scheduler = ArtworkScheduler(enabled=scheduler_enabled, cron_schedule=schedule_cron)

if scheduler_enabled:
    scheduler.start(lambda: threading.Thread(target=part.run_web, daemon=True).start())

ENV_VAR_MAP = {
    "plex_url": "PLEX_URL",
    "plex_token": "PLEX_TOKEN",
    "libraries": "LIBRARIES",
    "tmdb_key": "TMDB_API_KEY",
    "fanart_key": "FANART_API_KEY",
    "omdb_key": "OMDB_API_KEY",
    "tvdb_key": "TVDB_API_KEY",
    "include_backgrounds": "INCLUDE_BACKGROUNDS",
    "overwrite": "OVERWRITE",
    "dry_run": "DRY_RUN",
    "artwork_language": "ARTWORK_LANGUAGE",
    "provider_priority": "PROVIDER_PRIORITY",
    "final_approval": "FINAL_APPROVAL",
    "treat_generated_posters_as_missing": "TREAT_GENERATED_POSTERS_AS_MISSING",
    "webhook_url": "WEBHOOK_URL",
    "min_poster_width": "MIN_POSTER_WIDTH",
    "min_background_width": "MIN_BACKGROUND_WIDTH",
    "backup_artwork": "BACKUP_ARTWORK",
    "enable_scheduler": "ENABLE_SCHEDULER",
    "schedule_cron": "SCHEDULE_CRON",
}

FIELD_HEALTH_MAP = {
    "plex_url": "plex",
    "plex_token": "plex",
    "tmdb_key": "tmdb",
    "fanart_key": "fanart",
    "omdb_key": "omdb",
    "tvdb_key": "tvdb",
}


def _build_config_items():
    items = []
    for key in PArt.CONFIG_DEFAULTS.keys():
        env_var = ENV_VAR_MAP.get(key, key.upper())
        env_value = os.getenv(env_var)

        if env_value is not None:
            if key in PArt.BOOL_KEYS:
                value = env_value.lower() in ("true", "1", "y", "yes")
            else:
                value = env_value
        else:
            value = part.config.get(key, PArt.CONFIG_DEFAULTS[key])

        items.append(
            {
                "key": key,
                "value": value,
                "is_bool": key in PArt.BOOL_KEYS,
                "disabled": env_value is not None,
                "health_key": FIELD_HEALTH_MAP.get(key),
            }
        )
    return items


@app.route('/')
@auth_manager.requires_auth
def index():
    initial_progress = {"completed": part.progress_done, "total": part.progress_total}
    next_run = scheduler.get_next_run_time() if scheduler_enabled else None
    return render_template(
        'index.html',
        config=part.config.config,
        is_running=part.is_running,
        initial_progress=initial_progress,
        scheduler_enabled=scheduler_enabled,
        next_scheduled_run=next_run
    )


@app.route('/run', methods=['POST'])
@auth_manager.requires_auth
def run():
    part.config.set("final_approval", "final_approval" in request.form)
    part.config.save()
    if part.is_running:
        return redirect(url_for('index'))
    threading.Thread(target=part.run_web, daemon=True).start()
    return redirect(url_for('index'))


@app.route('/stream')
@auth_manager.requires_auth
@csrf.exempt  # Exempt SSE from CSRF
def stream():
    heartbeat_interval = 15

    def generate():
        next_heartbeat = time.time() + heartbeat_interval

        for payload in part.get_recent_events():
            yield f"data: {json.dumps(payload)}\n\n"

        while True:
            timeout = max(0, next_heartbeat - time.time())
            try:
                payload = part.event_queue.get(timeout=timeout)
                yield f"data: {json.dumps(payload)}\n\n"
                next_heartbeat = time.time() + heartbeat_interval
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
                next_heartbeat = time.time() + heartbeat_interval

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(
        stream_with_context(generate()),
        headers=headers,
        mimetype="text/event-stream",
    )


@app.route('/health')
@csrf.exempt
def health():
    return jsonify(run_checks())


@app.route('/approve')
@auth_manager.requires_auth
def approve():
    return render_template('approve.html', changes=part.proposed_changes)


@app.route('/apply_changes', methods=['POST'])
@auth_manager.requires_auth
def apply_changes():
    approved_count = 0
    for i, change in enumerate(part.proposed_changes):
        action = request.form.get(f'action_{i}')
        if action == 'approve':
            item_rating_key = request.form.get(f'item_rating_key_{i}')
            new_poster = request.form.get(f'new_poster_{i}')
            new_background = request.form.get(f'new_background_{i}')
            uploaded_poster_obj = change.get('uploaded_poster_obj')
            uploaded_art_obj = change.get('uploaded_art_obj')
            part.apply_change(item_rating_key, new_poster, new_background,
                            uploaded_poster_obj, uploaded_art_obj)
            approved_count += 1
    part.proposed_changes = []
    part.history_log.log_change(
        item_title=f"Batch approval of {approved_count} items",
        poster_changed=True,
        dry_run=False,
        source="manual_approval"
    )
    return redirect(url_for('approve'))


@app.route('/approve_all', methods=['POST'])
@auth_manager.requires_auth
def approve_all():
    """Approve all pending changes."""
    approved_count = 0
    for change in part.proposed_changes:
        item_rating_key = change.get('item_rating_key')
        new_poster = change.get('new_poster')
        new_background = change.get('new_background')
        uploaded_poster_obj = change.get('uploaded_poster_obj')
        uploaded_art_obj = change.get('uploaded_art_obj')
        if item_rating_key:
            part.apply_change(item_rating_key, new_poster, new_background,
                            uploaded_poster_obj, uploaded_art_obj)
            approved_count += 1
    part.proposed_changes = []
    part.history_log.log_change(
        item_title=f"Batch approval (all): {approved_count} items",
        poster_changed=True,
        dry_run=False,
        source="batch_approval"
    )
    return redirect(url_for('approve'))


@app.route('/decline_all', methods=['POST'])
@auth_manager.requires_auth
def decline_all():
    """Decline all pending changes."""
    declined_count = len(part.proposed_changes)
    part.proposed_changes = []
    part.history_log.log_change(
        item_title=f"Batch decline: {declined_count} items",
        dry_run=True,
        source="batch_decline"
    )
    return redirect(url_for('approve'))


@app.route('/monitoring')
@auth_manager.requires_auth
def monitoring():
    """Health monitoring dashboard."""
    # Get quota usage
    quota_stats = part.quota_tracker.get_all_usage()

    # Get history statistics
    history_stats = part.history_log.get_statistics()

    # Get recent changes
    recent_changes = part.history_log.get_recent_changes(limit=50, skip_dry_run=True)

    return render_template(
        'monitoring.html',
        quota_stats=quota_stats,
        history_stats=history_stats,
        recent_changes=recent_changes,
        scheduler_enabled=scheduler_enabled,
        next_scheduled_run=scheduler.get_next_run_time() if scheduler_enabled else None,
        is_running=part.is_running
    )


@app.route('/config', methods=['GET', 'POST'])
@auth_manager.requires_auth
def config():
    if request.method == 'POST':
        for key in PArt.CONFIG_DEFAULTS.keys():
            env_var = ENV_VAR_MAP.get(key, key.upper())
            # Skip if managed by environment variable
            if os.getenv(env_var):
                continue
            if key in PArt.BOOL_KEYS:
                part.config.set(key, key in request.form)
            else:
                part.config.set(key, request.form.get(key, "").strip())
        part.config.save()

        # Update scheduler if configuration changed
        if scheduler_enabled:
            new_cron = part.config.get('schedule_cron', '0 2 * * *')
            if new_cron != schedule_cron:
                scheduler.reschedule(new_cron)

        return redirect(url_for('config'))

    health_status = run_checks()
    return render_template(
        'config.html',
        config_items=_build_config_items(),
        health_status=health_status,
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
