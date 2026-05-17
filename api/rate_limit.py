"""Async sliding-window rate limiter.

Used to keep Solar API traffic under 100 req/min per the policy check.
In-process and not cluster-safe — fine for the MVP. Move to a shared
backing store (Redis) when we scale out.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._evict(now)
            if len(self._calls) >= self.max_calls:
                wait = self._calls[0] + self.window - now
                if wait > 0:
                    await asyncio.sleep(wait)
                self._evict(time.monotonic())
            self._calls.append(time.monotonic())

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._calls and self._calls[0] <= cutoff:
            self._calls.popleft()


# Google Solar API: stay well under the documented 100 req/min ceiling.
solar_limiter = SlidingWindowLimiter(max_calls=100, window_seconds=60.0)
