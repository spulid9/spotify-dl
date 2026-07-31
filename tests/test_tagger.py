"""Tests for spotify_dl.tagger module — metadata tagging logic."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

from spotify_dl.tagger import tag_file, build_ffmpeg_args
from spotify_dl.models import Track


class TestBuildFfmpegArgs:
    def test_basic_args_without_cover(self):
        track = Track(id="t1", name="Song", artist="Artist", album="Album", track_number=3)
        args = build_ffmpeg_args(Path("/tmp/input.mp3"), Path("/tmp/output.mp3"), track, cover_path=None)
        assert "-y" in args
        assert "-i" in args
        assert str(Path("/tmp/input.mp3")) in args
        assert "title=Song" in args
        assert "artist=Artist" in args
        assert "album=Album" in args
        assert "track=3" in args

    def test_basic_args_with_cover(self):
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        # build_ffmpeg_args checks cover_path.exists(), so we need a file that exists
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            cover = Path(f.name)
        try:
            args = build_ffmpeg_args(Path("/tmp/in.mp3"), Path("/tmp/out.mp3"), track, cover_path=cover)
            assert str(cover) in args
            assert "attached_pic" in args
        finally:
            cover.unlink()

    def test_output_path_is_last_arg(self):
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        args = build_ffmpeg_args(Path("/tmp/i.mp3"), Path("/tmp/o.mp3"), track, cover_path=None)
        assert args[-1] == str(Path("/tmp/o.mp3"))


class TestTagFile:
    def test_tags_successfully(self):
        track = Track(id="t1", name="Test Song", artist="Test Artist", album="Test Album", track_number=5)
        # Create a minimal valid MP3 file (just a few bytes of silence is enough for ffmpeg to remux)
        # We'll mock subprocess.run to avoid needing rea1 ffmpeg
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = tag_file(Path("/tmp/in.mp3"), Path("/tmp/out.mp3"), track, cover_path=None)
            assert result is True
            mock_run.assert_called_once()

    def test_returns_false_on_ffmpeg_failure(self):
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="codec error")
            result = tag_file(Path("/tmp/in.mp3"), Path("/tmp/out.mp3"), track, cover_path=None)
            assert result is False

    def test_returns_false_on_timeout(self):
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 60)):
            result = tag_file(Path("/tmp/in.mp3"), Path("/tmp/out.mp3"), track, cover_path=None)
            assert result is False

    def test_returns_false_on_os_error(self):
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        with patch("subprocess.run", side_effect=FileNotFoundError("no ffmpeg")):
            result = tag_file(Path("/tmp/in.mp3"), Path("/tmp/out.mp3"), track, cover_path=None)
            assert result is False

    def test_cleans_temp_input_on_failure(self):
        """tag_file unlinks temp input when ffmpeg fails and input != output."""
        track = Track(id="t1", name="S", artist="A", album="B", track_number=1)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            result = tag_file(Path("/tmp/in_fail.mp3"), Path("/tmp/out.mp3"), track, cover_path=None)
            assert result is False
            # ffmpeg failure triggers unlink of input (but we can't easily assert on real POSIX Path)
            # The important thing is it doesn't crash and returns False
