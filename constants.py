"""Constants and enumerations for P-Art."""

from enum import Enum


class ProviderName(str, Enum):
    """Provider names as enum for type safety."""
    TMDB = "tmdb"
    FANART = "fanart"
    OMDB = "omdb"
    TVDB = "tvdb"
    PLEX_UPLOADED = "plex_uploaded"


class MediaType(str, Enum):
    """Plex media types."""
    MOVIE = "movie"
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    COLLECTION = "collection"


class ArtworkType(str, Enum):
    """Types of artwork."""
    POSTER = "poster"
    BACKGROUND = "background"
    BANNER = "banner"
    THUMB = "thumb"


# Default configuration values
DEFAULT_CONFIG = {
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
    "treat_generated_posters_as_missing": False,
    "min_poster_width": 600,
    "min_background_width": 1920,
    "enable_seasons": False,
    "enable_episodes": False,
    "enable_collections": False,
    "backup_artwork": False,
    "webhook_url": "",
    "enable_scheduler": False,
    "schedule_cron": "0 2 * * *",  # 2 AM daily
    "enable_auth": False,
    "auth_username": "admin",
    "auth_password": "",
}

# Boolean configuration keys
BOOL_KEYS = {
    "include_backgrounds",
    "overwrite",
    "dry_run",
    "final_approval",
    "treat_generated_posters_as_missing",
    "enable_seasons",
    "enable_episodes",
    "enable_collections",
    "backup_artwork",
    "enable_scheduler",
    "enable_auth",
}

# API rate limits (requests per second)
RATE_LIMITS = {
    "api.themoviedb.org": 2.0,
    "webservice.fanart.tv": 1.0,
    "www.omdbapi.com": 3.0,
    "api.thetvdb.com": 1.0,
    "api4.thetvdb.com": 1.0,
}

# Daily quota limits for providers
DAILY_QUOTAS = {
    ProviderName.TMDB: 1000,  # TMDb has 1000 requests/day
    ProviderName.OMDB: 1000,  # OMDb free tier
    ProviderName.FANART: None,  # No daily limit
    ProviderName.TVDB: None,  # No daily limit
}

# Provider host mapping
PROVIDER_HOSTS = {
    "api.themoviedb.org": ProviderName.TMDB,
    "webservice.fanart.tv": ProviderName.FANART,
    "www.omdbapi.com": ProviderName.OMDB,
    "api.thetvdb.com": ProviderName.TVDB,
    "api4.thetvdb.com": ProviderName.TVDB,
}

# Aspect ratio preferences
ASPECT_RATIOS = {
    ArtworkType.POSTER: (2, 3),  # 2:3 for posters
    ArtworkType.BACKGROUND: (16, 9),  # 16:9 for backgrounds
    ArtworkType.BANNER: (758, 140),  # ~5.4:1 for banners
}

# Cache settings
CACHE_BATCH_SIZE = 50  # Save cache every N processed items
CACHE_AUTO_SAVE_INTERVAL = 60  # Auto-save cache every 60 seconds

# Cooldown settings
DEFAULT_COOLDOWN = 12 * 3600  # 12 hours for auth failures
RATE_LIMIT_COOLDOWN = 30 * 60  # 30 minutes for rate limits

# Web UI settings
EVENT_BUFFER_SIZE = 200
HEARTBEAT_INTERVAL = 15  # seconds
