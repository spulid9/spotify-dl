"""Data models — Track, DownloadResult, DownloadStatus."""

from __future__ import annotations
from enum import Enum


class DownloadStatus(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class Track:
    """Represents a single song to download."""

    __slots__ = ("id", "name", "artist", "album", "track_number", "album_art")

    def __init__(
        self,
        id: str,
        name: str,
        artist: str,
        album: str,
        track_number: int = 1,
        album_art: str | None = None,
    ):
        self.id = id
        self.name = name
        self.artist = artist
        self.album = album
        self.track_number = track_number
        self.album_art = album_art

    @staticmethod
    def _sanitize_filename_component(raw: str) -> str:
        """Keep only alphanumeric, spaces, dots, hyphens, underscores, apostrophes."""
        return "".join(c if c.isalnum() or c in " ._-'" else "" for c in raw).strip()

    @property
    def safe_title(self) -> str:
        return self._sanitize_filename_component(self.name)

    @property
    def safe_artist(self) -> str:
        return self._sanitize_filename_component(self.artist)

    @property
    def output_filename(self) -> str:
        return f"{self.safe_artist} - {self.safe_title}.mp3"

    @property
    def temp_filename_stem(self) -> str:
        return f"__temp_{self.id}"

    @property
    def cover_temp_stem(self) -> str:
        return f"__cover_{self.id}.jpg"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "track_number": self.track_number,
            "album_art": self.album_art,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Track:
        return cls(
            id=d["id"],
            name=d["name"],
            artist=d["artist"],
            album=d["album"],
            track_number=d.get("track_number", 1),
            album_art=d.get("album_art"),
        )

    def __repr__(self) -> str:
        return f'Track(id={self.id!r}, name="{self.name}", artist="{self.artist}")'


class DownloadResult:
    """Result of a single track download attempt."""

    __slots__ = ("track_id", "title", "artist", "status", "error")

    def __init__(
        self,
        status: DownloadStatus,
        track_id: str,
        title: str = "",
        artist: str = "",
        error: str = "",
    ):
        self.status = status
        self.track_id = track_id
        self.title = title
        self.artist = artist
        self.error = error

    @classmethod
    def success(cls, track_id: str, title: str, artist: str) -> DownloadResult:
        return cls(DownloadStatus.SUCCESS, track_id, title=title, artist=artist)

    @classmethod
    def skipped(cls, track_id: str, title: str, artist: str) -> DownloadResult:
        return cls(DownloadStatus.SKIPPED, track_id, title=title, artist=artist)

    @classmethod
    def failed(cls, track_id: str, title: str, artist: str, error: str) -> DownloadResult:
        return cls(DownloadStatus.FAILED, track_id, title=title, artist=artist,
                   error=error)

    def to_dict(self) -> dict:
        d = {
            "status": self.status.value,
            "track_id": self.track_id,
            "title": self.title,
            "artist": self.artist,
        }
        if self.error:
            d["error"] = self.error
        return d

    def __repr__(self) -> str:
        return (f"DownloadResult({self.status.value}, track_id={self.track_id!r}, "
                f'title="{self.title}")')
