"""Sentinel-2 SR Harmonized chip extraction via Earth Engine.

S2 is 10m optical, revisited every ~5 days. We don't expect to see ADUs
in a single S2 pixel — the role of S2 in TaxLens is the *multi-source
agreement* gate: an AlphaEarth-flagged change should also show up as a
reflectance shift in a coarser sensor before we trust it.

Output is a median composite of all (mostly) cloud-free scenes within
the calendar year. If no qualifying scenes exist, source='unavailable'
(Rule 3) — we never return a cloud-contaminated chip dressed as clean.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import httpx

from api.services.earth_engine import ee_module
from api.services.ee_naip import ChipResult  # reuse the same record shape

_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
_VIS = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}
_MAX_CLOUD_PCT = 30  # tighter than 60 default; we want clean composites


def _mask_clouds(img):
    """SR Harmonized: use the SCL classification band (4=vegetation, 5=
    bare soil, 6=water, 7=unclassified, 11=snow are "keep"; 3=shadow,
    8=cloud-medium-prob, 9=cloud-high-prob, 10=cirrus are "drop").

    QA60 was DEPRECATED for SR Harmonized in 2022-06 (all zeros for
    scenes after that date), so the previous QA60-based mask silently
    dropped no clouds on recent scenes — the median composite was
    cloud-contaminated. Found in the Phase 5 forensic pass."""
    scl = img.select("SCL")
    keep = (
        scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7)).Or(scl.eq(11))
    )
    return img.updateMask(keep)


def get_sentinel2_chip(
    geojson: dict[str, Any],
    year: int,
    size_px: int = 64,
    *,
    buffer_m: float = 40.0,
) -> ChipResult:
    """Pull an S2 median composite RGB chip for `geojson` for calendar year `year`."""
    ee = ee_module()
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    geom = ee.Geometry(geojson)
    coll = (
        ee.ImageCollection(_COLLECTION)
        .filterBounds(geom)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", _MAX_CLOUD_PCT))
        .map(_mask_clouds)
    )
    size = coll.size().getInfo()
    if size == 0:
        return ChipResult(
            png=None, source="unavailable", image_date=None,
            note=f"no S2 scenes <{_MAX_CLOUD_PCT}% cloud in {year}",
        )

    composite = coll.median()
    region = geom.buffer(buffer_m).bounds()
    url = composite.getThumbURL({
        **_VIS,
        "region": region,
        "dimensions": f"{size_px}x{size_px}",
        "format": "png",
    })
    r = httpx.get(url, timeout=60.0)
    r.raise_for_status()
    return ChipResult(
        png=r.content, source="sentinel2_median", image_date=f"{year}-median",
        note=f"median of {size} scenes",
    )
