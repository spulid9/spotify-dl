"""Tests for spotify_dl.cache module."""

import json
import tempfile
from pathlib import Path
from spotify_dl.cache import DownloadCache


class TestDownloadCache:
    def test_load_returns_empty_dict_for_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "nonexistent.json")
            assert cache.all() == {}

    def test_save_and_load_preserves_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            cache = DownloadCache(path)
            cache.set("track-1", {"file": "Artist - Song.mp3", "song": "Song", "artist": "Artist", "album": "Album"})
            assert "track-1" in cache.all()

            # Re-open from disk
            cache2 = DownloadCache(path)
            assert "track-1" in cache2.all()
            assert cache2.all()["track-1"]["song"] == "Song"

    def test_get_returns_none_for_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            assert cache.get("nonexistent") is None

    def test_get_returns_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            cache.set("abc", {"file": "Song.mp3"})
            assert cache.get("abc") == {"file": "Song.mp3"}

    def test_has_track_returns_true_for_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            cache.set("id-1", {"file": "Song.mp3"})
            assert cache.has("id-1")

    def test_has_track_returns_false_for_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            assert not cache.has("missing")

    def test_remove_deletes_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            cache.set("id-x", {"file": "x.mp3"})
            cache.remove("id-x")
            assert not cache.has("id-x")

    def test_bulk_remove_by_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            cache.set("a", {"file": "a.mp3"})
            cache.set("b", {"file": "b.mp3"})
            cache.set("c", {"file": "c.mp3"})
            removed = cache.bulk_remove(["a", "c"])
            assert removed == 2
            assert not cache.has("a")
            assert cache.has("b")
            assert not cache.has("c")

    def test_count_returns_number_of_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            assert cache.count() == 0
            cache.set("a", {"file": "a.mp3"})
            cache.set("b", {"file": "b.mp3"})
            assert cache.count() == 2

    def test_all_returns_shallow_copy_not_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DownloadCache(Path(tmp) / "cache.json")
            cache.set("a", {"file": "a.mp3"})
            data = cache.all()
            data["a"]["file"] = "modified.mp3"
            assert cache.get("a")["file"] == "a.mp3"

    def test_handles_corrupted_cache_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("this is not valid json {{{")
            cache = DownloadCache(path)
            # Should not raise; should return empty
            assert cache.all() == {}

    def test_handles_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"
            path.write_text("")
            cache = DownloadCache(path)
            assert cache.all() == {}
