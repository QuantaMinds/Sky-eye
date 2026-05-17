"""Google Geocoding API — address -> (lat, lng).

Cached 30 days by lowercased address. Uses the same Maps Platform key as Solar.
"""
from __future__ import annotations

import httpx

from api import cache
from api.config import get_settings
from api.models.lead import GeocodingResult

_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def _cache_key(address: str) -> str:
    return f"geocode:{address.lower().strip()}"


async def geocode(address: str) -> tuple[GeocodingResult, bool]:
    """Returns (result, cache_hit)."""
    key = _cache_key(address)
    hit = cache.get(key)
    if hit is not None:
        return GeocodingResult(**hit), True

    settings = get_settings()
    if not settings.google_solar_api_key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY not set (also used for Geocoding API)")

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
    cache.set(key, result.model_dump())
    return result, False
