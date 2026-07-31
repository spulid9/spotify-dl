"""Tests for spotify_dl.downloader module."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call, ANY

from spotify_dl.downloader import download_track, run_download_job
from spotify_dl.models import Track, DownloadResult, DownloadStatus
from spotify_dl.cache import DownloadCache


class TestDownloadTrack:
    def test_skips_when_cached_and_file_exists(self, tmp_path):
        track = Track(id="t1", name="Song", artist="Artist", album="Album")
        cache = DownloadCache(tmp_path / "cache.json")
        # Pre-populate cache with matching download_dir
        cache.set("t1", {"file": "Artist - Song.mp3", "song": "Song", "artist": "Artist", "album": "Album"})
        # Create the file to simulate it exists
        (tmp_path / "downloads" / "Artist - Song.mp3").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "downloads" / "Artist - Song.mp3").write_text("fake mp3 data")

        result = download_track(track, cache, download_dir=tmp_path / "downloads")

        assert result.status == DownloadStatus.SKIPPED
        assert result.track_id == "t1"

    def test_skips_when_output_file_already_exists(self, tmp_path):
        track = Track(id="t2", name="Exists", artist="Band", album="LP")
        cache = DownloadCache(tmp_path / "cache.json")
        dl_dir = tmp_path / "downloads"
        dl_dir.mkdir(parents=True)
        (dl_dir / "Band - Exists.mp3").write_text("existing file")

        result = download_track(track, cache, download_dir=dl_dir)
        assert result.status == DownloadStatus.SKIPPED
        # Cache should be updated
        assert cache.has("t2")

    def test_calls_ytdlp_with_correct_query(self):
        track = Track(id="t3", name="Test Song", artist="Test Artist", album="Album")
        cache = DownloadCache()

        with patch("spotify_dl.downloader.subprocess.run") as mock_run, \
             patch("spotify_dl.downloader._find_temp_output", return_value=Path("/tmp/__temp_t3.mp3")), \
             patch("spotify_dl.downloader.tag_file", return_value=True):
            mock_run.return_value = MagicMock(returncode=0)
            # output_path doesn't exist (not cached, not on disk) → download path
            with patch.object(Path, "exists", return_value=False), \
                 patch.object(Path, "unlink"), \
                 patch.object(Path, "mkdir"):
                result = download_track(track, cache, download_dir=Path("/tmp/dl"))

            # Verify yt-dlp was called
            calls = mock_run.call_args_list
            assert any("ytsearch" in str(c) for c in calls)

    def test_returns_failed_when_ytdlp_returns_nonzero(self):
        track = Track(id="t4", name="Impossible", artist="Nobody", album="Nowhere")
        cache = DownloadCache()

        with patch("spotify_dl.downloader.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="no results found")
            with patch("pathlib.Path.glob", return_value=[]):
                result = download_track(track, cache, download_dir=Path("/tmp/dl"))

            assert result.status == DownloadStatus.FAILED
            assert "no results found" in result.error

    def test_includes_track_in_error_on_timeout(self):
        track = Track(id="t5", name="Slow", artist="Turtle", album="Shell")
        cache = DownloadCache()

        with patch("spotify_dl.downloader.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 120)):
            result = download_track(track, cache, download_dir=Path("/tmp/dl"))

            assert result.status == DownloadStatus.FAILED
            assert "timeout" in result.error.lower()

    def test_downloads_and_tags_successfully(self, tmp_path):
        track = Track(id="t6", name="Hit", artist="Star", album="Album", album_art="http://img.url/cover.jpg")
        cache = DownloadCache()
        dl_dir = tmp_path / "dl"
        dl_dir.mkdir()

        output_file = dl_dir / "Star - Hit.mp3"

        def fake_tag_file(input_path, output_path, *args, **kwargs):
            """Simulate ffmpeg writing output, then verify."""
            output_path.write_text("fake audio")
            return True

        with patch("spotify_dl.downloader.subprocess.run") as mock_run, \
             patch("urllib.request.urlretrieve"), \
             patch("spotify_dl.downloader._find_temp_output", return_value=dl_dir / "__temp_t6.mp3"), \
             patch("spotify_dl.downloader.tag_file", side_effect=fake_tag_file):
            mock_run.return_value = MagicMock(returncode=0)
            result = download_track(track, cache, download_dir=dl_dir)

            assert result.status == DownloadStatus.SUCCESS
            assert output_file.exists()
            assert cache.has("t6")
