"""Tests for spotify_dl.job_state module."""

from spotify_dl.job_state import DownloadJobState, JobStatus


class TestDownloadJobState:
    def test_initial_state_is_idle(self):
        s = DownloadJobState()
        assert s.status == JobStatus.IDLE
        assert not s.running
        assert s.total == 0
        assert s.completed == 0

    def test_start_downloading_sets_running_and_status(self):
        s = DownloadJobState()
        s.start_downloading(10)
        assert s.running
        assert s.status == JobStatus.DOWNLOADING
        assert s.total == 10

    def test_increment_completed(self):
        s = DownloadJobState()
        s.start_downloading(5)
        s.increment_completed()
        s.increment_completed()
        assert s.completed == 2

    def test_increment_skipped(self):
        s = DownloadJobState()
        s.start_downloading(5)
        s.increment_skipped()
        s.increment_skipped()
        s.increment_skipped()
        assert s.skipped == 3

    def test_increment_failed(self):
        s = DownloadJobState()
        s.start_downloading(5)
        s.increment_failed()
        assert s.failed == 1

    def test_current_song_set_get(self):
        s = DownloadJobState()
        s.set_current_song("Artist - Title")
        assert s.current_song == "Artist - Title"

    def test_add_error(self):
        s = DownloadJobState()
        s.add_error("Artist - Song: yt-dlp failed")
        s.add_error("Artist2 - Song2: timeout")
        assert len(s.errors) == 2

    def test_errors_are_limited_to_last_100(self):
        s = DownloadJobState()
        for i in range(150):
            s.add_error(f"error {i}")
        assert len(s.errors) == 100
        assert s.errors[0] == "error 50"
        assert s.errors[-1] == "error 149"

    def test_mark_done(self):
        s = DownloadJobState()
        s.start_downloading(5)
        s.mark_done()
        assert not s.running
        assert s.status == JobStatus.DONE

    def test_mark_error(self):
        s = DownloadJobState()
        s.mark_error("auth failed")
        assert not s.running
        assert s.status == JobStatus.ERROR
        assert "auth failed" in s.errors

    def test_reset(self):
        s = DownloadJobState()
        s.start_downloading(10)
        s.increment_completed()
        s.increment_failed()
        s.add_error("boom")
        s.reset()
        assert s.status == JobStatus.IDLE
        assert s.total == 0
        assert s.errors == []

    def test_to_dict_contains_all_fields(self):
        s = DownloadJobState()
        s.start_downloading(5)
        s.increment_completed()
        s.set_current_song("Test")
        d = s.to_dict()
        assert d["running"] is True
        assert d["total"] == 5
        assert d["completed"] == 1
        assert d["current_song"] == "Test"

    def test_thread_safety_concurrent_increments(self):
        """Verify increments are atomic under thread contention."""
        import threading
        s = DownloadJobState()
        s.start_downloading(1000)

        def inc_all():
            for _ in range(100):
                s.increment_completed()
                s.increment_skipped()
                s.increment_failed()

        threads = [threading.Thread(target=inc_all) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert s.completed == 500
        assert s.skipped == 500
        assert s.failed == 500

    def test_cannot_increment_before_start(self):
        s = DownloadJobState()
        s.increment_completed()
        # Should not raise, but also should not increment above zero
        assert s.completed == 0

    def test_cannot_start_when_running(self):
        s = DownloadJobState()
        s.start_downloading(5)
        # Try to start again
        s.start_downloading(10)
        # Should keep original values
        assert s.total == 5
