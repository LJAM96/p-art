"""Shared credential validation helpers for P-Art."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

import requests
from plexapi.exceptions import Unauthorized
from plexapi.server import PlexServer

CONFIG_PATH = Path(".p_art_config.json")


def _load_config() -> Dict[str, object]:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def get_current_value(env_name: str, config_key: str) -> str:
    return _value(env_name, config_key)


def _value(
    env_name: str,
    config_key: str,
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    if overrides and env_name in overrides:
        val = overrides[env_name]
        return val.strip() if isinstance(val, str) else ""

    env_val = os.getenv(env_name)
    if env_val is not None:
        return env_val.strip()
    config = _load_config()
    val = config.get(config_key)
    return val.strip() if isinstance(val, str) else ""


def check_plex(
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    url = _value("PLEX_URL", "plex_url", overrides)
    token = _value("PLEX_TOKEN", "plex_token", overrides)
    if not url or not token:
        return False, "missing url or token"
    try:
        plex = PlexServer(url, token, timeout=30)
        return True, f"connected to {plex.friendlyName}"
    except Unauthorized:
        return False, "token rejected (401)"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_tmdb(
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    key = _value("TMDB_API_KEY", "tmdb_key", overrides)
    if not key:
        return False, "no key"
    resp = requests.get(
        "https://api.themoviedb.org/3/movie/550",
        params={"api_key": key},
        timeout=15,
    )
    if resp.status_code == 200:
        title = resp.json().get("title", "OK")
        return True, f"sample movie fetched ({title})"
    return False, f"status {resp.status_code}: {resp.text[:120]}"


def check_fanart(
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    key = _value("FANART_API_KEY", "fanart_key", overrides)
    if not key:
        return False, "no key"
    resp = requests.get(
        "https://webservice.fanart.tv/v3/movies/550",
        params={"api_key": key},
        timeout=15,
    )
    if resp.status_code == 200:
        return True, "sample artwork fetched"
    return False, f"status {resp.status_code}: {resp.text[:120]}"


def check_omdb(
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    key = _value("OMDB_API_KEY", "omdb_key", overrides)
    if not key:
        return False, "no key"
    resp = requests.get(
        "https://www.omdbapi.com/",
        params={"apikey": key, "i": "tt0137523"},
        timeout=15,
    )
    payload = {}
    msg = ""
    try:
        payload = resp.json()
        msg = payload.get("Error") or payload.get("error") or ""
    except ValueError:
        msg = resp.text[:120]
    if resp.status_code == 200 and payload.get("Response") == "True":
        return True, "sample movie fetched (Fight Club)"
    if "limit" in msg.lower():
        return False, f"rate limited: {msg}"
    return False, f"status {resp.status_code}: {msg or resp.text[:120]}"


def check_tvdb(
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    key = _value("TVDB_API_KEY", "tvdb_key", overrides)
    if not key:
        return False, "no key"
    pin = _value("TVDB_PIN", "tvdb_pin", overrides)
    user_key = _value("TVDB_USER_KEY", "tvdb_user_key", overrides)
    username = _value("TVDB_USERNAME", "tvdb_username", overrides)

    payload_v4 = {"apikey": key}
    if pin:
        payload_v4["pin"] = pin
    resp_v4 = requests.post(
        "https://api4.thetvdb.com/v4/login",
        json=payload_v4,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    try:
        data_v4 = resp_v4.json()
    except ValueError:
        data_v4 = {}
    if resp_v4.status_code == 200 and data_v4.get("data", {}).get("token"):
        return True, "token issued (v4)"

    payload_v3 = {"apikey": key}
    if user_key:
        payload_v3["userkey"] = user_key
    if username:
        payload_v3["username"] = username
    resp_v3 = requests.post(
        "https://api.thetvdb.com/login",
        json=payload_v3,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    try:
        data_v3 = resp_v3.json()
    except ValueError:
        data_v3 = {}
    if resp_v3.status_code == 200 and data_v3.get("token"):
        return True, "token issued (v3)"

    detail = data_v4.get("message") or data_v3.get("Error") or resp_v4.text[:120] or resp_v3.text[:120]
    return False, f"status v4:{resp_v4.status_code}/v3:{resp_v3.status_code}: {detail}"


CHECKS: Dict[
    str,
    Callable[[Optional[Dict[str, Optional[str]]]], Tuple[bool, str]],
] = {
    "plex": check_plex,
    "tmdb": check_tmdb,
    "fanart": check_fanart,
    "omdb": check_omdb,
    "tvdb": check_tvdb,
}


def run_checks(
    include: Optional[Iterable[str] | Dict[str, bool]] = None,
    overrides: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Dict[str, object]]:
    include_map: Optional[Dict[str, bool]]
    if include is None:
        include_map = None
    elif isinstance(include, dict):
        include_map = {name: bool(flag) for name, flag in include.items()}
    else:
        include_map = {name: True for name in include}

    results: Dict[str, Dict[str, object]] = {}
    for name, func in CHECKS.items():
        if include_map and not include_map.get(name, False):
            continue
        ok, detail = func(overrides=overrides)
        results[name] = {"ok": ok, "detail": detail}
    return results
