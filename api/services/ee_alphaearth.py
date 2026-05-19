"""AlphaEarth annual satellite embeddings via Earth Engine.

Dataset: GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL — 64-band per-pixel
embeddings (A00..A63) at 10m resolution, one composite per year. Used
as the CHEAP first filter in TaxLens: comparing two years of mean
embeddings over a parcel costs one reduceRegion per year and ~no
bandwidth, so we run it across thousands of parcels in a bbox before
spending real money on Gemini Pro vision over the top-N candidates.

Truth-first: returns vector=None / source='unavailable' when no
AlphaEarth image intersects the geometry for that year. Never substitutes
a different-year embedding or a zero vector — that would silently produce
fake "no change" scores at the cosine-distance step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.services.earth_engine import ee_module

_COLLECTION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
_BAND_COUNT = 64
_BANDS = [f"A{i:02d}" for i in range(_BAND_COUNT)]
# Native AlphaEarth resolution. reduceRegion's `scale` argument controls
# the grid the mean is computed over — passing 10m keeps us on-grid and
# avoids EE up-sampling that inflates EECU cost without adding signal.
_SCALE_M = 10


@dataclass(frozen=True)
class EmbeddingResult:
    """64-D mean embedding over a parcel, or unavailable."""
    vector: list[float] | None
    source: str   # 'alphaearth' | 'unavailable'
    image_date: str | None
    note: str | None = None


def get_alphaearth_embeddings(geojson: dict[str, Any], year: int) -> EmbeddingResult:
    """Mean of the 64-band AlphaEarth annual composite over `geojson` for
    calendar year `year`. The annual composite has one image per tile per
    year, so we filterDate to the year and mosaic — no cloud handling
    needed (the upstream pipeline already does it)."""
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
        return EmbeddingResult(
            vector=None, source="unavailable", image_date=None,
            note=f"no AlphaEarth coverage in {year} for this geometry",
        )

    img = coll.mosaic().select(_BANDS)
    stats = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=_SCALE_M,
        maxPixels=1e8,
    ).getInfo()

    # reduceRegion returns None for any band fully masked over the
    # geometry. If even one band is missing the vector is incomplete and
    # cosine distance against it is meaningless — fail honestly (Rule 3).
    vector: list[float] = []
    for band in _BANDS:
        v = stats.get(band)
        if v is None:
            return EmbeddingResult(
                vector=None, source="unavailable",
                image_date=f"{year}-annual",
                note=f"band {band} masked over geometry — incomplete embedding",
            )
        vector.append(float(v))

    return EmbeddingResult(
        vector=vector, source="alphaearth",
        image_date=f"{year}-annual", note=None,
    )
