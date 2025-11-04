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

from health_checks import run_checks
from p_art import PArt

app = Flask(__name__)
part = PArt()

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
def index():
    initial_progress = {"completed": part.progress_done, "total": part.progress_total}
    return render_template(
        'index.html',
        config=part.config.config,
        is_running=part.is_running,
        initial_progress=initial_progress
    )

@app.route('/run', methods=['POST'])
def run():
    part.config.set("final_approval", "final_approval" in request.form)
    part.config.save()
    if part.is_running:
        return redirect(url_for('index'))
    threading.Thread(target=part.run_web, daemon=True).start()
    return redirect(url_for('index'))

@app.route('/stream')
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
def health():
    return jsonify(run_checks())

@app.route('/approve')
def approve():
    return render_template('approve.html', changes=part.proposed_changes)

@app.route('/apply_changes', methods=['POST'])
def apply_changes():
    for i in range(len(part.proposed_changes)):
        action = request.form.get(f'action_{i}')
        if action == 'approve':
            item_rating_key = request.form.get(f'item_rating_key_{i}')
            new_poster = request.form.get(f'new_poster_{i}')
            new_background = request.form.get(f'new_background_{i}')
            part.apply_change(item_rating_key, new_poster, new_background)
    part.proposed_changes = []
    return redirect(url_for('approve'))

@app.route('/config', methods=['GET', 'POST'])
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
        return redirect(url_for('config'))

    health_status = run_checks()
    return render_template(
        'config.html',
        config_items=_build_config_items(),
        health_status=health_status,
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
