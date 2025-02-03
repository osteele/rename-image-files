import asyncio
import time

# Rate limiting configuration
INITIAL_BACKOFF = 1.0  # Initial backoff in seconds
MAX_BACKOFF = 60.0  # Maximum backoff in seconds
BACKOFF_FACTOR = 2.0  # Multiply by this after each failure


class RateLimiter:
    """Shared rate limiter with exponential backoff."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._current_backoff = INITIAL_BACKOFF
        self._last_error_time = 0.0
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # Minimum time between requests

    async def before_request(self):
        """Wait appropriate time before making a request."""
        async with self._lock:
            now = time.time()

            # If we're in backoff mode, wait until backoff period is over
            if self._last_error_time > 0:
                time_since_error = now - self._last_error_time
                if time_since_error < self._current_backoff:
                    await asyncio.sleep(self._current_backoff - time_since_error)

            # Ensure minimum interval between requests
            time_since_last_request = now - self._last_request_time
            if time_since_last_request < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - time_since_last_request)

            self._last_request_time = time.time()

    async def on_success(self):
        """Reset backoff on successful request."""
        async with self._lock:
            self._current_backoff = INITIAL_BACKOFF
            self._last_error_time = 0

    async def on_rate_limit(self):
        """Increase backoff on rate limit error."""
        async with self._lock:
            self._last_error_time = time.time()
            self._current_backoff = min(self._current_backoff * BACKOFF_FACTOR, MAX_BACKOFF)
            return self._current_backoff
