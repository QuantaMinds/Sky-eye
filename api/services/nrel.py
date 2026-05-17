"""NREL PVWatts v8 — annual production estimate for a residential PV system."""
from __future__ import annotations

import httpx

from api import cache
from api.config import get_settings
from api.models.lead import NRELData

_URL = "https://developer.nrel.gov/api/pvwatts/v8.json"


def _cache_key(lat: float, lng: float, system_kw: float) -> str:
    return f"nrel:{lat:.4f},{lng:.4f}:{system_kw}"


async def get_production(
    lat: float, lng: float, system_kw: float = 4.0
) -> tuple[NRELData, bool]:
    key = _cache_key(lat, lng, system_kw)
    hit = cache.get(key)
    if hit is not None:
        return NRELData(**hit), True

    settings = get_settings()
    if not settings.nrel_api_key:
        raise RuntimeError("NREL_API_KEY not set")

    params = {
        "api_key": settings.nrel_api_key,
        "lat": lat, "lon": lng,
        "system_capacity": system_kw,
        "module_type": 0, "losses": 14, "array_type": 1,
        "tilt": 20, "azimuth": 180,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(_URL, params=params)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(f"NREL errors: {data['errors']}")

    out = data.get("outputs") or {}
    result = NRELData(
        ac_annual_kwh=float(out.get("ac_annual", 0.0)),
        capacity_factor=out.get("capacity_factor"),
        solar_radiation=out.get("solrad_annual"),
    )
    cache.set(key, result.model_dump())
    return result, False
