"""Rolling 1-hour hit/miss + BQ-write counters for /health observability.

In-process only — when we cluster across uvicorn workers, swap this for
a Redis-backed counter set. Stats are per-service for cache; flat for
BQ writes (single counter).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_HOUR_SECONDS = 3600.0


class _RollingHitMiss:
    """Hits + misses inside the last `window` seconds. Per service."""

    def __init__(self, window: float = _HOUR_SECONDS) -> None:
        self.window = window
        # (timestamp, is_hit)
        self._events: deque[tuple[float, bool]] = deque()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()

    def hit(self) -> None:
        self._events.append((time.monotonic(), True))

    def miss(self) -> None:
        self._events.append((time.monotonic(), False))

    def rate(self) -> float | None:
        """Return hit-rate fraction (0..1) over the rolling window.
        None when no events recorded — distinguishes 'no traffic' from
        'all misses', which would otherwise both read as 0.0."""
        self._evict(time.monotonic())
        if not self._events:
            return None
        hits = sum(1 for _, h in self._events if h)
        return hits / len(self._events)


class _RollingSuccessFail:
    """Sliding-window success-rate tracker. Used for BQ writes."""

    def __init__(self, window: float = _HOUR_SECONDS) -> None:
        self.window = window
        self._events: deque[tuple[float, bool]] = deque()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()

    def ok(self) -> None:
        self._events.append((time.monotonic(), True))

    def fail(self) -> None:
        self._events.append((time.monotonic(), False))

    def rate(self) -> float | None:
        self._evict(time.monotonic())
        if not self._events:
            return None
        return sum(1 for _, ok in self._events if ok) / len(self._events)


# Module-level singletons. Reset on process restart — fine for /health.
_cache_counters: dict[str, _RollingHitMiss] = defaultdict(_RollingHitMiss)
bq_writes = _RollingSuccessFail()


def cache_hit(service: str) -> None:
    _cache_counters[service].hit()


def cache_miss(service: str) -> None:
    _cache_counters[service].miss()


def hit_rates() -> dict[str, float | None]:
    return {svc: c.rate() for svc, c in _cache_counters.items()}


def bq_success_rate() -> float | None:
    return bq_writes.rate()


# Test hook — reset all in-process state. Never call from production code.
def _reset_for_tests() -> None:
    _cache_counters.clear()
    bq_writes._events.clear()
