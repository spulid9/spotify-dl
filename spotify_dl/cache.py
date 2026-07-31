"""Download cache — persistent JSON store for tracking downloaded tracks."""

import json
from copy import deepcopy
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DownloadCache:
    """Persistent cache for tracking which tracks have been downloaded.

    Stores a JSON dict mapping track_id -> download metadata.
    Thread-safe for reads; writes use a lock-free atomic file write.
    """

    def __init__(self, path: Path | None = None):
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        """Load cache from disk. Returns empty dict on any corruption."""
        try:
            raw = self._path.read_text(encoding="utf-8")
            if not raw.strip():
                self._data = {}
                return
            self._data = json.loads(raw)
        except (json.JSONDecodeError, OSError, FileNotFoundError) as e:
            logger.warning("Cache file corrupt or unreadable (%s), starting fresh: %s",
                           type(e).__name__, e)
            self._data = {}

    def _save(self) -> None:
        """Write cache to disk atomically via temp file + rename."""
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            logger.error("Failed to save cache: %s", e)

    def all(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of all cached entries."""
        return deepcopy(self._data)

    def get(self, track_id: str) -> dict[str, Any] | None:
        """Get the cached entry for a track, or None."""
        return self._data.get(track_id)

    def has(self, track_id: str) -> bool:
        """Check if a track is in the cache."""
        return track_id in self._data

    def set(self, track_id: str, info: dict[str, Any]) -> None:
        """Store download info for a track."""
        self._data[track_id] = info
        self._save()

    def remove(self, track_id: str) -> None:
        """Remove a single entry from the cache."""
        self._data.pop(track_id, None)
        self._save()

    def bulk_remove(self, track_ids: list[str]) -> int:
        """Remove multiple entries. Returns count of actually removed."""
        count = 0
        for tid in track_ids:
            if tid in self._data:
                del self._data[tid]
                count += 1
        if count:
            self._save()
        return count

    def count(self) -> int:
        """Return the number of cached entries."""
        return len(self._data)
