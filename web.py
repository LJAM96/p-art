from flask import Flask, render_template, request, redirect, url_for
import os
import threading
import json
from p_art import PArt

app = Flask(__name__)
part = PArt()


def _build_config_items():
    items = []
    # Map config keys to their environment variable names
    env_var_map = {
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
    }
    
    for key in PArt.CONFIG_DEFAULTS.keys():
        env_var = env_var_map.get(key, key.upper())
        env_value = os.getenv(env_var)
        
        # Use environment variable value if available, otherwise use config
        if env_value is not None:
            if key in PArt.BOOL_KEYS:
                value = env_value.lower() in ('true', '1', 'y', 'yes')
            else:
                value = env_value
        else:
            value = part.config.get(key, PArt.CONFIG_DEFAULTS[key])
        
        items.append({
            "key": key,
            "value": value,
            "is_bool": key in PArt.BOOL_KEYS,
            "disabled": env_value is not None,
        })
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
    def generate():
        for payload in part.get_recent_events():
            yield f"data: {json.dumps(payload)}\n\n"
        while True:
            payload = part.event_queue.get()
            yield f"data: {json.dumps(payload)}\n\n"
    return app.response_class(generate(), mimetype='text/event-stream')

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
        # Map config keys to their environment variable names
        env_var_map = {
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
        }
        
        for key in PArt.CONFIG_DEFAULTS.keys():
            env_var = env_var_map.get(key, key.upper())
            # Skip if managed by environment variable
            if os.getenv(env_var):
                continue
            if key in PArt.BOOL_KEYS:
                part.config.set(key, key in request.form)
            else:
                part.config.set(key, request.form.get(key, "").strip())
        part.config.save()
        return redirect(url_for('config'))

    return render_template('config.html', config_items=_build_config_items())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
