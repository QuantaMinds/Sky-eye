
"""Google Solar API — buildingInsights:findClosest.

Cached 30 days by lowercased address (per Solar API ToS).
Rate-limited to 100 req/min by api.rate_limit.solar_limiter.

TRUTH-FIRST: the public Solar API does not expose detected arrays. We
emit `has_existing_solar=None` rather than guessing False. A real
detector (Insights program or CV on dataLayers GeoTIFF) is Phase 2.
"""
from __future__ import annotations

import httpx

from api import cache
from api.config import get_settings
from api.models.lead import SolarRoofData
from api.rate_limit import solar_limiter

_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"


def _cache_key(address: str) -> str:
    return f"solar:{address.lower().strip()}"


def _empty(building_name: str = "(no Solar coverage)") -> SolarRoofData:
    return SolarRoofData(building_name=building_name)


async def get_roof_data(
    lat: float, lng: float, address: str
) -> tuple[SolarRoofData, bool]:
    """Returns (data, cache_hit). Empty record on 404 (no Solar imagery)."""
    key = _cache_key(address)
    hit = cache.get(key)
    if hit is not None:
        return SolarRoofData(**hit), True

    settings = get_settings()
    if not settings.google_solar_api_key:
        raise RuntimeError("GOOGLE_SOLAR_API_KEY not set")

    await solar_limiter.acquire()
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
        cache.set(key, result.model_dump(), ttl_days=7)
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
    cache.set(key, result.model_dump())
    return result, False
