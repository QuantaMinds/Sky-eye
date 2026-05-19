"""US Census ACS 5-year (2024 vintage) — median household income by block group.

ACS 5-year 2020-2024 was released Dec 2025; this is the most recent vintage
api.census.gov serves as of 2026-05. Two-step lookup: Census Geocoder
resolves lat/lng -> (state, county, tract, block group), then ACS
B19013_001E is fetched. Cached 30 days by rounded coordinates. The Census
Bureau uses -666666666 as a "no data" sentinel — we map that to None.
"""
from __future__ import annotations

import httpx

from api.config import get_settings
from api.middleware import rate_limiter, ttl_cache
from api.models.lead import CensusData

_ACS_VINTAGE = "2024"
_ACS_URL = f"https://api.census.gov/data/{_ACS_VINTAGE}/acs/acs5"
_GEO_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
_INCOME_VAR = "B19013_001E"
_SERVICE = "census"


def _cache_key(lat: float, lng: float) -> str:
    return f"{lat:.5f},{lng:.5f}"


def _parse_income(raw: str | int | float | None) -> float | None:
    if raw is None or raw == "" or str(raw) == "-666666666":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def get_block_group_data(lat: float, lng: float) -> tuple[CensusData, bool]:
    key = _cache_key(lat, lng)
    cached = await ttl_cache.get(_SERVICE, key)
    if cached is not None:
        return CensusData(**cached), True

    settings = get_settings()
    async with await rate_limiter.acquire(_SERVICE), httpx.AsyncClient(timeout=20.0) as client:
        geo = await client.get(
            _GEO_URL,
            params={
                "x": lng, "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "layers": "all", "format": "json",
            },
        )
        geo.raise_for_status()
        layers = (geo.json().get("result") or {}).get("geographies") or {}
        candidates = layers.get("2020 Census Blocks") or layers.get("Census Blocks") or []
        if not candidates:
            raise RuntimeError("Census Geocoder returned no block for this point")
        bg = candidates[0]
        state, county = bg.get("STATE"), bg.get("COUNTY")
        tract, bg_id = bg.get("TRACT"), bg.get("BLKGRP")
        if not all([state, county, tract, bg_id]):
            raise RuntimeError(f"Incomplete geography: {bg}")

        params: dict[str, str] = {
            "get": f"{_INCOME_VAR},NAME",
            "for": f"block group:{bg_id}",
            "in": f"state:{state} county:{county} tract:{tract}",
        }
        if settings.census_api_key:
            params["key"] = settings.census_api_key
        r = await client.get(_ACS_URL, params=params)

    # Census redirects invalid/missing keys to an HTML page instead of returning 401/403.
    if r.is_redirect:
        loc = r.headers.get("location", "")
        if "invalid_key" in loc:
            raise RuntimeError(
                "CENSUS_API_KEY rejected by api.census.gov (invalid_key). "
                "Request a fresh key at https://api.census.gov/data/key_signup.html — "
                "check your inbox/spam for the activation link before using it."
            )
        if "missing_key" in loc:
            raise RuntimeError("CENSUS_API_KEY not set on the request to api.census.gov.")
    r.raise_for_status()
    rows = r.json()
    if len(rows) < 2:
        raise RuntimeError("Census ACS returned no data row")

    result = CensusData(
        median_household_income=_parse_income(rows[1][0]),
        block_group_geoid=f"{state}{county}{tract}{bg_id}",
    )
    await ttl_cache.set(_SERVICE, key, result.model_dump())
    return result, False
