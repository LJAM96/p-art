"""Backup and restore manager for P-Art artwork."""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

log = logging.getLogger("p-art")


@dataclass
class ArtworkBackup:
    """Backup entry for an item's artwork."""
    item_rating_key: str
    item_title: str
    media_type: str
    timestamp: float
    poster_url: Optional[str] = None
    background_url: Optional[str] = None


class BackupManager:
    """Manages artwork backups for restoration."""

    def __init__(self, backup_path: Path = Path(".artwork_backups.json"), enabled: bool = False):
        self.backup_path = backup_path
        self.enabled = enabled
        self._lock = threading.Lock()
        self._backups = self._load()

    def _load(self) -> Dict[str, ArtworkBackup]:
        """Load backups from file."""
        if not self.backup_path.exists():
            return {}

        try:
            data = json.loads(self.backup_path.read_text())
            backups = {}
            for key, value in data.items():
                backups[key] = ArtworkBackup(**value)
            return backups
        except Exception as e:
            log.warning(f"Failed to load artwork backups: {e}")
            return {}

    def save(self):
        """Save backups to file."""
        if not self.enabled:
            return

        try:
            with self._lock:
                data = {key: asdict(backup) for key, backup in self._backups.items()}
                self.backup_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning(f"Failed to save artwork backups: {e}")

    def backup_item(self, item) -> bool:
        """Backup current artwork for an item."""
        if not self.enabled:
            return False

        try:
            rating_key = str(item.ratingKey)
            title = getattr(item, 'title', 'Unknown')
            media_type = getattr(item, 'type', 'unknown')
            poster_url = getattr(item, 'thumbUrl', None)
            background_url = getattr(item, 'artUrl', None)

            import time
            backup = ArtworkBackup(
                item_rating_key=rating_key,
                item_title=title,
                media_type=media_type,
                timestamp=time.time(),
                poster_url=poster_url,
                background_url=background_url
            )

            with self._lock:
                self._backups[rating_key] = backup

            return True
        except Exception as e:
            log.warning(f"Failed to backup artwork for {getattr(item, 'title', 'Unknown')}: {e}")
            return False

    def restore_item(self, plex, item_rating_key: str) -> bool:
        """Restore backed up artwork for an item."""
        if not self.enabled:
            return False

        with self._lock:
            backup = self._backups.get(item_rating_key)

        if not backup:
            log.warning(f"No backup found for item {item_rating_key}")
            return False

        try:
            item = plex.fetchItem(int(item_rating_key))

            if backup.poster_url:
                item.uploadPoster(url=backup.poster_url)
                log.info(f"Restored poster for {backup.item_title}")

            if backup.background_url:
                item.uploadArt(url=backup.background_url)
                log.info(f"Restored background for {backup.item_title}")

            return True
        except Exception as e:
            log.error(f"Failed to restore artwork for {backup.item_title}: {e}")
            return False

    def get_backup(self, item_rating_key: str) -> Optional[ArtworkBackup]:
        """Get backup for a specific item."""
        with self._lock:
            return self._backups.get(item_rating_key)

    def list_backups(self) -> List[ArtworkBackup]:
        """List all backups."""
        with self._lock:
            return list(self._backups.values())

    def remove_backup(self, item_rating_key: str) -> bool:
        """Remove a backup."""
        with self._lock:
            if item_rating_key in self._backups:
                del self._backups[item_rating_key]
                return True
        return False

    def cleanup_old_backups(self, days_to_keep: int = 30):
        """Remove backups older than specified days."""
        import time
        cutoff_time = time.time() - (days_to_keep * 86400)

        with self._lock:
            keys_to_remove = [
                key for key, backup in self._backups.items()
                if backup.timestamp < cutoff_time
            ]
            for key in keys_to_remove:
                del self._backups[key]

        if keys_to_remove:
            log.info(f"Cleaned up {len(keys_to_remove)} old backups")
