"""Download job state — thread-safe tracking of download progress."""

import threading
import copy
from enum import Enum


class JobStatus(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    READY = "ready"
    DOWNLOADING = "downloading"
    DONE = "done"
    ERROR = "error"


class DownloadJobState:
    """Thread-safe mutable state for tracking a download batch.

    Uses a reentrant lock so multiple threads can update counters safely.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._status = JobStatus.IDLE
        self._running = False
        self._total = 0
        self._completed = 0
        self._skipped = 0
        self._failed = 0
        self._current_song = ""
        self._errors: list[str] = []
        self._tracks: list = []
        self._max_errors = 100

    # ── Read-only accessors ──────────────────────────────────────────

    @property
    def status(self) -> JobStatus:
        return self._status

    @property
    def running(self) -> bool:
        return self._running

    @property
    def total(self) -> int:
        return self._total

    @property
    def completed(self) -> int:
        return self._completed

    @property
    def skipped(self) -> int:
        return self._skipped

    @property
    def failed(self) -> int:
        return self._failed

    @property
    def current_song(self) -> str:
        return self._current_song

    @property
    def errors(self) -> list[str]:
        with self._lock:
            return list(self._errors)

    @property
    def tracks(self) -> list:
        with self._lock:
            return list(self._tracks)

    # ── Mutators ─────────────────────────────────────────────────────

    def set_tracks(self, tracks: list) -> None:
        with self._lock:
            self._tracks = list(tracks)

    def start_downloading(self, total: int) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._status = JobStatus.DOWNLOADING
            self._total = total
            self._completed = 0
            self._skipped = 0
            self._failed = 0
            self._errors = []

    def set_current_song(self, text: str) -> None:
        with self._lock:
            self._current_song = text

    def increment_completed(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._completed += 1

    def increment_skipped(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._skipped += 1

    def increment_failed(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._failed += 1

    def add_error(self, msg: str) -> None:
        with self._lock:
            self._errors.append(msg)
            if len(self._errors) > self._max_errors:
                self._errors = self._errors[-self._max_errors:]

    def mark_done(self) -> None:
        with self._lock:
            self._running = False
            self._status = JobStatus.DONE
            self._current_song = ""

    def mark_error(self, msg: str) -> None:
        with self._lock:
            self._running = False
            self._status = JobStatus.ERROR
            self._errors.append(msg)

    def reset(self) -> None:
        with self._lock:
            self._status = JobStatus.IDLE
            self._running = False
            self._total = 0
            self._completed = 0
            self._skipped = 0
            self._failed = 0
            self._current_song = ""
            self._errors = []

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "status": self._status.value,
                "total": self._total,
                "completed": self._completed,
                "skipped": self._skipped,
                "failed": self._failed,
                "current_song": self._current_song,
                "errors": self._errors[-10:],
            }
