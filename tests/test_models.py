"""Tests for spotify_dl.models module."""

from spotify_dl.models import Track, DownloadResult, DownloadStatus


class TestTrack:
    def test_creates_from_dict(self):
        t = Track(
            id="track-123",
            name="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            track_number=11,
            album_art="http://img.url/cover.jpg",
        )
        assert t.id == "track-123"
        assert t.name == "Bohemian Rhapsody"
        assert t.artist == "Queen"
        assert t.album == "A Night at the Opera"
        assert t.track_number == 11
        assert t.album_art == "http://img.url/cover.jpg"

    def test_dict_roundtrip_preserves_all_fields(self):
        t = Track(
            id="x",
            name="Song",
            artist="Artist",
            album="Album",
            track_number=1,
            album_art="http://x.com/img.jpg",
        )
        d = t.to_dict()
        t2 = Track.from_dict(d)
        assert t2.id == t.id
        assert t2.name == t.name
        assert t2.artist == t.artist
        assert t2.album == t.album
        assert t2.track_number == t.track_number
        assert t2.album_art == t.album_art

    def test_safe_filename_strips_special_chars(self):
        t = Track(id="1", name='Song / With "Special" Chars!?', artist='Artist*:Name<>', album="Album")
        assert "Song  With Special Chars" == t.safe_title
        assert "ArtistName" == t.safe_artist

    def test_output_filename_combines_artist_and_title(self):
        t = Track(id="1", name="Yesterday", artist="Beatles", album="Help")
        assert t.output_filename == "Beatles - Yesterday.mp3"

    def test_output_filename_concatenates_safely(self):
        t = Track(id="1", name="Song/With:Slash?", artist="Bad*Artist", album="Album")
        filename = t.output_filename
        assert filename.endswith(".mp3")
        assert "Bad" in filename
        assert "With" in filename

    def test_temp_filename_uses_track_id(self):
        t = Track(id="abc-123", name="Song", artist="Artist", album="Album")
        assert "abc-123" in t.temp_filename_stem

    def test_cover_temp_filename_uses_track_id(self):
        t = Track(id="xyz-789", name="Song", artist="Artist", album="Album")
        assert "xyz-789" in t.cover_temp_stem
        assert t.cover_temp_stem.endswith(".jpg")


class TestDownloadResult:
    def test_success_result(self):
        r = DownloadResult.success("t1", "Song", "Artist")
        assert r.status == DownloadStatus.SUCCESS
        assert r.track_id == "t1"

    def test_skipped_result(self):
        r = DownloadResult.skipped("t2", "Song", "Artist")
        assert r.status == DownloadStatus.SKIPPED

    def test_failed_result_with_error(self):
        r = DownloadResult.failed("t3", "Song", "Artist", "yt-dlp timeout")
        assert r.status == DownloadStatus.FAILED
        assert r.error == "yt-dlp timeout"

    def test_success_result_to_dict(self):
        r = DownloadResult.success("t1", "Song", "Artist")
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["track_id"] == "t1"

    def test_failed_result_to_dict_includes_error(self):
        r = DownloadResult.failed("t1", "S", "A", "bad thing")
        d = r.to_dict()
        assert d["error"] == "bad thing"
