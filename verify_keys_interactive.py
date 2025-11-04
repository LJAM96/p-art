#!/usr/bin/env python3
"""Interactive credential tester for P-Art."""

from __future__ import annotations

import sys

from health_checks import get_current_value, run_checks

PROVIDER_PROMPTS = {
    "plex": [
        ("PLEX_URL", "plex_url", "Plex URL"),
        ("PLEX_TOKEN", "plex_token", "Plex Token"),
    ],
    "tmdb": [
        ("TMDB_API_KEY", "tmdb_key", "TMDb API Key"),
    ],
    "fanart": [
        ("FANART_API_KEY", "fanart_key", "Fanart.tv API Key"),
    ],
    "omdb": [
        ("OMDB_API_KEY", "omdb_key", "OMDb API Key"),
    ],
    "tvdb": [
        ("TVDB_API_KEY", "tvdb_key", "TheTVDB API Key"),
        ("TVDB_PIN", "tvdb_pin", "TheTVDB PIN (optional)"),
        ("TVDB_USER_KEY", "tvdb_user_key", "TheTVDB User Key (optional)"),
        ("TVDB_USERNAME", "tvdb_username", "TheTVDB Username (optional)"),
    ],
}

ORDER = ["plex", "tmdb", "fanart", "omdb", "tvdb"]


def _is_secret(env_name: str) -> bool:
    return any(token in env_name for token in ("KEY", "TOKEN"))


def _prompt_value(label: str, env_name: str, default: str) -> str:
    secret = _is_secret(env_name)
    if default:
        if secret:
            hint = "(current value hidden, press Enter to reuse)"
        else:
            hint = f"[{default}]"
    else:
        hint = ""
    display = f"{label} {hint}".strip()
    value = input(f"{display}: ").strip()
    if not value and default:
        return default
    return value


def gather_overrides(choice: str) -> dict:
    overrides: dict = {}
    prompts = PROVIDER_PROMPTS.get(choice, [])
    for env_name, config_key, label in prompts:
        default = get_current_value(env_name, config_key)
        overrides[env_name] = _prompt_value(label, env_name, default)
    return overrides


def run_interactive(choice: str) -> None:
    if choice == "all":
        overrides: dict = {}
        for name in ORDER:
            overrides.update(gather_overrides(name))
        results = run_checks(overrides=overrides)
    else:
        overrides = gather_overrides(choice)
        results = run_checks(include={choice: True}, overrides=overrides)

    failures = [name for name, status in results.items() if not status.get("ok")]
    for name in ORDER:
        if name not in results:
            continue
        status = results[name]
        ok = bool(status.get("ok"))
        detail = status.get("detail", "")
        icon = "OK" if ok else "!!"
        print(f"{icon} {name.upper()}: {detail}")
    if failures:
        print(f"\n{len(failures)} provider(s) failed: {', '.join(failures)}")
    else:
        print("\nAll selected providers look good.")


def main() -> int:
    options = ORDER + ["all"]
    while True:
        print("\nChoose a provider to test:")
        for idx, name in enumerate(options, start=1):
            print(f"  {idx}. {name.capitalize() if name != 'all' else 'All providers'}")
        print("  q. Quit")

        choice = input("> ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return 0

        try:
            index = int(choice) - 1
            if 0 <= index < len(options):
                choice_key = options[index]
            else:
                print("Invalid selection.")
                continue
        except ValueError:
            choice_key = choice

        if choice_key not in options:
            print("Invalid selection.")
            continue

        try:
            run_interactive(choice_key)
        except KeyboardInterrupt:
            print("\nCancelled current test.")
        except Exception as exc:  # pragma: no cover - interactive use only
            print(f"Unexpected error: {exc}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(0)
