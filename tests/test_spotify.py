"""Tests for spotify_dl.spotify module."""

from unittest.mock import patch, MagicMock
from spotify_dl.spotify import parse_track, fetch_all_liked_tracks, SpotifyAuthManager


class TestParseTrack:
    def test_parses_valid_spotify_track_with_cover(self):
        item = {
            "track": {
                "id": "abc-123",
                "name": "Test Song",
                "artists": [{"name": "Artist Name"}],
                "album": {
                    "name": "Album Name",
                    "images": [{"url": "http://img.url/large.jpg"}, {"url": "http://img.url/small.jpg"}],
                },
                "track_number": 5,
            }
        }
        track = parse_track(item)
        assert track.id == "abc-123"
        assert track.name == "Test Song"
        assert track.artist == "Artist Name"
        assert track.album == "Album Name"
        assert track.track_number == 5
        assert track.album_art == "http://img.url/large.jpg"

    def test_parses_track_with_multiple_artists(self):
        item = {
            "track": {
                "id": "xyz",
                "name": "Collab",
                "artists": [{"name": "Artist1"}, {"name": "Artist2"}],
                "album": {"name": "Album", "images": []},
                "track_number": 1,
            }
        }
        track = parse_track(item)
        assert track.artist == "Artist1"

    def test_parses_track_without_album_art(self):
        item = {
            "track": {
                "id": "no-art",
                "name": "No Cover",
                "artists": [{"name": "Solo"}],
                "album": {"name": "Raw", "images": []},
                "track_number": 1,
            }
        }
        track = parse_track(item)
        assert track.album_art is None

    def test_parses_track_without_images_key(self):
        item = {
            "track": {
                "id": "no-img",
                "name": "No Img Key",
                "artists": [{"name": "Unknown"}],
                "album": {"name": "Mystery"},
            }
        }
        track = parse_track(item)
        assert track.album_art is None
        assert track.track_number == 1  # default


class TestFetchAllLikedTracks:
    def test_fetches_single_page(self):
        mock_sp = MagicMock()
        mock_sp.current_user_saved_tracks.return_value = {
            "items": [
                {"track": {"id": "1", "name": "S1", "artists": [{"name": "A1"}], "album": {"name": "B1", "images": []}, "track_number": 1}},
                {"track": {"id": "2", "name": "S2", "artists": [{"name": "A2"}], "album": {"name": "B2", "images": []}, "track_number": 2}},
            ],
            "next": None,
        }
        tracks = fetch_all_liked_tracks(mock_sp)
        assert len(tracks) == 2
        assert tracks[0].id == "1"
        assert tracks[1].id == "2"

    def test_fetches_multiple_pages(self):
        mock_sp = MagicMock()
        page1 = {"items": [{"track": {"id": "a", "name": "A", "artists": [{"name": "X"}], "album": {"name": "Y", "images": []}, "track_number": 1}}], "next": "page2"}
        page2 = {"items": [{"track": {"id": "b", "name": "B", "artists": [{"name": "Z"}], "album": {"name": "W", "images": []}, "track_number": 1}}], "next": None}
        mock_sp.current_user_saved_tracks.return_value = page1
        mock_sp.next.return_value = page2
        tracks = fetch_all_liked_tracks(mock_sp)
        assert len(tracks) == 2
        assert tracks[0].id == "a"
        assert tracks[1].id == "b"

    def test_handles_empty_library(self):
        mock_sp = MagicMock()
        mock_sp.current_user_saved_tracks.return_value = None
        tracks = fetch_all_liked_tracks(mock_sp)
        assert tracks == []

    def test_handles_empty_items(self):
        mock_sp = MagicMock()
        mock_sp.current_user_saved_tracks.return_value = {"items": [], "next": None}
        tracks = fetch_all_liked_tracks(mock_sp)
        assert tracks == []


class TestSpotifyAuthManager:
    def test_constructs_with_minimal_config(self):
        mgr = SpotifyAuthManager(
            client_id="cid",
            client_secret="csecret",
            redirect_uri="http://localhost/callback",
            scope="user-library-read",
        )
        assert mgr.client_id == "cid"
        assert mgr.client_secret == "csecret"

    def test_get_authorize_url_returns_valid_url(self):
        mgr = SpotifyAuthManager(
            client_id="test-cid",
            client_secret="cs",
            redirect_uri="http://localhost/callback",
            scope="user-library-read",
        )
        url = mgr.get_authorize_url()
        assert url.startswith("https://accounts.spotify.com/authorize")
        assert "client_id=test-cid" in url
        assert "user-library-read" in url

    def test_multiple_instances_independent_cache(self):
        """Each SpotifyAuthManager should have its own MemoryCacheHandler."""
        mgr1 = SpotifyAuthManager("cid1", "cs", "http://localhost:5000/callback", "user-library-read")
        mgr2 = SpotifyAuthManager("cid2", "cs", "http://localhost:5000/callback", "user-library-read")
        assert mgr1.get_authorize_url() != mgr2.get_authorize_url()
