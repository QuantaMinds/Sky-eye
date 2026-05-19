"""Google Solar API — buildingInsights:findClosest.

Phase 4: caching via api.middleware.ttl_cache (Redis hot / BigQuery cold,
30d TTL); rate limited via api.middleware.rate_limiter ("solar" service:
10 concurrent + 100/min burst, per Google ToS). 404s are cached with a
shorter 7d override so we re-probe Solar coverage sooner.

TRUTH-FIRST: the public Solar API does not expose detected arrays. We
emit `has_existing_solar=None` rather than guessing False. A real
detector (Insights program or CV on dataLayers GeoTIFF) is Phase 2.
"""
from __future__ import annotations

import httpx

from api.config import get_settings
from api.middleware import rate_limiter, ttl_cache
from api.models.lead import SolarRoofData

_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
_SERVICE = "solar"
_NOT_FOUND_TTL_SECONDS = 7 * 86400  # re-probe 404s after a week


def _cache_key(address: str) -> str:
    return address.lower().strip()


def _empty(building_name: str = "(no Solar coverage)") -> SolarRoofData:
    return SolarRoofData(building_name=building_name)


async def get_roof_data(
    lat: float, lng: float, address: str
) -> tuple[SolarRoofData, bool]:
    """Returns (data, cache_hit). Empty record on 404 (no Solar imagery)."""
    key = _cache_key(address)
    cached = await ttl_cache.get(_SERVICE, key)
    if cached is not None:
        return SolarRoofData(**cached), True

    settings = get_settings()
    if not settings.google_solar_api_key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY not set")

    async with await rate_limiter.acquire(_SERVICE):
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                _URL,
                params={
                    "location.latitude": lat,
                    "location.longitude": lng,
                    "requiredQuality": "HIGH",
                    "key": settings.google_solar_api_key,
                },
            )

    if r.status_code == 404:
        result = _empty()
        await ttl_cache.set(
            _SERVICE, key, result.model_dump(), ttl_override=_NOT_FOUND_TTL_SECONDS
        )
        return result, False
    r.raise_for_status()

    data = r.json()
    sp = data.get("solarPotential") or {}
    configs = sp.get("solarPanelConfigs") or []
    best = (
        max(configs, key=lambda c: c.get("yearlyEnergyDcKwh", 0)) if configs else {}
    )
    result = SolarRoofData(
        max_array_panels=sp.get("maxArrayPanelsCount"),
        max_kwh_year=best.get("yearlyEnergyDcKwh"),
        max_sunshine_hours=sp.get("maxSunshineHoursPerYear"),
        has_existing_solar=None,  # unknown — public API does not expose this
        building_name=(data.get("name") or "")[:64],
    )
    await ttl_cache.set(_SERVICE, key, result.model_dump())
    return result, False
