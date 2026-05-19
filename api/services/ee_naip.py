"""NAIP aerial chip extraction via Earth Engine.

NAIP (USDA/NAIP/DOQQ) is 0.6-1m RGB+NIR aerial imagery refreshed every
2-3 years per state. California flights: 2020, 2022, 2024 (typical).
Asking for a year without a flight -> source='unavailable' (Rule 3),
NOT a silent fallback to the nearest year.

Returns PNG bytes (so callers can write to disk for the labeling tool
or feed to Gemini Pro multimodal). Server-side rendering via
getThumbURL — we never download the full GeoTIFF.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import httpx

from api.services.earth_engine import ee_module

_COLLECTION = "USDA/NAIP/DOQQ"
_VIS = {"bands": ["R", "G", "B"], "min": 0, "max": 255}


@dataclass(frozen=True)
class ChipResult:
    """Truth-first chip result. `png` is None iff source != 'naip'."""
    png: bytes | None
    source: str   # 'naip' | 'unavailable'
    image_date: str | None  # ISO date of the contributing scene, when known
    note: str | None = None


def _bounds_from_geojson(ee, geojson: dict[str, Any], buffer_m: float = 20.0):
    """Build the EE Geometry + a buffered bbox for context around the parcel."""
    geom = ee.Geometry(geojson)
    return geom.buffer(buffer_m).bounds()


def get_naip_chip(
    geojson: dict[str, Any],
    year: int,
    size_px: int = 256,
    *,
    buffer_m: float = 20.0,
) -> ChipResult:
    """Pull a NAIP RGB chip for `geojson` taken in calendar year `year`.

    Returns a ChipResult. If NAIP has no flight intersecting the geometry
    within `year`, returns source='unavailable' — never substitutes a
    different-year image (Rule 3: callers must know they have no chip).
    """
    ee = ee_module()
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    geom = ee.Geometry(geojson)
    coll = (
        ee.ImageCollection(_COLLECTION)
        .filterBounds(geom)
        .filterDate(start, end)
    )
    size = coll.size().getInfo()
    if size == 0:
        return ChipResult(
            png=None, source="unavailable", image_date=None,
            note=f"no NAIP coverage in {year} for this geometry",
        )

    # Mosaic in case the parcel straddles two DOQQ tiles flown the same season.
    img = coll.mosaic()
    # Pull the most recent contributing scene's date for attribution.
    last = coll.sort("system:time_start", False).first()
    image_date = ee.Date(last.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    region = _bounds_from_geojson(ee, geojson, buffer_m=buffer_m)
    url = img.getThumbURL({
        **_VIS,
        "region": region,
        "dimensions": f"{size_px}x{size_px}",
        "format": "png",
    })
    r = httpx.get(url, timeout=60.0)
    r.raise_for_status()
    return ChipResult(
        png=r.content, source="naip", image_date=image_date, note=None,
    )


def save_chip(chip: ChipResult, path) -> bool:
    """Helper for scripts: write png to disk if present, return whether
    bytes were actually written. Skips silently when png is None."""
    if chip.png is None:
        return False
    with io.open(path, "wb") as f:
        f.write(chip.png)
    return True
