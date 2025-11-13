"""API quota tracking for P-Art providers."""

import json
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from constants import DAILY_QUOTAS, ProviderName


class QuotaTracker:
    """Tracks daily API quota usage for providers."""

    def __init__(self, quota_path: Path = Path(".quota_tracker.json")):
        self.quota_path = quota_path
        self._lock = threading.Lock()
        self._quotas = self._load()

    def _load(self) -> Dict[str, Dict[str, int]]:
        """Load quota data from file."""
        if self.quota_path.exists():
            try:
                data = json.loads(self.quota_path.read_text())
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def save(self):
        """Save quota data to file."""
        try:
            with self._lock:
                self.quota_path.write_text(json.dumps(self._quotas, indent=2))
        except Exception:
            pass

    def _get_date_key(self) -> str:
        """Get current date key (YYYY-MM-DD)."""
        return time.strftime("%Y-%m-%d")

    def _get_provider_data(self, provider: str) -> Dict[str, int]:
        """Get today's data for a provider."""
        date_key = self._get_date_key()
        with self._lock:
            if provider not in self._quotas:
                self._quotas[provider] = {}
            if date_key not in self._quotas[provider]:
                self._quotas[provider][date_key] = 0
            return {date_key: self._quotas[provider][date_key]}

    def increment(self, provider: str, count: int = 1):
        """Increment request count for a provider."""
        date_key = self._get_date_key()
        with self._lock:
            if provider not in self._quotas:
                self._quotas[provider] = {}
            if date_key not in self._quotas[provider]:
                self._quotas[provider][date_key] = 0
            self._quotas[provider][date_key] += count

    def get_usage(self, provider: str) -> int:
        """Get today's usage for a provider."""
        date_key = self._get_date_key()
        with self._lock:
            return self._quotas.get(provider, {}).get(date_key, 0)

    def get_remaining(self, provider: str) -> Optional[int]:
        """Get remaining quota for a provider. Returns None if unlimited."""
        if provider not in DAILY_QUOTAS:
            return None

        limit = DAILY_QUOTAS.get(provider)
        if limit is None:
            return None

        usage = self.get_usage(provider)
        return max(0, limit - usage)

    def is_quota_exceeded(self, provider: str) -> bool:
        """Check if quota is exceeded for a provider."""
        remaining = self.get_remaining(provider)
        if remaining is None:
            return False
        return remaining <= 0

    def get_all_usage(self) -> Dict[str, Dict[str, int]]:
        """Get usage stats for all providers."""
        date_key = self._get_date_key()
        stats = {}
        with self._lock:
            for provider in ProviderName:
                usage = self._quotas.get(provider.value, {}).get(date_key, 0)
                limit = DAILY_QUOTAS.get(provider)
                stats[provider.value] = {
                    "usage": usage,
                    "limit": limit,
                    "remaining": None if limit is None else max(0, limit - usage),
                }
        return stats

    def cleanup_old_data(self, days_to_keep: int = 7):
        """Remove quota data older than specified days."""
        cutoff_time = time.time() - (days_to_keep * 86400)
        cutoff_date = time.strftime("%Y-%m-%d", time.localtime(cutoff_time))

        with self._lock:
            for provider in list(self._quotas.keys()):
                dates_to_remove = [
                    date for date in self._quotas[provider].keys()
                    if date < cutoff_date
                ]
                for date in dates_to_remove:
                    del self._quotas[provider][date]

                # Remove empty provider entries
                if not self._quotas[provider]:
                    del self._quotas[provider]
