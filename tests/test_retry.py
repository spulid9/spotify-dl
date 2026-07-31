"""Tests for spotify_dl.retry module."""

import time
from spotify_dl.retry import retry, RetryExhaustedError


class TestRetry:
    def test_successful_call_returns_result(self):
        @retry(max_retries=3)
        def succeed():
            return "ok"
        assert succeed() == "ok"

    def test_retries_on_exception_and_succeeds(self):
        calls = []

        @retry(max_retries=3, delay=0)
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = flaky()
        assert result == "recovered"
        assert len(calls) == 3

    def test_raises_retry_exhausted_after_max_retries(self):
        @retry(max_retries=2, delay=0)
        def always_fails():
            raise ValueError("persistent error")

        try:
            always_fails()
            assert False, "should have raised"
        except RetryExhaustedError as e:
            assert "ValueError" in str(e)
            assert "persistent error" in str(e)
            assert e.attempts == 2

    def test_retries_only_on_specified_exceptions(self):
        calls = []

        @retry(max_retries=3, delay=0, on=(ValueError,))
        def selective():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("retry me")
            raise TypeError("should not retry")

        try:
            selective()
            assert False
        except TypeError:
            assert len(calls) == 2  # first retried, second not

    def test_delay_between_retries(self):
        """Verify delay is applied between retries."""
        calls = []
        delays = []

        @retry(max_retries=2, delay=0.05)
        def slow_fail():
            calls.append(time.monotonic())
            raise RuntimeError("fail")

        try:
            slow_fail()
        except RetryExhaustedError:
            pass

        # Check delays were applied
        for i in range(1, len(calls)):
            diff = calls[i] - calls[i - 1]
            assert diff >= 0.04, f"expected delay >= 0.04, got {diff}"

    def test_passes_args_and_kwargs_through(self):
        @retry(max_retries=1)
        def with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = with_args(1, 2, c=3)
        assert result == "1-2-3"

    def test_attempts_counter_in_exception(self):
        @retry(max_retries=5, delay=0)
        def fail_all():
            raise RuntimeError("no")

        try:
            fail_all()
        except RetryExhaustedError as e:
            assert e.attempts == 5
