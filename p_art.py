import os
import re
import json
import time
import logging
import random
import sys
import threading
import queue
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List
from pathlib import Path
from urllib.parse import urlparse
from collections import deque

class WebLogHandler(logging.Handler):
    def __init__(self, enqueue_callback):
        super().__init__()
        self.enqueue_callback = enqueue_callback

    def emit(self, record):
        message = self.format(record)
        self.enqueue_callback({"type": "log", "message": message})

import requests
from plexapi.server import PlexServer
from plexapi.exceptions import Unauthorized

# ---------- logging ----------
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("p-art")


@dataclass
class ChangeLogEntry:
    title: str
    poster_changed: bool = False
    background_changed: bool = False
    source: Optional[str] = None
    dry_run: bool = False


@dataclass
class ArtResult:
    poster_url: Optional[str] = None
    background_url: Optional[str] = None
    source: Optional[str] = None


class RateLimiter:
    def __init__(self, rate_per_sec: float):
        self.interval = 1.0 / max(rate_per_sec, 0.001)
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            if now < self._next:
                time.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


class Cache:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._cache = self._load()
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Dict[str, dict]]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text())
            except Exception:
                pass
        return {}

    def save(self):
        try:
            with self._lock:
                self.cache_path.write_text(json.dumps(self._cache, indent=2))
        except Exception:
            pass

    def get(self, namespace: str, key: str):
        with self._lock:
            return self._cache.get(namespace, {}).get(key)

    def set(self, namespace: str, key: str, value):
        with self._lock:
            self._cache.setdefault(namespace, {})[key] = value


class Config:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                config = json.loads(self.config_path.read_text())
                if isinstance(config, dict):
                    return config
            except Exception:
                pass
        return {}

    def save(self):
        try:
            self.config_path.write_text(json.dumps(self.config, indent=2))
        except Exception:
            pass

    def ensure_defaults(self, defaults: Dict[str, object]):
        changed = False
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value
                changed = True
        if changed:
            self.save()

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value):
        self.config[key] = value


from abc import ABC, abstractmethod

class Provider(ABC):
    def __init__(self, part: "PArt", api_key: Optional[str]):
        self.part = part
        self.api_key = api_key
        self._cooldown_notified = False

    def _check_cooldown(self, provider_name: str) -> bool:
        on_cooldown, reason, remaining = self.part._provider_on_cooldown(provider_name)
        if on_cooldown:
            if not self._cooldown_notified:
                minutes = max(1, int(remaining // 60) or 1)
                detail = f" ({reason})" if reason else ""
                log.info(f"{provider_name.upper()} provider on cooldown{detail}. Skipping for about {minutes} minute(s).")
                self._cooldown_notified = True
            return True
        self._cooldown_notified = False
        return False

    @abstractmethod
    def get_art(self, item, min_poster_w: int, min_back_w: int) -> ArtResult:
        pass


class TMDbProvider(Provider):
    def get_art(self, item, min_poster_w: int, min_back_w: int) -> ArtResult:
        if not self.api_key:
            return ArtResult()

        if self._check_cooldown("tmdb"):
            return ArtResult()

        ids = self.part._resolve_external_ids(item)
        movie_tmdb_id = ids.get('tmdb') if item.type == 'movie' else None
        tv_tmdb_id = ids.get('tmdb') if item.type == 'show' else None

        ns = "tmdb_movie" if movie_tmdb_id else "tmdb_tv"
        key = movie_tmdb_id or tv_tmdb_id
        cached = self.part.cache.get(ns, key)
        if cached:
            return ArtResult(**cached)

        base = "https://api.themoviedb.org/3"
        headers = {"Accept": "application/json"}
        params = {"api_key": self.api_key, "include_image_language": f"{self.part.artwork_language},en,null"}

        if movie_tmdb_id:
            r = self.part._safe_get(f"{base}/movie/{movie_tmdb_id}/images",
                                 params=params,
                                 headers=headers)
        elif tv_tmdb_id:
            r = self.part._safe_get(f"{base}/tv/{tv_tmdb_id}/images",
                                 params=params,
                                 headers=headers)
        else:
            return ArtResult()

        if not r:
            return ArtResult()

        data = r.json()
        posters = [{"url": f"https://image.tmdb.org/t/p/original{p.get('file_path')}", "width": p.get("width", 0)}
                   for p in data.get("posters", []) if p.get("file_path")]
        backdrops = [{"url": f"https://image.tmdb.org/t/p/original{b.get('file_path')}", "width": b.get("width", 0)}
                     for b in data.get("backdrops", []) if b.get("file_path")]

        res = ArtResult(
            poster_url=self.part._pick_best_image(posters, min_poster_w),
            background_url=self.part._pick_best_image(backdrops, min_back_w),
            source="tmdb"
        )
        self.part.cache.set(ns, key, res.__dict__)
        return res


class FanartProvider(Provider):
    def get_art(self, item, min_poster_w: int, min_back_w: int) -> ArtResult:
        if not self.api_key:
            return ArtResult()

        if self._check_cooldown("fanart"):
            return ArtResult()

        ids = self.part._resolve_external_ids(item)
        tmdb_id = ids.get('tmdb')
        tvdb_id = ids.get('tvdb')

        ns = "fanart_tv" if tvdb_id else "fanart_movie"
        key = tvdb_id or tmdb_id
        cached = self.part.cache.get(ns, key)
        if cached:
            return ArtResult(**cached)

        if tvdb_id:
            r = self.part._safe_get(f"https://webservice.fanart.tv/v3/tv/{tvdb_id}", params={"api_key": self.api_key})
        elif tmdb_id:
            r = self.part._safe_get(f"https://webservice.fanart.tv/v3/movies/{tmdb_id}", params={"api_key": self.api_key})
        else:
            return ArtResult()

        if not r:
            return ArtResult()

        data = r.json()
        poster_sets = (data.get("movieposter", []) or []) + (data.get("tvposter", []) or [])
        bg_sets = (data.get("moviebackground", []) or []) + (data.get("showbackground", []) or []) + (data.get("tvthumb", []) or []) + (data.get("fanart", []) or [])
        posters = [{"url": i.get("url"), "width": int(i.get("width", 0))} for i in poster_sets if i.get("url")]
        backgrounds = [{"url": i.get("url"), "width": int(i.get("width", 0))} for i in bg_sets if i.get("url")]

        res = ArtResult(
            poster_url=self.part._pick_best_image(posters, min_poster_w),
            background_url=self.part._pick_best_image(backgrounds, min_back_w),
            source="fanart"
        )
        self.part.cache.set(ns, key, res.__dict__)
        return res


class OMDbProvider(Provider):
    def __init__(self, part, api_key: Optional[str]):
        super().__init__(part, api_key)

    def get_art(self, item, min_poster_w: int, min_back_w: int) -> ArtResult:
        if not self.api_key:
            return ArtResult()

        if self._check_cooldown("omdb"):
            return ArtResult()

        ids = self.part._resolve_external_ids(item)
        imdb_id = ids.get('imdb')

        if not imdb_id:
            return ArtResult()

        ns = "omdb"
        key = imdb_id
        cached = self.part.cache.get(ns, key)
        if cached:
            return ArtResult(**cached)

        r = self.part._safe_get("https://www.omdbapi.com/", params={"apikey": self.api_key, "i": imdb_id})
        if not r:
            return ArtResult()

        js = r.json()
        poster = js.get("Poster")
        res = ArtResult(poster_url=poster if poster and poster != "N/A" else None, background_url=None, source="omdb")
        self.part.cache.set(ns, key, res.__dict__)
        return res


class TVDbProvider(Provider):
    def get_art(self, item, min_poster_w: int, min_back_w: int) -> ArtResult:
        if not self.api_key or not item.type == 'show':
            return ArtResult()

        if self._check_cooldown("tvdb"):
            return ArtResult()

        ids = self.part._resolve_external_ids(item)
        tvdb_id = ids.get('tvdb')

        if not tvdb_id:
            return ArtResult()

        ns = "tvdb"
        key = tvdb_id
        cached = self.part.cache.get(ns, key)
        if cached:
            return ArtResult(**cached)

        base = "https://api.thetvdb.com"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.api_key}"}

        r = self.part._safe_get(f"{base}/v3/series/{tvdb_id}/images/query", params={"keyType": "poster"}, headers=headers)
        if not r:
            return ArtResult()
        data = r.json()
        posters = []
        if "data" in data:
            for p in data["data"]:
                posters.append({"url": f"{base}/banners/{p['fileName']}", "width": p.get("resolution", "0x0").split('x')[0]})

        r = self.part._safe_get(f"{base}/v3/series/{tvdb_id}/images/query", params={"keyType": "fanart"}, headers=headers)
        if not r:
            return ArtResult()
        data = r.json()
        backgrounds = []
        if "data" in data:
            for b in data["data"]:
                backgrounds.append({"url": f"{base}/banners/{b['fileName']}", "width": b.get("resolution", "0x0").split('x')[0]})

        res = ArtResult(
            poster_url=self.part._pick_best_image(posters, min_poster_w),
            background_url=self.part._pick_best_image(backgrounds, min_back_w),
            source="tvdb"
        )
        self.part.cache.set(ns, key, res.__dict__)
        return res


class PArt:
    CONFIG_DEFAULTS = {
        "plex_url": "",
        "plex_token": "",
        "libraries": "all",
        "tmdb_key": "",
        "fanart_key": "",
        "omdb_key": "",
        "tvdb_key": "",
        "include_backgrounds": True,
        "overwrite": False,
        "dry_run": True,
        "artwork_language": "en",
        "provider_priority": "tmdb,fanart,omdb",
        "final_approval": False,
    }

    BOOL_KEYS = {"include_backgrounds", "overwrite", "dry_run", "final_approval"}

    def __init__(self):
        self.config = Config(Path(".p_art_config.json"))
        self.config.ensure_defaults(self.CONFIG_DEFAULTS)
        self.cache = Cache(Path(".provider_cache.json"))
        self.plex: Optional[PlexServer] = None
        self.session = requests.Session()
        self.limiters = {
            "api.themoviedb.org": RateLimiter(rate_per_sec=2.0),
            "webservice.fanart.tv": RateLimiter(rate_per_sec=1.0),
            "www.omdbapi.com": RateLimiter(rate_per_sec=3.0),
            "api.thetvdb.com": RateLimiter(rate_per_sec=1.0),
            "api4.thetvdb.com": RateLimiter(rate_per_sec=1.0),
        }
        self._provider_hosts = {
            "api.themoviedb.org": "tmdb",
            "webservice.fanart.tv": "fanart",
            "www.omdbapi.com": "omdb",
            "api.thetvdb.com": "tvdb",
            "api4.thetvdb.com": "tvdb",
        }
        self._change_log: List[ChangeLogEntry] = []
        self.proposed_changes: List[Dict] = []

        self._event_queue = queue.Queue()
        self._event_buffer = deque(maxlen=200)
        self._event_lock = threading.Lock()
        self._cooldown_lock = threading.Lock()
        self._provider_cooldowns: Dict[str, Tuple[float, Optional[str]]] = {}
        self.web_log_handler = WebLogHandler(self._enqueue_event)
        log.addHandler(self.web_log_handler)
        self.event_queue = self._event_queue

        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        log.setLevel(log_level)

        log_file = os.getenv("LOG_FILE")
        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            log.addHandler(handler)

        self.progress_total = 0
        self.progress_done = 0
        self.is_running = False

    def _enqueue_event(self, payload: Dict[str, object]):
        with self._event_lock:
            self._event_buffer.append(payload)
        self._event_queue.put(payload)

    def get_recent_events(self) -> List[Dict[str, object]]:
        with self._event_lock:
            return list(self._event_buffer)

    def _reset_progress(self, total: int):
        self.progress_total = total
        self.progress_done = 0
        self._enqueue_event({"type": "progress", "completed": self.progress_done, "total": self.progress_total})

    def _increment_progress(self, step: int = 1):
        self.progress_done = min(self.progress_total, self.progress_done + step)
        self._enqueue_event({"type": "progress", "completed": self.progress_done, "total": self.progress_total})

    def _set_status(self, state: str):
        self._enqueue_event({"type": "status", "state": state})

    def _set_provider_cooldown(self, provider: str, seconds: float, reason: Optional[str] = None):
        if seconds <= 0:
            return
        cooldown_until = time.time() + seconds
        with self._cooldown_lock:
            current = self._provider_cooldowns.get(provider)
            if current and current[0] >= cooldown_until:
                return
            self._provider_cooldowns[provider] = (cooldown_until, reason)
        minutes = max(1, int(seconds // 60) or 1)
        detail = f": {reason}" if reason else ""
        log.warning(f"{provider.upper()} provider rate limited{detail}. Cooling down for about {minutes} minute(s).")

    def _provider_on_cooldown(self, provider: str) -> Tuple[bool, Optional[str], float]:
        with self._cooldown_lock:
            info = self._provider_cooldowns.get(provider)
            if not info:
                return False, None, 0.0
            until, reason = info
            remaining = until - time.time()
            if remaining <= 0:
                self._provider_cooldowns.pop(provider, None)
                return False, None, 0.0
        return True, reason, max(0.0, remaining)

    def _host_of(self, url: str) -> str:
        return urlparse(url).netloc

    def _safe_get(self, url, params=None, headers=None) -> Optional[requests.Response]:
        host = self._host_of(url)
        if host in self.limiters:
            self.limiters[host].wait()
        for attempt in range(4):
            try:
                log.debug(f"Requesting: {url}")
                r = self.session.get(url, params=params, headers=headers, timeout=12)
                log.debug(f"Response: {r.status_code}")
                if r and r.status_code == 200:
                    return r
                error_detail = ""
                payload = None
                if r:
                    try:
                        payload = r.json()
                    except ValueError:
                        payload = None
                    if isinstance(payload, dict):
                        error_detail = (
                            payload.get("status_message")
                            or payload.get("status")
                            or payload.get("message")
                            or payload.get("Error")
                            or payload.get("error")
                            or ""
                        )
                    if not error_detail and r.text:
                        error_detail = r.text.strip()[:200]

                provider_name = self._provider_hosts.get(host)
                if r and provider_name:
                    lower = (error_detail or "").lower()
                    if r.status_code == 429 or ("limit" in lower and ("rate" in lower or "request" in lower)):
                        retry_after_hint = 30 * 60  # default cooldown 30 minutes
                        try:
                            retry_after_hint = int(r.headers.get("Retry-After", retry_after_hint))
                        except (TypeError, ValueError):
                            pass
                        reason = error_detail or f"HTTP {r.status_code}"
                        self._set_provider_cooldown(provider_name, retry_after_hint, reason)
                        log.warning(f"{provider_name.upper()} provider rate limited: {reason}")
                        return None
                    if r.status_code in (401, 403):
                        detail = error_detail or f"HTTP {r.status_code}"
                        self._set_provider_cooldown(provider_name, 12 * 3600, detail)
                        log.error(f"{provider_name.upper()} provider unauthorized; further requests disabled for this run. Detail: {detail}")
                        return None
                retry_after = 0
                if r and r.status_code in (429, 500, 502, 503, 504):
                    try:
                        retry_after = int(r.headers.get("Retry-After", "0"))
                    except Exception:
                        retry_after = 0
                sleep_time = max(retry_after, 1) * (1 + 0.25 * random.random()) * (2 ** attempt)
                log.warning(f"Request to {url} failed with status {r.status_code}. Retrying in {sleep_time:.2f} seconds.")
                time.sleep(min(sleep_time, 30))
            except requests.RequestException as e:
                log.error(f"Request to {url} failed: {e}")
                pass
        return None

    def _resolve_external_ids(self, item) -> Dict[str, str]:
        ids = {}
        try:
            if item.guid:
                ids.update(self._extract_ids_from_guid(item.guid))
            for g in getattr(item, "guids", []) or []:
                if getattr(g, "id", None):
                    ids.update(self._extract_ids_from_guid(g.id))
        except Exception:
            pass
        return ids

    def _extract_ids_from_guid(self, guid: str) -> Dict[str, str]:
        ids = {}
        if "themoviedb" in guid:
            m = re.search(r"themoviedb://(\d+)", guid)
            if m:
                ids["tmdb"] = m.group(1)
        if "thetvdb" in guid:
            m = re.search(r"thetvdb://(\d+)", guid)
            if m:
                ids["tvdb"] = m.group(1)
        if "imdb" in guid:
            m = re.search(r"imdb://(tt\d+)", guid)
            if m:
                ids["imdb"] = m.group(1)
        return ids

    def _pick_best_image(self, images, min_width):
        best = None
        best_w = 0
        for img in images or []:
            w = img.get("width") or img.get("w") or img.get("size") or 0
            if isinstance(w, str):
                try:
                    w = int(w)
                except ValueError:
                    w = 0
            url = img.get("url") or img.get("source") or img.get("link") or img.get("image")
            if not url:
                continue
            if w >= min_width and w > best_w:
                best = url
                best_w = w
        return best

    def _get_processing_options(self):
        print("\n[Step 4/5] Processing Options")
        self.include_backgrounds = os.getenv("INCLUDE_BACKGROUNDS", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("INCLUDE_BACKGROUNDS") else self._get_yes_no("Include backgrounds/art?", self.config.get("include_backgrounds", True))
        only_missing_env = os.getenv("ONLY_MISSING", "").lower()
        if only_missing_env in ('true', '1', 'y', 'yes'):
            self.overwrite = False
            print("  - ONLY_MISSING is set, so existing artwork will not be overwritten.")
        else:
            self.overwrite = os.getenv("OVERWRITE", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("OVERWRITE") else self._get_yes_no("Overwrite existing artwork?", self.config.get("overwrite", False))
        self.dry_run = os.getenv("DRY_RUN", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("DRY_RUN") else self._get_yes_no("Dry run (don't actually upload)?", self.config.get("dry_run", True))
        self.artwork_language = os.getenv("ARTWORK_LANGUAGE") or self._get_input("Artwork Language (e.g., en, fr, de)", self.config.get("artwork_language", "en"))

        self.config.set("include_backgrounds", self.include_backgrounds)
        self.config.set("overwrite", self.overwrite)
        self.config.set("dry_run", self.dry_run)
        self.config.set("artwork_language", self.artwork_language)
        self.config.save()

        print(f"\n✓ Configuration saved to {self.config.config_path}")

        self._get_providers()

    def _get_providers(self):
        self.providers = {}
        if self.tmdb_key:
            self.providers['tmdb'] = TMDbProvider(self, self.tmdb_key)
        if self.fanart_key:
            self.providers['fanart'] = FanartProvider(self, self.fanart_key)
        if self.omdb_key:
            self.providers['omdb'] = OMDbProvider(self, self.omdb_key)
        if self.tvdb_key:
            self.providers['tvdb'] = TVDbProvider(self, self.tvdb_key)

    def run(self):
        print("=" * 60)
        print("Plex Poster and Background Filler")
        print("=" * 60)

        if self.config.config and not os.getenv("PLEX_URL"):
            print("\n✓ Loaded saved configuration from previous run")

        if not self._connect_to_plex(interactive=True):
            return

        self._change_log = []
        self.proposed_changes = []

        self._get_api_keys()
        self._select_libraries()
        self._get_processing_options()

        provider_priority_str = os.getenv("PROVIDER_PRIORITY") or "tmdb,fanart,omdb"
        self.provider_priority = [p.strip() for p in provider_priority_str.split(',')]

        print("\n[Step 5/5] Processing")
        print(f"Settings:")
        print(f"  - Include backgrounds: {self.include_backgrounds}")
        print(f"  - Overwrite existing: {self.overwrite}")
        print(f"  - Dry run: {self.dry_run}")
        print(f"  - Provider priority: {self.provider_priority}")
        print()

        if os.getenv("LIBRARIES") or self._get_yes_no("Start processing?", True):
            print("\nProcessing libraries...\n")
        else:
            print("Cancelled.")
            return

        total_items = 0
        for library in self.libraries:
            print(f"\n{'=' * 60}")
            print(f"Processing: {library.title}")
            print(f"{'=' * 60}")

            try:
                items = library.all()
                item_count = len(items)
                print(f"Found {item_count} items\n")

                for i, item in enumerate(items):
                    total_items += 1
                    log.info(f"-> Processing {i + 1}/{item_count}: {item.title}")
                    self._process_item(item)

            except Exception as e:
                print(f"✗ Error processing library {library.title}: {e}")

        self.cache.save()

        print(f"\n{'=' * 60}")
        print(f"Processing complete! Processed {total_items} items.")
        print(f"Cache saved to: {self.cache.cache_path}")

    def run_web(self):
        if self.is_running:
            log.warning("Artwork update already in progress. Ignoring new request.")
            return

        log.info("Starting artwork update from web UI...")
        self.is_running = True
        self._set_status("running")
        self._change_log = []
        self.proposed_changes = []
        self._reset_progress(0)

        try:
            if not self._connect_to_plex(interactive=False):
                return

            self._get_api_keys_from_config()
            self._get_libraries_from_config()
            if not getattr(self, "libraries", None):
                log.error("No Plex libraries configured. Update cancelled.")
                return

            self._get_processing_options_from_config()
            self._get_providers()

            provider_priority_str = os.getenv("PROVIDER_PRIORITY") or self.config.get("provider_priority", "tmdb,fanart,omdb")
            self.provider_priority = [p.strip() for p in provider_priority_str.split(',') if p.strip()]
            if not self.provider_priority:
                self.provider_priority = list(self.providers.keys())

            library_batches = []
            total_items = 0
            for library in self.libraries:
                try:
                    items = library.all()
                    item_count = len(items)
                    total_items += item_count
                    library_batches.append((library, items))
                except Exception as e:
                    log.error(f"Error fetching items from {library.title}: {e}")

            self._reset_progress(total_items)

            if total_items == 0:
                log.info("No media items found to process.")
                return

            if not self.providers:
                log.warning("No artwork providers are configured; skipping artwork lookup.")

            for library, items in library_batches:
                item_count = len(items)
                log.info(f"Processing: {library.title}")
                log.info(f"Found {item_count} items")

                for i, item in enumerate(items):
                    log.info(f"-> Processing {i + 1}/{item_count}: {item.title}")
                    self._process_item(item)
                    self._increment_progress()

            self.cache.save()
            log.info("Artwork update finished.")
        finally:
            self.is_running = False
            self._set_status("idle")

    def _get_api_keys_from_config(self):
        self.tmdb_key = os.getenv("TMDB_API_KEY") or self.config.get("tmdb_key", "")
        self.fanart_key = os.getenv("FANART_API_KEY") or self.config.get("fanart_key", "")
        self.omdb_key = os.getenv("OMDB_API_KEY") or self.config.get("omdb_key", "")
        self.tvdb_key = os.getenv("TVDB_API_KEY") or self.config.get("tvdb_key", "")

    def _get_libraries_from_config(self):
        libraries_env = os.getenv("LIBRARIES") or self.config.get("libraries", "all")
        all_libraries = self.plex.library.sections()
        if libraries_env.lower() == 'all':
            self.libraries = [lib for lib in all_libraries if lib.type in ('movie', 'show')]
        else:
            lib_names = [name.strip() for name in libraries_env.split(',')]
            self.libraries = [lib for lib in all_libraries if lib.title in lib_names]
            missing = [name for name in lib_names if name and name not in [lib.title for lib in self.libraries]]
            if missing:
                log.warning(f"Could not find the following libraries: {', '.join(missing)}")

        if not self.libraries:
            log.error("No matching Plex libraries were resolved from configuration.")

    def _get_processing_options_from_config(self):
        include_backgrounds_env = os.getenv("INCLUDE_BACKGROUNDS")
        self.include_backgrounds = include_backgrounds_env.lower() in ('true', '1', 'y', 'yes') if include_backgrounds_env else self.config.get("include_backgrounds", True)
        
        only_missing_env = os.getenv("ONLY_MISSING")
        if only_missing_env and only_missing_env.lower() in ('true', '1', 'y', 'yes'):
            self.overwrite = False
        else:
            overwrite_env = os.getenv("OVERWRITE")
            self.overwrite = overwrite_env.lower() in ('true', '1', 'y', 'yes') if overwrite_env else self.config.get("overwrite", False)
        
        dry_run_env = os.getenv("DRY_RUN")
        self.dry_run = dry_run_env.lower() in ('true', '1', 'y', 'yes') if dry_run_env else self.config.get("dry_run", True)
        
        self.artwork_language = os.getenv("ARTWORK_LANGUAGE") or self.config.get("artwork_language", "en")
        self.final_approval = self.config.get("final_approval", False)

    def apply_change(self, item_rating_key: str, new_poster: Optional[str], new_background: Optional[str]):
        try:
            item = self.plex.fetchItem(int(item_rating_key))
            if new_poster:
                item.uploadPoster(url=new_poster)
                log.info(f"Set poster for {item.title}")
            if new_background:
                item.uploadArt(url=new_background)
                log.info(f"Set background for {item.title}")
        except Exception as e:
            log.error(f"Failed to apply change for item {item_rating_key}: {e}")

        if self._change_log:
            print(f"\nSummary of changes ({len(self._change_log)} items):")
            for entry in self._change_log:
                status = "[DRY RUN]" if entry.dry_run else "[CHANGED]"
                poster_status = "Poster" if entry.poster_changed else ""
                background_status = "Background" if entry.background_changed else ""
                artwork_type = ", ".join(filter(None, [poster_status, background_status]))
                if artwork_type:
                    print(f"  {status} {entry.title}: {artwork_type} from {entry.source}")
                else:
                    print(f"  {status} {entry.title}: No artwork updated (already present or not found)")
        else:
            print("\nNo artwork changes were made.")

        print(f"{'=' * 60}")

    def _process_item(self, item):
        title = getattr(item, 'title', 'Unknown')

        has_poster = bool(getattr(item, 'thumb', None))
        has_background = bool(getattr(item, 'art', None))

        if not self.overwrite and has_poster and (not self.include_backgrounds or has_background):
            log.info(f"  - Skipping '{title}', artwork already present.")
            return

        result = ArtResult()

        for provider_name in self.provider_priority:
            if provider_name in self.providers:
                log.info(f"  - Checking {provider_name} for '{title}'...")
                provider = self.providers[provider_name]
                provider_result = provider.get_art(item, 600, 1920) # TODO: make min widths configurable

                if not result.poster_url:
                    result.poster_url = provider_result.poster_url
                if self.include_backgrounds and not result.background_url:
                    result.background_url = provider_result.background_url
                if provider_result.poster_url or provider_result.background_url:
                    result.source = provider_result.source

            if result.poster_url and (not self.include_backgrounds or result.background_url):
                break

        if self.final_approval:
            if result.poster_url and (self.overwrite or not has_poster):
                self.proposed_changes.append({
                    "item_rating_key": item.ratingKey,
                    "title": title,
                    "current_poster": item.thumbUrl,
                    "new_poster": result.poster_url,
                    "source": result.source
                })
            if self.include_backgrounds and result.background_url and (self.overwrite or not has_background):
                self.proposed_changes.append({
                    "item_rating_key": item.ratingKey,
                    "title": title,
                    "current_background": item.artUrl,
                    "new_background": result.background_url,
                    "source": result.source
                })
            return

        updated = False
        if result.poster_url and (self.overwrite or not has_poster):
            if self.dry_run:
                log.info(f"  [DRY RUN] Would set poster from {result.source}: {title}")
            else:
                try:
                    item.uploadPoster(url=result.poster_url)
                    log.info(f"  ✓ Set poster from {result.source}: {title}")
                    updated = True
                except Exception as e:
                    log.info(f"  ✗ Failed to set poster for {title}: {e}")

        if self.include_backgrounds and result.background_url and (self.overwrite or not has_background):
            if self.dry_run:
                log.info(f"  [DRY RUN] Would set background from {result.source}: {title}")
            else:
                try:
                    item.uploadArt(url=result.background_url)
                    log.info(f"  ✓ Set background from {result.source}: {title}")
                    updated = True
                except Exception as e:
                    log.info(f"  ✗ Failed to set background for {title}: {e}")

        if not updated and not self.dry_run:
            if not result.poster_url and not result.background_url:
                log.info(f"  - No artwork found for: {title}")

        if updated or (self.dry_run and (result.poster_url or result.background_url)):
            self._change_log.append(ChangeLogEntry(
                title=title,
                poster_changed=bool(result.poster_url and (self.overwrite or not has_poster)),
                background_changed=bool(self.include_backgrounds and result.background_url and (self.overwrite or not has_background)),
                source=result.source,
                dry_run=self.dry_run
            ))

    def _get_api_keys(self):
        print("\n[Step 2/5] API Keys")
        print("Enter your API keys (press Enter to skip)")
        self.tmdb_key = os.getenv("TMDB_API_KEY") or self._get_input("TMDb API Key", self.config.get("tmdb_key", ""))
        self.fanart_key = os.getenv("FANART_API_KEY") or self._get_input("Fanart.tv API Key", self.config.get("fanart_key", ""))
        self.omdb_key = os.getenv("OMDB_API_KEY") or self._get_input("OMDb API Key", self.config.get("omdb_key", ""))
        self.tvdb_key = os.getenv("TVDB_API_KEY") or self._get_input("TheTVDB API Key", self.config.get("tvdb_key", ""))

        self.config.set("tmdb_key", self.tmdb_key)
        self.config.set("fanart_key", self.fanart_key)
        self.config.set("omdb_key", self.omdb_key)
        self.config.set("tvdb_key", self.tvdb_key)
        self.config.save()

        if not any([self.tmdb_key, self.fanart_key, self.omdb_key, self.tvdb_key]):
            print("\n⚠ Warning: No API keys provided. Cannot fetch artwork.")

    def _select_libraries(self):
        print("\n[Step 3/5] Library Selection")
        
        libraries_env = os.getenv("LIBRARIES")
        if libraries_env:
            all_libraries = self.plex.library.sections()
            if libraries_env.lower() == 'all':
                self.libraries = [lib for lib in all_libraries if lib.type in ('movie', 'show')]
            else:
                lib_names = [name.strip() for name in libraries_env.split(',')]
                self.libraries = [lib for lib in all_libraries if lib.title in lib_names]
            
            if not self.libraries:
                print(f"Could not find the specified libraries: {libraries_env}. Falling back to manual selection.")
                self._manual_library_selection()
        else:
            self._manual_library_selection()

        if not self.libraries:
            print("No libraries selected. Exiting.")
            sys.exit()

        print(f"\n✓ Selected {len(self.libraries)} library/libraries:")
        for lib in self.libraries:
            print(f"  - {lib.title}")

    def _manual_library_selection(self):
        try:
            print("Fetching libraries from Plex (this may take a moment)...")
            all_sections = self.plex.library.sections()
            sections = [s for s in all_sections if s.type in ("movie", "show")]

            if not sections:
                print("\nNo movie or TV libraries found!")
                self.libraries = []
                return

            print(f"\n{len(sections)} movie/TV libraries available:")
            for i, section in enumerate(sections, 1):
                print(f"  {i}. {section.title} ({section.type})")

            print("\nEnter library numbers to process (comma-separated, or 'all'):")
            choice = input("> ").strip().lower()

            if choice == 'all':
                self.libraries = sections
            else:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                self.libraries = [sections[i] for i in indices if 0 <= i < len(sections)]
        except Exception as e:
            print(f"\n✗ Error fetching libraries: {e}")
            self.libraries = []

    def _connect_to_plex(self, interactive: bool = True) -> bool:
        if interactive:
            print("\n[Step 1/5] Plex Connection")

        default_url = self.config.get("plex_url", "http://localhost:32400")
        default_token = self.config.get("plex_token", "")
        plex_url = os.getenv("PLEX_URL") or default_url
        plex_token = os.getenv("PLEX_TOKEN") or default_token

        if interactive:
            plex_url = os.getenv("PLEX_URL") or self._get_input("Plex URL", plex_url)
            plex_token = os.getenv("PLEX_TOKEN") or self._get_input("Plex Token", plex_token)

        if not plex_url or not plex_token:
            if interactive:
                print("\nCannot continue without Plex connection. Exiting.")
            else:
                log.error("Cannot start artwork update: Plex URL or token is missing. Set them in the Configuration page.")
            self.plex = None
            return False

        try:
            self.plex = PlexServer(plex_url, plex_token, timeout=120)
            log.info(f"Connected to Plex: {self.plex.friendlyName}")
            self.config.set("plex_url", plex_url)
            self.config.set("plex_token", plex_token)
            self.config.save()
            return True
        except Unauthorized:
            log.error("Plex connection failed: Invalid token.")
        except Exception as e:
            log.error(f"Plex connection failed: {e}")

        self.plex = None
        if interactive:
            print("\nCannot continue without Plex connection. Exiting.")
        return False

    def _get_input(self, prompt: str, default: str = "") -> str:
        if default:
            user_input = input(f"{prompt} [{default}]: ").strip()
            return user_input if user_input else default
        return input(f"{prompt}: ").strip()

    def _get_yes_no(self, prompt: str, default: bool = True) -> bool:
        default_str = "Y/n" if default else "y/N"
        while True:
            response = input(f"{prompt} [{default_str}]: ").strip().lower()
            if not response:
                return default
            if response in ['y', 'yes']:
                return True
            if response in ['n', 'no']:
                return False
            print("Please enter 'y' or 'n'")


if __name__ == "__main__":
    app = PArt()
    app.run()
