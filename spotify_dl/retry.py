"""Retry decorator — exponential backoff with configurable exception filtering."""

from __future__ import annotations

import time
import logging
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, original: Exception, attempts: int):
        self.original = original
        self.attempts = attempts
        super().__init__(
            f"Retry exhausted after {attempts} attempts. "
            f"Last error: {type(original).__name__}({original})"
        )


def retry(
    max_retries: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    on: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator: retry a function on specified exceptions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for delay after each retry.
        on: Tuple of exception types to catch and retry on.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except on as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise RetryExhaustedError(e, max_retries) from e
                    logger.debug(
                        "Retry %d/%d for %s: %s", attempt + 1, max_retries,
                        func.__name__, e
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            # Unreachable — but satisfy type checker
            raise RetryExhaustedError(
                last_exception or RuntimeError("unknown"),
                max_retries,
            )

        return wrapper  # type: ignore[return-value]
    return decorator
