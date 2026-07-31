"""Configuration for Spotify Downloader.

Reads from environment variables with sensible defaults.
All values can be overridden via constructor kwargs or env vars.
"""

import os
import sys
from pathlib import Path


class Config:
    """Central configuration with env-var + constructor override chain."""

    def __init__(
        self,
        spotify_client_id: str | None = None,
        spotify_client_secret: str | None = None,
        redirect_uri: str | None = None,
        scope: str | None = None,
        port: int | None = None,
        download_dir: str | None = None,
        cache_dir: str | None = None,
        max_concurrent: int | None = None,
    ):
        self.spotify_client_id = spotify_client_id or os.environ.get(
            "SPOTIFY_CLIENT_ID", ""
        )
        self.spotify_client_secret = spotify_client_secret or os.environ.get(
            "SPOTIFY_CLIENT_SECRET", ""
        )
        self.redirect_uri = redirect_uri or "http://127.0.0.1:5000/callback"
        self.scope = scope or "user-library-read"
        self._port = port if port is not None else 5000
        self._max_concurrent = max_concurrent if max_concurrent is not None else 3
        self._cache_dir_override = cache_dir
        self._download_dir_override = download_dir

    @property
    def port(self) -> int:
        return self._port

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def cache_dir(self) -> Path:
        if self._cache_dir_override:
            return Path(self._cache_dir_override)
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "SpotifyDownloader"
        return Path.home() / ".config" / "spotify-downloader"

    @property
    def download_dir(self) -> Path:
        if self._download_dir_override:
            return Path(self._download_dir_override)
        return Path.home() / "Downloads" / "spotify-music"

    @property
    def query_template(self) -> str:
        return "{artist} - {title} audio"

    def __repr__(self) -> str:
        return (
            f"Config(client_id={'***' if self.spotify_client_id else '???'}, "
            f"port={self.port}, max_concurrent={self.max_concurrent}, "
            f"download_dir={self.download_dir})"
        )
