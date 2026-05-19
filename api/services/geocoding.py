"""Google Geocoding API — address -> (lat, lng).

Phase 4: cached via ttl_cache (30d TTL); rate-limited at 50/min via the
"geocoding" service in rate_limiter. Uses the same Maps Platform key as
the Solar API (one billing line for both).
"""
from __future__ import annotations

import httpx

from api.config import get_settings
from api.middleware import rate_limiter, ttl_cache
from api.models.lead import GeocodingResult

_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_SERVICE = "geocoding"


def _cache_key(address: str) -> str:
    return address.lower().strip()


async def geocode(address: str) -> tuple[GeocodingResult, bool]:
    """Returns (result, cache_hit)."""
    key = _cache_key(address)
    cached = await ttl_cache.get(_SERVICE, key)
    if cached is not None:
        return GeocodingResult(**cached), True

    settings = get_settings()
    if not settings.google_solar_api_key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY not set (also used for Geocoding API)")

    async with await rate_limiter.acquire(_SERVICE):
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                _URL,
                params={"address": address, "key": settings.google_solar_api_key},
            )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise RuntimeError(f"Geocoding failed: status={data.get('status')}")

    top = data["results"][0]
    loc = top["geometry"]["location"]
    result = GeocodingResult(
        lat=loc["lat"], lng=loc["lng"], formatted_address=top["formatted_address"]
    )
    await ttl_cache.set(_SERVICE, key, result.model_dump())
    return result, False
