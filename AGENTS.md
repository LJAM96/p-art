# Repository Guidelines

P-Art automates Plex artwork updates via a Flask UI and CLI; this guide gets contributors productive quickly.

## Project Structure & Module Organization
- `p_art.py` holds the `PArt` core logic, provider integrations, caching, and CLI workflow.
- `web.py` boots the Flask server and wires template routes for approval flows.
- `templates/` contains Jinja2 HTML views for dashboard, config, and approval screens.
- `Dockerfile` and `docker-compose.yml` define container packaging; `entrypoint.sh` runs `flask run`.
- Runtime state persists in `.p_art_config.json` and `.provider_cache.json` at the repo root.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: create an isolated environment.
- `pip install -r requirements.txt`: install Flask, PlexAPI, and other dependencies.
- `FLASK_APP=web.py flask run --debug`: launch the UI at http://localhost:5000.
- `python p_art.py`: run the interactive CLI to process artwork without the web layer.
- `docker-compose up --build`: smoke-test the containerized stack end-to-end.

## Coding Style & Naming Conventions
- Follow PEP 8: 4-space indentation, snake_case functions, and PascalCase classes (e.g., `PArt`).
- Prefer type hints and early returns; keep provider modules readable with cohesive helpers.
- Store secrets in environment variables; avoid committing `.p_art_config.json` or cache files.

## Testing Guidelines
- Automated tests are not yet in-tree; add new `pytest` suites under `tests/` when contributing features.
- At minimum, run `python p_art.py --dry-run` or exercise the Flask UI against a Plex sandbox before opening a PR.
- For API integrations, mock provider responses to keep tests deterministic.

## Commit & Pull Request Guidelines
- Use Conventional Commits (`feat:`, `fix:`, `docs:`) to match existing history (`git log -5` for examples).
- Keep PRs focused, include configuration or UI screenshots when relevant, and link Plex issue IDs if applicable.
- Describe manual verification steps (CLI, Flask UI, Docker) in the PR body; note any follow-up work.

## Configuration Tips
- Use a `.env` file loaded by `python-dotenv` for local API keys (`TMDB_API_KEY`, `PLEX_TOKEN`, etc.).
- When overriding options via env vars, remember the web UI disables those fields to prevent accidental overrides.
