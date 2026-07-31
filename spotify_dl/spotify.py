"""Spotify client — OAuth, library fetching, track parsing."""

import logging
from typing import Any

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler

from spotify_dl.models import Track

logger = logging.getLogger(__name__)


def parse_track(item: dict[str, Any]) -> Track:
    """Convert a Spotify API track item into our Track model."""
    t = item["track"]
    album = t.get("album", {})
    images = album.get("images", [])
    return Track(
        id=t["id"],
        name=t["name"],
        artist=t["artists"][0]["name"],
        album=album.get("name", ""),
        track_number=t.get("track_number", 1),
        album_art=images[0]["url"] if images else None,
    )


def fetch_all_liked_tracks(sp: spotipy.Spotify) -> list[Track]:
    """Fetch ALL liked songs from the user's library (paginated)."""
    tracks: list[Track] = []
    results = sp.current_user_saved_tracks(limit=50)
    while results:
        for item in results.get("items", []):
            try:
                tracks.append(parse_track(item))
            except (KeyError, IndexError, TypeError) as e:
                logger.warning("Skipping malformed track: %s", e)
        results = sp.next(results) if results and results.get("next") else None
    return tracks


class SpotifyAuthManager:
    """Manages Spotify OAuth flow and client creation."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scope: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scope = scope

    def _make_oauth(self) -> SpotifyOAuth:
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_handler=MemoryCacheHandler(),
        )

    def get_authorize_url(self) -> str:
        return self._make_oauth().get_authorize_url()

    def complete_auth(self, code: str) -> spotipy.Spotify:
        """Exchange auth code for a Spotify client with valid token."""
        oauth = self._make_oauth()
        oauth.get_access_token(code)
        return spotipy.Spotify(auth_manager=oauth)
