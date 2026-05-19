"""Pre-warm the external-API caches for a batch of (lat, lng, address) points.

Runs the 4 cache-bearing services that take a coordinate input
(Solar, Geocoding, Census, NREL) for each input and writes results
into the Phase 4 cache. Gemini is intentionally NOT pre-warmed —
narratives are per-lead and lazy by design (feedback-no-narrative-in-batch).

Skips work when ttl_cache already has the key. Returns a stats dict.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from api.middleware import ttl_cache
from api.services import census, geocoding, nrel, solar_api


@dataclass
class WarmupStats:
    requested: int = 0
    solar_fetched: int = 0
    census_fetched: int = 0
    nrel_fetched: int = 0
    geocoding_fetched: int = 0
    failed: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> dict:
        return {
            "requested": self.requested,
            "solar_fetched": self.solar_fetched,
            "census_fetched": self.census_fetched,
            "nrel_fetched": self.nrel_fetched,
            "geocoding_fetched": self.geocoding_fetched,
            "failed": self.failed,
            "errors": self.errors[:5],
        }


async def _warm_one(lat: float, lng: float, address: str, stats: WarmupStats) -> None:
    # Each call returns (data, cache_hit). cache_hit=False means we just
    # fetched fresh and wrote to the cache — that's a real warming event.
    try:
        _, hit = await solar_api.get_roof_data(lat, lng, address)
        if not hit:
            stats.solar_fetched += 1
    except Exception as exc:
        stats.errors.append(f"solar {address!r}: {exc}")
        stats.failed += 1

    try:
        _, hit = await census.get_block_group_data(lat, lng)
        if not hit:
            stats.census_fetched += 1
    except Exception as exc:
        stats.errors.append(f"census {address!r}: {exc}")
        stats.failed += 1

    try:
        _, hit = await nrel.get_production(lat, lng)
        if not hit:
            stats.nrel_fetched += 1
    except Exception as exc:
        stats.errors.append(f"nrel {address!r}: {exc}")
        stats.failed += 1

    # Geocoding is pre-warmed only when caller supplies the address —
    # the (lat, lng) is already resolved here, but storing the reverse
    # mapping is harmless and saves a hop on the next batch round.
    if address:
        try:
            _, hit = await geocoding.geocode(address)
            if not hit:
                stats.geocoding_fetched += 1
        except Exception as exc:
            stats.errors.append(f"geocoding {address!r}: {exc}")
            stats.failed += 1


async def warm(points: list[tuple[float, float, str]], *, concurrency: int = 8) -> WarmupStats:
    """Pre-warm caches for the given (lat, lng, address) points.

    concurrency caps in-flight points; the service-level semaphores
    (Solar=10) still apply on top of this.
    """
    stats = WarmupStats(requested=len(points))
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(p):
        async with sem:
            await _warm_one(*p, stats=stats)

    await asyncio.gather(*[_bounded(p) for p in points])
    return stats
