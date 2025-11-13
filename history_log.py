"""Change history and audit logging for P-Art."""

import sqlite3
import threading
import time
from pathlib import Path
from typing import List, Optional, Dict


class HistoryLog:
    """SQLite-based change history tracker."""

    def __init__(self, db_path: Path = Path(".p_art_history.db")):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """Initialize the database schema."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    item_title TEXT NOT NULL,
                    item_rating_key TEXT,
                    media_type TEXT,
                    poster_changed INTEGER DEFAULT 0,
                    background_changed INTEGER DEFAULT 0,
                    source TEXT,
                    dry_run INTEGER DEFAULT 0,
                    old_poster_url TEXT,
                    new_poster_url TEXT,
                    old_background_url TEXT,
                    new_background_url TEXT
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON changes(timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_item_title ON changes(item_title)
            ''')

            conn.commit()
            conn.close()

    def log_change(self, item_title: str, poster_changed: bool = False,
                   background_changed: bool = False, source: Optional[str] = None,
                   dry_run: bool = False, item_rating_key: Optional[str] = None,
                   media_type: Optional[str] = None, old_poster_url: Optional[str] = None,
                   new_poster_url: Optional[str] = None, old_background_url: Optional[str] = None,
                   new_background_url: Optional[str] = None):
        """Log an artwork change."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO changes (
                    timestamp, item_title, item_rating_key, media_type,
                    poster_changed, background_changed, source, dry_run,
                    old_poster_url, new_poster_url, old_background_url, new_background_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(), item_title, item_rating_key, media_type,
                int(poster_changed), int(background_changed), source, int(dry_run),
                old_poster_url, new_poster_url, old_background_url, new_background_url
            ))

            conn.commit()
            conn.close()

    def get_recent_changes(self, limit: int = 100, skip_dry_run: bool = False) -> List[Dict]:
        """Get recent changes."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = 'SELECT * FROM changes'
            if skip_dry_run:
                query += ' WHERE dry_run = 0'
            query += ' ORDER BY timestamp DESC LIMIT ?'

            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def get_changes_by_item(self, item_title: str) -> List[Dict]:
        """Get all changes for a specific item."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM changes
                WHERE item_title = ?
                ORDER BY timestamp DESC
            ''', (item_title,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def get_changes_in_range(self, start_time: float, end_time: float) -> List[Dict]:
        """Get changes within a time range."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM changes
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp DESC
            ''', (start_time, end_time))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def get_statistics(self) -> Dict:
        """Get overall statistics."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM changes WHERE dry_run = 0')
            total_changes = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM changes WHERE poster_changed = 1 AND dry_run = 0')
            posters_changed = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM changes WHERE background_changed = 1 AND dry_run = 0')
            backgrounds_changed = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(DISTINCT item_title) FROM changes WHERE dry_run = 0')
            unique_items = cursor.fetchone()[0]

            cursor.execute('''
                SELECT source, COUNT(*) as count
                FROM changes
                WHERE dry_run = 0
                GROUP BY source
                ORDER BY count DESC
            ''')
            by_source = {row[0] or "unknown": row[1] for row in cursor.fetchall()}

            conn.close()

            return {
                "total_changes": total_changes,
                "posters_changed": posters_changed,
                "backgrounds_changed": backgrounds_changed,
                "unique_items": unique_items,
                "by_source": by_source,
            }

    def cleanup_old_data(self, days_to_keep: int = 90):
        """Remove history older than specified days."""
        cutoff_time = time.time() - (days_to_keep * 86400)

        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('DELETE FROM changes WHERE timestamp < ?', (cutoff_time,))

            conn.commit()
            conn.close()
