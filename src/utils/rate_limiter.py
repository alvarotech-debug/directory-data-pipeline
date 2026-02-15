"""
Adaptive rate limiter with jitter and backoff awareness.

Adjusts request speed dynamically based on server responses,
preventing 429 (Too Many Requests) while maximizing throughput.
"""

import asyncio
import logging
import random
import time


class AdaptiveRateLimiter:
    """
    Rate limiter that adjusts speed based on server responses.

    Starts at configured rate, slows down on 429 responses,
    and gradually speeds back up after successful requests.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        jitter: float = 0.3,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.95,
    ) -> None:
        self.base_interval = 1.0 / requests_per_second
        self.current_interval = self.base_interval
        self.jitter = jitter
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()
        self._consecutive_success: int = 0
        self.logger = logging.getLogger(self.__class__.__name__)

    async def wait(self) -> None:
        """Wait the appropriate interval before next request."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            jitter_amount = random.uniform(0, self.jitter)
            wait_time = self.current_interval + jitter_amount - elapsed

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self._last_request = time.monotonic()

    def report_success(self) -> None:
        """Report a successful request — may speed up."""
        self._consecutive_success += 1
        if self._consecutive_success > 10:
            self.current_interval = max(
                self.base_interval,
                self.current_interval * self.recovery_factor,
            )

    def report_rate_limit(self) -> None:
        """Report a 429 response — slow down."""
        self._consecutive_success = 0
        self.current_interval *= self.backoff_factor
        self.logger.warning(
            "Rate limit hit. Interval increased to %.2fs",
            self.current_interval,
        )

    @property
    def stats(self) -> dict:
        """Current rate limiter state."""
        return {
            "base_interval": self.base_interval,
            "current_interval": self.current_interval,
            "consecutive_success": self._consecutive_success,
        }
