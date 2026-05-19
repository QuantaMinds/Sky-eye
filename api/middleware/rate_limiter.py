"""Per-service rate-limiter registry — Phase 4 ToS policy is canonical here.

Spec config (do not drift; update _SPEC and both producers/consumers pick up):
  - Solar API:    10 concurrent, 100/min burst (ToS-bound)
  - Geocoding:    50/min burst
  - Gemini Flash: 60/min burst + input/output token counters
  - Census:       500/min burst
  - NREL:         no enforced limit (spec does not require)

Public surface:
  - acquire(service)          -> applies the burst window, returns the
                                 concurrency limiter (or None) for use as
                                 an async context manager
  - record_gemini_tokens(...) -> records input/output token usage from
                                 the Vertex AI response usage_metadata
  - headroom()                -> snapshot of remaining capacity per
                                 service — consumed by /health
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Iterable

from api.middleware._limiter_primitives import (
    ConcurrencyLimiter,
    SlidingWindowLimiter,
    TokenCounter,
)


@dataclass(frozen=True)
class ServiceLimits:
    name: str
    rpm: int | None = None
    concurrent: int | None = None
    track_tokens: bool = False


_SPEC: tuple[ServiceLimits, ...] = (
    ServiceLimits("solar",     rpm=100, concurrent=10),
    ServiceLimits("geocoding", rpm=50),
    ServiceLimits("gemini",    rpm=60, track_tokens=True),
    ServiceLimits("census",    rpm=500),
)


class _Registry:
    def __init__(self, spec: Iterable[ServiceLimits]) -> None:
        self._windows: dict[str, SlidingWindowLimiter] = {}
        self._concurrency: dict[str, ConcurrencyLimiter] = {}
        self._tokens: dict[str, TokenCounter] = {}
        for s in spec:
            if s.rpm is not None:
                self._windows[s.name] = SlidingWindowLimiter(s.rpm, 60.0, name=s.name)
            if s.concurrent is not None:
                self._concurrency[s.name] = ConcurrencyLimiter(s.concurrent, name=s.name)
            if s.track_tokens:
                self._tokens[s.name] = TokenCounter()

    def window(self, service: str) -> SlidingWindowLimiter | None:
        return self._windows.get(service)

    def concurrency(self, service: str) -> ConcurrencyLimiter | None:
        return self._concurrency.get(service)

    def tokens(self, service: str) -> TokenCounter | None:
        return self._tokens.get(service)

    def headroom(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for name, w in self._windows.items():
            out.setdefault(name, {})["burst_available"] = w.headroom()
        for name, c in self._concurrency.items():
            out.setdefault(name, {})["concurrent_available"] = c.headroom()
        for name, t in self._tokens.items():
            out.setdefault(name, {}).update(t.usage())
        return out


registry = _Registry(_SPEC)


async def acquire(service: str):
    """Apply the burst window for `service`. Returns an async context
    manager — the concurrency limiter when the service has one, else a
    null context. Caller MUST enter it before issuing the request:

        async with await rate_limiter.acquire("solar"):
            ...  # the external API call
    """
    w = registry.window(service)
    if w is not None:
        await w.acquire()
    c = registry.concurrency(service)
    return c if c is not None else contextlib.nullcontext()


def record_gemini_tokens(input_tokens: int, output_tokens: int) -> None:
    t = registry.tokens("gemini")
    if t is not None:
        t.record(input_tokens=input_tokens, output_tokens=output_tokens)


def headroom() -> dict[str, dict[str, int]]:
    return registry.headroom()
