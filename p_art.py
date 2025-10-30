#!/usr/bin/env python3
"""
Plex Poster and Background Filler CLI
Run: python p_art_tui.py

This app allows you to:
- Connect to your Plex server
- Enter API keys for TMDb, Fanart, OMDb
- Load and select libraries to process
- Choose provider priority
- Control overwrite, dry run, rate limits
"""

import os
import re
import json
import time
import logging
import random
import sys
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List
from pathlib import Path
from urllib.parse import urlparse

import requests
from plexapi.server import PlexServer

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- logging ----------
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("plex-art-filler")

# ---------- constants ----------
DEFAULT_TIMEOUT = 12
DEFAULT_MIN_POSTER_WIDTH = 600
DEFAULT_MIN_BACKGROUND_WIDTH = 1920
CONFIG_PATH = Path(".p_art_config.json")

TRUSTED_PROVIDERS = {
    "tmdb", "themoviedb",
    "tvdb", "thetvdb",
    "fanart", "fanart.tv",
    "omdb",
    "trakt",
    "imdb",
    "local", "embedded"
}

CACHE_PATH = Path(".provider_cache.json")
_cache_lock = threading.Lock()
_provider_cache: Dict[str, Dict[str, dict]] = {}

def cache_load(path: Path):
    global _provider_cache
    if path.exists():
        try:
            _provider_cache = json.loads(path.read_text())
            if not isinstance(_provider_cache, dict):
                _provider_cache = {}
        except Exception:
            _provider_cache = {}

def cache_save(path: Path):
    try:
        with _cache_lock:
            path.write_text(json.dumps(_provider_cache))
    except Exception:
        pass

def cache_get(namespace: str, key: str):
    with _cache_lock:
        return _provider_cache.get(namespace, {}).get(key)

def cache_set(namespace: str, key: str, value):
    with _cache_lock:
        _provider_cache.setdefault(namespace, {})[key] = value

# ---------- config persistence ----------
def config_load(path: Path) -> dict:
    """Load saved configuration from file."""
    if path.exists():
        try:
            config = json.loads(path.read_text())
            if isinstance(config, dict):
                return config
        except Exception:
            pass
    return {}

def config_save(path: Path, config: dict):
    """Save configuration to file."""
    try:
        path.write_text(json.dumps(config, indent=2))
    except Exception:
        pass

# ---------- rate limiting ----------
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

def host_of(url: str) -> str:
    return urlparse(url).netloc

limiters = {
    "api.themoviedb.org": RateLimiter(rate_per_sec=2.0),
    "webservice.fanart.tv": RateLimiter(rate_per_sec=1.0),
    "www.omdbapi.com": RateLimiter(rate_per_sec=3.0),
}

session = requests.Session()

def _http_get(url, params=None, headers=None) -> Optional[requests.Response]:
    try:
        return session.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException:
        return None

def safe_get(url, params=None, headers=None) -> Optional[requests.Response]:
    host = host_of(url)
    if host in limiters:
        limiters[host].wait()
    for attempt in range(4):
        r = _http_get(url, params=params, headers=headers)
        if r and r.status_code == 200:
            return r
        retry_after = 0
        if r and r.status_code in (429, 500, 502, 503, 504):
            try:
                retry_after = int(r.headers.get("Retry-After", "0"))
            except Exception:
                retry_after = 0
        sleep_time = max(retry_after, 1) * (1 + 0.25 * random.random()) * (2 ** attempt)
        time.sleep(min(sleep_time, 30))
    return None

@dataclass
class ArtResult:
    poster_url: Optional[str] = None
    background_url: Optional[str] = None
    source: Optional[str] = None

def extract_ids_from_guid(guid: str) -> Dict[str, str]:
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

def resolve_external_ids(item) -> Dict[str, str]:
    ids = {}
    try:
        if item.guid:
            ids.update(extract_ids_from_guid(item.guid))
        for g in getattr(item, "guids", []) or []:
            if getattr(g, "id", None):
                ids.update(extract_ids_from_guid(g.id))
    except Exception:
        pass
    return ids

def pick_best_image(images, min_width):
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

# ---------- Providers ----------
def tmdb_art(api_key: Optional[str], movie_tmdb_id: Optional[str], tv_tmdb_id: Optional[str],
             min_poster_w: int, min_back_w: int) -> ArtResult:
    if not api_key:
        return ArtResult()
    ns = "tmdb_movie" if movie_tmdb_id else "tmdb_tv"
    key = movie_tmdb_id or tv_tmdb_id
    cached = cache_get(ns, key)
    if cached:
        return ArtResult(**cached)
    base = "https://api.themoviedb.org/3"
    headers = {"Accept": "application/json"}
    if movie_tmdb_id:
        r = safe_get(f"{base}/movie/{movie_tmdb_id}/images",
                     params={"api_key": api_key, "include_image_language": "en,null"},
                     headers=headers)
    elif tv_tmdb_id:
        r = safe_get(f"{base}/tv/{tv_tmdb_id}/images",
                     params={"api_key": api_key, "include_image_language": "en,null"},
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
        poster_url=pick_best_image(posters, min_poster_w),
        background_url=pick_best_image(backdrops, min_back_w),
        source="tmdb"
    )
    cache_set(ns, key, res.__dict__)
    return res

def fanart_art(api_key: Optional[str], tmdb_id: Optional[str], tvdb_id: Optional[str],
               min_poster_w: int, min_back_w: int) -> ArtResult:
    if not api_key:
        return ArtResult()
    ns = "fanart_tv" if tvdb_id else "fanart_movie"
    key = tvdb_id or tmdb_id
    cached = cache_get(ns, key)
    if cached:
        return ArtResult(**cached)
    if tvdb_id:
        r = safe_get(f"https://webservice.fanart.tv/v3/tv/{tvdb_id}", params={"api_key": api_key})
    elif tmdb_id:
        r = safe_get(f"https://webservice.fanart.tv/v3/movies/{tmdb_id}", params={"api_key": api_key})
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
        poster_url=pick_best_image(posters, min_poster_w),
        background_url=pick_best_image(backgrounds, min_back_w),
        source="fanart"
    )
    cache_set(ns, key, res.__dict__)
    return res

def omdb_art(api_key: Optional[str], imdb_id: Optional[str]) -> ArtResult:
    if not api_key or not imdb_id:
        return ArtResult()
    ns = "omdb"
    key = imdb_id
    cached = cache_get(ns, key)
    if cached:
        return ArtResult(**cached)
    r = safe_get("https://www.omdbapi.com/", params={"apikey": api_key, "i": imdb_id})
    if not r:
        return ArtResult()
    js = r.json()
    poster = js.get("Poster")
    res = ArtResult(poster_url=poster if poster and poster != "N/A" else None, background_url=None, source="omdb")
    cache_set(ns, key, res.__dict__)
    return res

# ---------- CLI Functions ----------
def get_input(prompt: str, default: str = "") -> str:
    """Get input from user with optional default value."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()

def get_yes_no(prompt: str, default: bool = True) -> bool:
    """Get yes/no input from user."""
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

def connect_to_plex(url: str, token: str) -> Optional[PlexServer]:
    """Connect to Plex server."""
    try:
        # Increase timeout to 120 seconds for slow connections
        plex = PlexServer(url, token, timeout=120)
        print(f"✓ Connected to Plex: {plex.friendlyName}")
        return plex
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return None

def select_libraries(plex: PlexServer) -> List:
    """Let user select which libraries to process."""
    try:
        print("Fetching libraries from Plex (this may take a moment)...")

        # Retry logic for slow connections
        max_retries = 3
        for attempt in range(max_retries):
            try:
                all_sections = plex.library.sections()
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Timeout on attempt {attempt + 1}/{max_retries}, retrying...")
                    time.sleep(2)
                else:
                    raise e

        print(f"Found {len(all_sections)} total sections")

        sections = []
        for s in all_sections:
            section_type = s.type if hasattr(s, 'type') else getattr(s, 'TYPE', None)
            print(f"  - {s.title} (type: {section_type})")
            if section_type in ("movie", "show"):
                sections.append(s)

        if not sections:
            print("\nNo movie or TV libraries found!")
            return []

        print(f"\n{len(sections)} movie/TV libraries available:")
        for i, section in enumerate(sections, 1):
            section_type = section.type if hasattr(section, 'type') else section.TYPE
            print(f"  {i}. {section.title} ({section_type})")

        print("\nEnter library numbers to process (comma-separated, or 'all'):")
        choice = input("> ").strip().lower()

        if choice == 'all':
            return sections

        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            return [sections[i] for i in indices if 0 <= i < len(sections)]
        except (ValueError, IndexError):
            print("Invalid selection, processing all libraries")
            return sections
    except Exception as e:
        print(f"\n✗ Error fetching libraries: {e}")
        print("\nThis might be due to:")
        print("  - Slow network connection")
        print("  - Large Plex library taking time to load")
        print("  - Plex server being overloaded")
        print("\nTry again or check your Plex server status.")
        return []

def process_item(item, tmdb_key: str, fanart_key: str, omdb_key: str,
                 include_backgrounds: bool, overwrite: bool, dry_run: bool,
                 min_poster_w: int, min_back_w: int):
    """Process a single item (movie or show) to fill missing artwork."""
    title = getattr(item, 'title', 'Unknown')

    # Check if we need to process this item
    has_poster = bool(getattr(item, 'thumb', None))
    has_background = bool(getattr(item, 'art', None))

    if not overwrite and has_poster and (not include_backgrounds or has_background):
        log.info(f"  - Skipping '{title}', artwork already present.")
        return

    # Get external IDs
    ids = resolve_external_ids(item)

    # Try providers in order
    result = ArtResult()

    # Try TMDb
    if tmdb_key and ('tmdb' in ids or 'tvdb' in ids):
        log.info(f"  - Checking TMDb for '{title}'...")
        movie_id = ids.get('tmdb') if item.type == 'movie' else None
        tv_id = ids.get('tmdb') if item.type == 'show' else None
        result = tmdb_art(tmdb_key, movie_id, tv_id, min_poster_w, min_back_w)

    # Try Fanart if needed
    if (not result.poster_url or (include_backgrounds and not result.background_url)) and fanart_key:
        log.info(f"  - Checking Fanart.tv for '{title}'...")
        tmdb_id = ids.get('tmdb')
        tvdb_id = ids.get('tvdb')
        fanart_result = fanart_art(fanart_key, tmdb_id, tvdb_id, min_poster_w, min_back_w)
        if not result.poster_url:
            result.poster_url = fanart_result.poster_url
        if include_backgrounds and not result.background_url:
            result.background_url = fanart_result.background_url
        if fanart_result.poster_url or fanart_result.background_url:
            result.source = fanart_result.source

    # Try OMDb if still need poster
    if not result.poster_url and omdb_key and 'imdb' in ids:
        log.info(f"  - Checking OMDb for '{title}'...")
        omdb_result = omdb_art(omdb_key, ids['imdb'])
        if omdb_result.poster_url:
            result.poster_url = omdb_result.poster_url
            result.source = omdb_result.source

    # Apply artwork
    updated = False
    if result.poster_url and (overwrite or not has_poster):
        if dry_run:
            log.info(f"  [DRY RUN] Would set poster from {result.source}: {title}")
        else:
            try:
                item.uploadPoster(url=result.poster_url)
                log.info(f"  ✓ Set poster from {result.source}: {title}")
                updated = True
            except Exception as e:
                log.info(f"  ✗ Failed to set poster for {title}: {e}")

    if include_backgrounds and result.background_url and (overwrite or not has_background):
        if dry_run:
            log.info(f"  [DRY RUN] Would set background from {result.source}: {title}")
        else:
            try:
                item.uploadArt(url=result.background_url)
                log.info(f"  ✓ Set background from {result.source}: {title}")
                updated = True
            except Exception as e:
                log.info(f"  ✗ Failed to set background for {title}: {e}")

    if not updated and not dry_run:
        if not result.poster_url and not result.background_url:
            log.info(f"  - No artwork found for: {title}")

def main():
    """Main CLI interface."""
    print("=" * 60)
    print("Plex Poster and Background Filler")
    print("=" * 60)

    # Load cache
    cache_load(CACHE_PATH)

    # Load saved configuration
    saved_config = config_load(CONFIG_PATH)
    if saved_config and not os.getenv("PLEX_URL"):
        print("\n✓ Loaded saved configuration from previous run")

    # Step 1: Plex connection
    print("\n[Step 1/5] Plex Connection")
    plex_url = os.getenv("PLEX_URL") or get_input("Plex URL", saved_config.get("plex_url", "http://localhost:32400"))
    plex_token = os.getenv("PLEX_TOKEN") or get_input("Plex Token", saved_config.get("plex_token", ""))

    plex = connect_to_plex(plex_url, plex_token)
    if not plex:
        print("\nCannot continue without Plex connection. Exiting.")
        return

    # Step 2: API Keys
    print("\n[Step 2/5] API Keys")
    print("Enter your API keys (press Enter to skip)")
    tmdb_key = os.getenv("TMDB_API_KEY") or get_input("TMDb API Key", saved_config.get("tmdb_key", ""))
    fanart_key = os.getenv("FANART_API_KEY") or get_input("Fanart.tv API Key", saved_config.get("fanart_key", ""))
    omdb_key = os.getenv("OMDB_API_KEY") or get_input("OMDb API Key", saved_config.get("omdb_key", ""))

    if not any([tmdb_key, fanart_key, omdb_key]):
        print("\n⚠ Warning: No API keys provided. Cannot fetch artwork.")
        if not (os.getenv("LIBRARIES") and get_yes_no("Continue anyway?", False)):
            return

    # Step 3: Library selection
    print("\n[Step 3/5] Library Selection")
    
    libraries_env = os.getenv("LIBRARIES")
    if libraries_env:
        all_libraries = plex.library.sections()
        if libraries_env.lower() == 'all':
            libraries = [lib for lib in all_libraries if lib.type in ('movie', 'show')]
        else:
            lib_names = [name.strip() for name in libraries_env.split(',')]
            libraries = [lib for lib in all_libraries if lib.title in lib_names]
    else:
        libraries = select_libraries(plex)

    if not libraries:
        print("No libraries selected. Exiting.")
        return

    print(f"\n✓ Selected {len(libraries)} library/libraries:")
    for lib in libraries:
        print(f"  - {lib.title}")

    # Step 4: Options
    print("\n[Step 4/5] Processing Options")
    include_backgrounds = os.getenv("INCLUDE_BACKGROUNDS", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("INCLUDE_BACKGROUNDS") else get_yes_no("Include backgrounds/art?", saved_config.get("include_backgrounds", True))
    only_missing_env = os.getenv("ONLY_MISSING", "").lower()
    if only_missing_env in ('true', '1', 'y', 'yes'):
        overwrite = False
        print("  - ONLY_MISSING is set, so existing artwork will not be overwritten.")
    else:
        overwrite = os.getenv("OVERWRITE", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("OVERWRITE") else get_yes_no("Overwrite existing artwork?", saved_config.get("overwrite", False))
    dry_run = os.getenv("DRY_RUN", "").lower() in ('true', '1', 'y', 'yes') if os.getenv("DRY_RUN") else get_yes_no("Dry run (don't actually upload)?", saved_config.get("dry_run", True))

    # Save configuration for next run
    config_to_save = {
        "plex_url": plex_url,
        "plex_token": plex_token,
        "tmdb_key": tmdb_key,
        "fanart_key": fanart_key,
        "omdb_key": omdb_key,
        "include_backgrounds": include_backgrounds,
        "overwrite": overwrite,
        "dry_run": dry_run,
    }
    config_save(CONFIG_PATH, config_to_save)
    print(f"\n✓ Configuration saved to {CONFIG_PATH}")

    # Step 5: Process
    print("\n[Step 5/5] Processing")
    print(f"Settings:")
    print(f"  - Include backgrounds: {include_backgrounds}")
    print(f"  - Overwrite existing: {overwrite}")
    print(f"  - Dry run: {dry_run}")
    print()

    if os.getenv("LIBRARIES") or get_yes_no("Start processing?", True):
        print("\nProcessing libraries...\n")
    else:
        print("Cancelled.")
        return

    total_items = 0
    for library in libraries:
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
                process_item(
                    item, tmdb_key, fanart_key, omdb_key,
                    include_backgrounds, overwrite, dry_run,
                    DEFAULT_MIN_POSTER_WIDTH, DEFAULT_MIN_BACKGROUND_WIDTH
                )

        except Exception as e:
            print(f"✗ Error processing library {library.title}: {e}")

    # Save cache
    cache_save(CACHE_PATH)

    print(f"\n{'=' * 60}")
    print(f"Processing complete! Processed {total_items} items.")
    print(f"Cache saved to: {CACHE_PATH}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()