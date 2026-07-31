"""Tests for spotify_dl.config module."""

import os
import sys
from pathlib import Path
from spotify_dl.config import Config


class TestConfig:
    def test_loads_client_id_from_env(self, monkeypatch):
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-id-123")
        cfg = Config()
        assert cfg.spotify_client_id == "test-id-123"

    def test_loads_client_secret_from_env(self, monkeypatch):
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret-456")
        cfg = Config()
        assert cfg.spotify_client_secret == "test-secret-456"

    def test_loads_client_id_from_init_arg(self):
        cfg = Config(spotify_client_id="explicit-id")
        assert cfg.spotify_client_id == "explicit-id"

    def test_init_arg_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env-id")
        cfg = Config(spotify_client_id="arg-id")
        assert cfg.spotify_client_id == "arg-id"

    def test_redirect_uri_defaults_to_localhost(self):
        cfg = Config()
        assert cfg.redirect_uri == "http://127.0.0.1:5000/callback"

    def test_scope_is_user_library_read(self):
        cfg = Config()
        assert cfg.scope == "user-library-read"

    def test_concurrent_downloads_default(self):
        cfg = Config()
        assert cfg.max_concurrent == 3

    def test_concurrent_downloads_custom(self):
        cfg = Config(max_concurrent=5)
        assert cfg.max_concurrent == 5

    def test_download_dir_default_is_home_downloads_spotify(self, monkeypatch):
        monkeypatch.setattr("spotify_dl.config.Path.home", lambda: __import__("pathlib").Path("/fake/home"))
        cfg = Config()
        assert cfg.download_dir.name == "spotify-music"
        assert "Downloads" in str(cfg.download_dir)

    def test_cache_dir_default_is_config_spotify_downloader(self, monkeypatch):
        monkeypatch.setattr("spotify_dl.config.Path.home", lambda: __import__("pathlib").Path("/fake/home"))
        cfg = Config()
        if sys.platform == "win32":
            assert "SpotifyDownloader" in str(cfg.cache_dir)
        else:
            assert ".config/spotify-downloader" in str(cfg.cache_dir)

    def test_download_dir_custom(self, monkeypatch):
        monkeypatch.setattr("spotify_dl.config.Path.home", lambda: __import__("pathlib").Path("/fake/home"))
        cfg = Config(download_dir="/custom/downloads")
        assert cfg.download_dir == Path("/custom/downloads")

    def test_cache_dir_custom(self):
        cfg = Config(cache_dir="/custom/cache")
        assert cfg.cache_dir == Path("/custom/cache")

    def test_port_override(self):
        cfg = Config(port=8080)
        assert cfg.port == 8080

    def test_youtube_search_query_format(self):
        """query_template should be format-able with artist and title."""
        cfg = Config()
        query = cfg.query_template.format(artist="Radiohead", title="Creep")
        assert "Radiohead" in query
        assert "Creep" in query

    def test_config_repr_shows_keys(self):
        cfg = Config()
        r = repr(cfg)
        assert "Config(" in r
        assert "port=" in r
