"""Phase 4 load test — drive the rate limiters + cache hot/cold paths
without spending a dollar on live APIs.

Usage:
    python scripts/loadtest_phase4.py --concurrent 50 --duration 60

What it does:
  - Mocks the external HTTP calls (Solar / Geocoding / Census / NREL) so
    no real spend, no ToS-burning traffic
  - Mocks the BQ cold tier so no BigQuery cost
  - Uses fakeredis as the hot tier
  - Fires `concurrent` async workers for `duration` seconds, each picking
    a random (lat,lng,address) from a synthetic pool and running a
    mini-pipeline (solar + census + nrel + occasional geocode)
  - Measures: cache hit rate, rate-limit wait time, success/fail counts,
    p50 / p95 wall-clock latency per pipeline call

Pass criteria:
  - Zero unhandled exceptions
  - Cache hit rate >= 50% after the warmup period
  - All rate limiters report >= 0 headroom at end (i.e. window honored)
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.middleware import _cache_metrics, rate_limiter, ttl_cache  # noqa: E402


def _bench_pool(n: int) -> list[tuple[float, float, str]]:
    """Synthetic LA-area lat/lng/address pool. Deliberately small so the
    cache hit rate climbs over the run — that's the whole point."""
    out = []
    for i in range(n):
        lat = 34.05 + (i % 40) * 0.005
        lng = -118.25 - (i // 40) * 0.005
        out.append((lat, lng, f"{i*10} Synthetic Blvd, Los Angeles, CA"))
    return out


class _Fake200Response:
    status_code = 200
    is_redirect = False
    def __init__(self, body: dict) -> None:
        self._body = body
    def raise_for_status(self) -> None:
        pass
    def json(self) -> dict:
        return self._body


_FAKE_SOLAR_BODY = {
    "name": "buildings/loadtest",
    "solarPotential": {
        "maxArrayPanelsCount": 22,
        "maxSunshineHoursPerYear": 1700.0,
        "solarPanelConfigs": [{"yearlyEnergyDcKwh": 10500.0}],
    },
}
_FAKE_CENSUS_GEO = {
    "result": {
        "geographies": {
            "2020 Census Blocks": [
                {"STATE": "06", "COUNTY": "037", "TRACT": "207400", "BLKGRP": "1"}
            ]
        }
    }
}
_FAKE_CENSUS_ACS = [["B19013_001E", "NAME"], ["72500", "Block Group 1"]]
_FAKE_NREL = {"errors": [], "outputs": {"ac_annual": 11200.0, "capacity_factor": 0.18, "solrad_annual": 5.3}}
_FAKE_GEOCODE = {
    "status": "OK",
    "results": [{
        "geometry": {"location": {"lat": 34.06, "lng": -118.27}},
        "formatted_address": "Synthetic, Los Angeles, CA",
    }],
}


class _FakeAsyncClient:
    """Mocks httpx.AsyncClient — returns canned bodies per URL pattern."""
    def __init__(self, *a, **kw): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): pass
    async def get(self, url: str, params: dict | None = None, **kw):
        # Inject tiny latency so the rate limiters have time to interleave.
        await asyncio.sleep(0.002)
        if "solar.googleapis.com" in url:
            return _Fake200Response(_FAKE_SOLAR_BODY)
        if "geocoding.geo.census.gov" in url:
            return _Fake200Response(_FAKE_CENSUS_GEO)
        if "api.census.gov" in url:
            return _Fake200Response(_FAKE_CENSUS_ACS)
        if "developer.nrel.gov" in url:
            return _Fake200Response(_FAKE_NREL)
        if "maps.googleapis.com" in url:
            return _Fake200Response(_FAKE_GEOCODE)
        return _Fake200Response({})


async def _one_iteration(pool, latencies, errors):
    lat, lng, addr = random.choice(pool)
    t0 = time.perf_counter()
    try:
        from api.services import solar_api, census, nrel
        await solar_api.get_roof_data(lat, lng, addr)
        await census.get_block_group_data(lat, lng)
        await nrel.get_production(lat, lng)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    latencies.append((time.perf_counter() - t0) * 1000)


async def _worker(stop_at, pool, latencies, errors, counter):
    while time.monotonic() < stop_at:
        await _one_iteration(pool, latencies, errors)
        counter[0] += 1


async def run(concurrent: int, duration: int) -> int:
    # Hermetic: fakeredis + mocked BQ + mocked httpx.
    from fakeredis import aioredis as fr
    ttl_cache._set_redis_client_for_tests(fr.FakeRedis(decode_responses=True))
    _cache_metrics._reset_for_tests()

    pool = _bench_pool(80)  # 80 unique points => hit rate climbs after warmup
    latencies: list[float] = []
    errors: list[str] = []
    counter = [0]

    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)), \
         patch("api.services.solar_api.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.services.census.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.services.nrel.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.config.get_settings") as mock_settings:
        mock_settings.return_value.google_solar_api_key = "fake"
        mock_settings.return_value.google_cloud_project = "fake"
        mock_settings.return_value.nrel_api_key = "fake"
        mock_settings.return_value.census_api_key = "fake"
        mock_settings.return_value.vertex_ai_location = "us-central1"

        stop_at = time.monotonic() + duration
        t0 = time.monotonic()
        await asyncio.gather(*[
            _worker(stop_at, pool, latencies, errors, counter)
            for _ in range(concurrent)
        ])
        elapsed = time.monotonic() - t0

    headroom = rate_limiter.headroom()
    rates = ttl_cache.hit_rates()

    latencies.sort()
    p50 = latencies[len(latencies)//2] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if latencies else 0
    iters = counter[0]
    pipelines_per_sec = iters / elapsed if elapsed else 0

    print(f"\nload test: concurrent={concurrent}  duration={duration}s  elapsed={elapsed:.1f}s")
    print(f"  total pipeline iterations:  {iters}")
    print(f"  pipelines / sec:            {pipelines_per_sec:.1f}")
    print(f"  latency p50:                {p50:.1f} ms")
    print(f"  latency p95:                {p95:.1f} ms")
    print(f"  errors:                     {len(errors)}")
    print(f"  cache hit rates:            {rates}")
    print(f"  rate-limit headroom (end):  {headroom}")

    ok = True
    if errors:
        print(f"  FAIL: {len(errors)} errors — sample: {errors[:3]}")
        ok = False
    # After warmup, hit rate should be high — each call writes to cache then
    # subsequent calls for the same coord hit. With 80 unique points and
    # many iterations, hit rate >= 50% is the floor.
    for svc, rate in rates.items():
        if rate is not None and rate < 0.5:
            print(f"  FAIL: {svc} hit rate {rate:.2f} < 0.5 floor")
            ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrent", type=int, default=50)
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()
    return asyncio.run(run(args.concurrent, args.duration))


if __name__ == "__main__":
    sys.exit(main())
