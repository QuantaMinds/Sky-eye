"""Rate-limiting primitives — sliding window, concurrency cap, token counter.

Each class is single-responsibility. Composed by api.middleware.rate_limiter.
In-process / per-uvicorn-worker — promote to Redis-backed when we cluster.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


class SlidingWindowLimiter:
    """Rolling-window RPM gate. The Nth+1 call inside `window` seconds
    blocks until the oldest call ages out."""

    def __init__(self, max_calls: int, window_seconds: float, *, name: str = "") -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self.name = name
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

    def headroom(self) -> int:
        self._evict(time.monotonic())
        return max(0, self.max_calls - len(self._calls))


class ConcurrencyLimiter:
    """Bounded in-flight cap via asyncio.Semaphore + headroom tracker."""

    def __init__(self, max_concurrent: int, *, name: str = "") -> None:
        self.max_concurrent = max_concurrent
        self.name = name
        self._sem = asyncio.Semaphore(max_concurrent)
        self._in_flight = 0
        self._peak = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ConcurrencyLimiter":
        await self._sem.acquire()
        async with self._lock:
            self._in_flight += 1
            if self._in_flight > self._peak:
                self._peak = self._in_flight
        return self

    async def __aexit__(self, *exc) -> None:
        async with self._lock:
            self._in_flight -= 1
        self._sem.release()

    def headroom(self) -> int:
        return max(0, self.max_concurrent - self._in_flight)

    @property
    def in_flight(self) -> int:
        return self._in_flight


@dataclass
class TokenCounter:
    """Rolling token usage for Gemini quota visibility — NOT a hard limiter.

    Vertex AI enforces real token quotas server-side; this exposes the
    minute-window usage to /health so we can see how close we are.
    """
    window_seconds: float = 60.0
    _input: deque[tuple[float, int]] = field(default_factory=deque)
    _output: deque[tuple[float, int]] = field(default_factory=deque)

    def record(self, *, input_tokens: int, output_tokens: int) -> None:
        now = time.monotonic()
        self._input.append((now, input_tokens))
        self._output.append((now, output_tokens))
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for q in (self._input, self._output):
            while q and q[0][0] <= cutoff:
                q.popleft()

    def usage(self) -> dict[str, int]:
        self._evict(time.monotonic())
        return {
            "input_tokens_last_window": sum(n for _, n in self._input),
            "output_tokens_last_window": sum(n for _, n in self._output),
        }
