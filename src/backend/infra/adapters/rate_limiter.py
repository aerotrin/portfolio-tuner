"""Generic thread-safe sliding-window rate limiter."""

from collections import deque
from dataclasses import dataclass
import logging
import threading
import time


logger = logging.getLogger(__name__)


@dataclass
class RateLimiterConfig:
    """
    Args:
        max_per_minute: Maximum requests allowed in any 60-second window.
    """

    max_per_minute: int


class RateLimiter:
    """
    Thread-safe sliding-window rate limiter.

    Tracks timestamps of the last `max_per_minute` requests. When the window
    is full, blocks until the oldest request ages out of the 60-second window.

    `handle_rate_limit` reacts to upstream 429 responses with exponential
    backoff on top of the window constraint.

    Usage::

        limiter = RateLimiter(RateLimiterConfig(max_per_minute=750))
        limiter.acquire_slot()   # blocks until a slot is available
        # ... make HTTP request ...
        if status == 429:
            limiter.handle_rate_limit(retry_after=5, attempt=1)
    """

    def __init__(self, config: RateLimiterConfig) -> None:
        self.cfg = config
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self._backoff_until: float = 0.0

    def acquire_slot(self) -> None:
        """Block until a request slot is available, then consume it."""
        while True:
            with self._lock:
                now = time.monotonic()

                if now < self._backoff_until:
                    sleep_for = self._backoff_until - now
                else:
                    cutoff = now - 60.0
                    while self._timestamps and self._timestamps[0] < cutoff:
                        self._timestamps.popleft()

                    if len(self._timestamps) < self.cfg.max_per_minute:
                        self._timestamps.append(now)
                        return

                    # Window full — sleep until the oldest slot expires
                    sleep_for = (self._timestamps[0] + 60.0) - now + 0.05

                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "RateLimiter window full (%d/%d), sleeping %.2fs",
                            len(self._timestamps),
                            self.cfg.max_per_minute,
                            sleep_for,
                        )

            time.sleep(sleep_for)

    def handle_rate_limit(self, retry_after: int, attempt: int) -> None:
        """
        React to a 429 by imposing an exponential backoff.

        Uses ``max(retry_after, 2) * min(2 ** attempt, 8)`` seconds.
        Never shortens an already-active backoff period.

        Args:
            retry_after: Seconds from the upstream Retry-After header.
            attempt:     Current retry attempt (1-based).
        """
        with self._lock:
            base_backoff = max(retry_after, 2)
            total_backoff = base_backoff * min(2**attempt, 8)
            self._backoff_until = max(self._backoff_until, time.monotonic() + total_backoff)

            logger.warning(
                "RateLimiter: upstream 429, backing off %ds (attempt %d)",
                total_backoff,
                attempt,
            )
