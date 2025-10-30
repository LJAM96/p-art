from flask import Flask, render_template, request, redirect, url_for
from p_art import PArt

app = Flask(__name__)
part = PArt()

@app.route('/')
def index():
    return render_template('index.html', config=part.config.config)

@app.route('/run', methods=['POST'])
def run():
    part.config.set("final_approval", "final_approval" in request.form)
    part.config.save()
    part.run_web()
    return redirect(url_for('index'))

@app.route('/stream')
def stream():
    def generate():
        while True:
            message = part.web_log_handler.queue.get()
            yield f"data: {message}\n\n"
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
    return redirect(url_for('index'))

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        for key in part.config.config.keys():
            if not os.getenv(key.upper()):
                part.config.set(key, request.form.get(key))
        part.config.save()
        return redirect(url_for('index'))

    return render_template('config.html', config=part.config.config, env_keys=os.environ.keys())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
