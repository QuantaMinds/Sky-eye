"""Phase 4 tests — production caching + rate limiting.

All 5 spec tests must pass (CLAUDE.md Rule 2):
  - test_ttl_expiry
  - test_rate_limiter_blocks_burst
  - test_concurrent_requests_respect_semaphore
  - test_cache_hit_rate_metric_works
  - test_redis_failure_falls_back_to_bigquery_cache

Tests run hermetic: fakeredis for the hot tier, mocked _bq_cache for
the cold tier. No live BigQuery, no live Redis, no live external APIs.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from api.middleware import _cache_metrics, rate_limiter, ttl_cache
from api.middleware._limiter_primitives import (
    ConcurrencyLimiter,
    SlidingWindowLimiter,
)


@pytest.fixture(autouse=True)
def _reset_state(mocker):
    """Each test starts with empty fakeredis + empty metrics + mocked BQ.

    We re-build the Redis client so prior-test keys don't leak into the
    next test (fakeredis instances share state by name unless reset).
    """
    from fakeredis import aioredis as fr
    fresh = fr.FakeRedis(decode_responses=True)
    ttl_cache._set_redis_client_for_tests(fresh)
    _cache_metrics._reset_for_tests()
    # Default: BQ tier is a no-op so we don't need credentials.
    mocker.patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None))
    mocker.patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None))
    yield


async def test_ttl_expiry(mocker):
    """Solar TTL is 30d. Write a value, then advance _now() past 30d
    and confirm the envelope freshness check refuses the cached entry.

    Also confirms the BQ fallback fires on Redis miss + returns None when
    BQ also has nothing (so the metric increments cache_miss, not hit)."""
    # Sanity: Solar TTL is 30 days per spec.
    assert ttl_cache.TTL_SECONDS["solar"] == 30 * 86400

    real_now = time.time()
    mocker.patch("api.middleware.ttl_cache._now", return_value=real_now)
    await ttl_cache.set("solar", "addr-1", {"panels": 24})
    hit = await ttl_cache.get("solar", "addr-1")
    assert hit == {"panels": 24}, "fresh value must hit"

    # Advance clock 31 days into the future.
    mocker.patch(
        "api.middleware.ttl_cache._now",
        return_value=real_now + 31 * 86400,
    )
    miss = await ttl_cache.get("solar", "addr-1")
    assert miss is None, "value past its 30d TTL must surface as miss"


async def test_rate_limiter_blocks_burst():
    """N+1th call inside the window blocks until the oldest call ages
    out. Uses a small fixture (3/0.2s) so the test runs in <1s rather
    than burning 60 wall-clock seconds against the spec's 60/min."""
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=0.2)
    t0 = time.monotonic()
    for _ in range(3):
        await limiter.acquire()  # first three are instant
    instant_elapsed = time.monotonic() - t0
    assert instant_elapsed < 0.05, f"first 3 calls should be instant, took {instant_elapsed:.3f}s"

    t1 = time.monotonic()
    await limiter.acquire()  # 4th must wait for the window to age
    waited = time.monotonic() - t1
    assert waited >= 0.15, f"4th call should wait ~0.2s, waited {waited:.3f}s"


async def test_concurrent_requests_respect_semaphore():
    """Solar's 10-concurrent cap holds even when 12 tasks pile in.
    Verified via the ConcurrencyLimiter's _peak counter."""
    sem = ConcurrencyLimiter(max_concurrent=10, name="test")

    observed: list[int] = []

    async def _do_request():
        async with sem:
            observed.append(sem.in_flight)
            await asyncio.sleep(0.05)

    await asyncio.gather(*[_do_request() for _ in range(12)])
    assert max(observed) <= 10, f"peak in-flight {max(observed)} > cap of 10"
    assert sem._peak <= 10
    assert sem._peak >= 1, "at least one request must have actually run"


async def test_cache_hit_rate_metric_works():
    """After mixed hits + misses, the per-service hit-rate is correct
    and reaches the /health surface via ttl_cache.hit_rates()."""
    # Set up: write+read twice (2 hits), then read 2 missing keys (2 misses)
    await ttl_cache.set("solar", "k1", {"v": 1})
    await ttl_cache.get("solar", "k1")  # hit
    await ttl_cache.get("solar", "k1")  # hit
    await ttl_cache.get("solar", "missing-1")  # miss
    await ttl_cache.get("solar", "missing-2")  # miss

    rates = ttl_cache.hit_rates()
    assert "solar" in rates
    assert rates["solar"] == pytest.approx(0.5, abs=0.001), \
        f"2 hits / 4 reads = 0.5, got {rates['solar']}"

    # Confirm the /health endpoint reflects the same metric.
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        r = client.get("/health")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "healthy"
    assert body["cache_hit_rate_per_service_last_1h"]["solar"] == pytest.approx(0.5)
    assert "rate_limit_headroom_per_service" in body
    assert body["rate_limit_headroom_per_service"]["solar"]["concurrent_available"] == 10


async def test_redis_failure_falls_back_to_bigquery_cache(mocker):
    """When Redis is unreachable, reads still serve via the BQ tier and
    writes still target BQ. The fallback must not surface as a miss."""
    # Swap Redis for a client whose get/set raise.
    class _BoomRedis:
        async def get(self, *a, **kw):
            raise RuntimeError("redis down")
        async def set(self, *a, **kw):
            raise RuntimeError("redis down")
    ttl_cache._set_redis_client_for_tests(_BoomRedis())

    # BQ tier serves the value when Redis raises.
    mocker.patch(
        "api.middleware._bq_cache.get",
        new=AsyncMock(return_value={"panels": 24, "kwh": 11420}),
    )
    bq_set = mocker.patch(
        "api.middleware._bq_cache.set", new=AsyncMock(return_value=None)
    )

    # Read should succeed via the BQ fallback and register as a HIT,
    # not a miss.
    value = await ttl_cache.get("solar", "k-during-outage")
    assert value == {"panels": 24, "kwh": 11420}
    rates = ttl_cache.hit_rates()
    assert rates.get("solar", 0) > 0, "BQ-served read must increment cache_hit"

    # Write should still target BQ even when Redis is down.
    await ttl_cache.set("solar", "k-write-during-outage", {"panels": 18})
    bq_set.assert_called()
    success_rate = ttl_cache.bq_success_rate()
    assert success_rate == 1.0, f"BQ writes should all succeed, got {success_rate}"


async def test_corrupt_redis_envelope_falls_through_to_bq(mocker):
    """Phase 4 forensic finding §7: a corrupt Redis value MUST fall
    through to BQ cleanly, never crash the read.

    Promotes the defense from accident-of-placement (the outer try/
    except in get() used to swallow JSONDecodeError implicitly) to an
    explicit catch inside _unwrap_if_fresh. The test exercises four
    distinct failure modes directly:
      1. Invalid JSON ("not json{")
      2. Valid JSON but wrong shape (top-level array)
      3. Envelope missing the 'v' key
      4. Envelope with a non-numeric 'exp' field

    See [[feedback-explicit-defense-not-accident]].
    """
    bq_value = {"panels": 24, "kwh": 11420}
    mocker.patch(
        "api.middleware._bq_cache.get",
        new=AsyncMock(return_value=bq_value),
    )
    mocker.patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None))

    class _CorruptRedis:
        def __init__(self, payload):
            self.payload = payload
        async def get(self, *a, **kw):
            return self.payload
        async def set(self, *a, **kw):
            pass

    cases = (
        ("invalid-json",       "not json{"),
        ("wrong-shape",        "[1,2,3]"),
        ("missing-v",          '{"exp": null}'),
        ("garbage-exp",        '{"v": {"x": 1}, "exp": "not-a-number"}'),
    )
    for label, payload in cases:
        ttl_cache._set_redis_client_for_tests(_CorruptRedis(payload))
        # The read must NOT raise — corrupt envelope returns None from
        # _unwrap_if_fresh, then ttl_cache falls through to BQ which
        # serves the real value.
        try:
            value = await ttl_cache.get("solar", f"k-{label}")
        except Exception as exc:
            pytest.fail(f"corrupt envelope {label!r} raised: {exc!r}")
        # Specifically: cases 1-3 surface the BQ value; case 4 also
        # serves from BQ because the envelope's exp can't be checked.
        assert value == bq_value, f"{label}: expected BQ value, got {value!r}"


async def test_startup_hook_invokes_ensure_table(mocker):
    """The FastAPI lifespan must call _bq_cache.ensure_table() exactly
    once during startup, AND must not crash the app if ensure_table
    raises (transient BQ outage during deploy).

    Catches the §8 forensic finding: code declared a CREATE TABLE
    statement but nothing in the app ever invoked it, so prod writes
    400'd on a missing table. The lifespan hook closes that gap.
    """
    from fastapi.testclient import TestClient

    # Happy path: ensure_table succeeds, app starts cleanly.
    ensure_mock = mocker.patch(
        "api.main._bq_cache.ensure_table",
        new=AsyncMock(return_value=None),
    )
    from api.main import app
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
    ensure_mock.assert_awaited_once()

    # Failure path: ensure_table raises but the app must STILL start
    # (idempotent DDL — lazy-create on first write is acceptable fallback).
    ensure_mock_fail = mocker.patch(
        "api.main._bq_cache.ensure_table",
        new=AsyncMock(side_effect=RuntimeError("simulated BQ outage at deploy")),
    )
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200, "startup must not crash on ensure_table failure"
    ensure_mock_fail.assert_awaited_once()
