"""LA County parcel lookup by (lat, lng).

Phase 1.5c — replaces the assessor.py mock. Resolves a geocoded point to the
parcel that contains it via BigQuery `ST_CONTAINS` on the WGS84-reprojected
polygon table, and returns owner-occupancy + tenure-equity signals.

Architecture:
  - Single SQL: ST_CONTAINS on geom-clustered table. BQ's S2-cell pruning
    handles spatial indexing natively; NO manual bbox prefilter (verified
    2026-05-17: it slows queries and silently drops large-parcel edge hits).
  - QueryJobConfig.maximum_bytes_billed = 580 MB hard ceiling
    (~0.35 cent absolute max per lookup, 5x the measured typical cost).
  - SQLite cache layer = DOUBLE-CLICK SHIELD ONLY. Coord-keyed caches have
    ~0% hit rate on fresh leads; the cache only protects against
    reloads / duplicate async fires (see feedback_coord_cache_is_double_click_shield).
"""
from __future__ import annotations

from google.cloud import bigquery

from api import cache
from api.config import get_settings
from api.models.lead import ParcelData

_TABLE = "sky-eye-496604.parcels.la_county"

_LOOKUP_SQL = f"""
WITH matches AS (
  SELECT
    apn, address_situs, city, zip,
    use_category, use_subcategory, use_code,
    is_residential, is_taxable, stream,
    has_homeowners_exemption, homeowners_exemption_amount,
    arms_length_year, recording_year,
    year_built, sqft_main, total_value, land_value, improvement_value,
    area_m2,
    -- # of AINs whose polygon contains this point. >1 means we're inside
    -- a multi-unit building (condo / apartment) and the returned AIN is
    -- one of the sibling units, not necessarily the queried one.
    COUNT(*) OVER () AS ains_at_point
  FROM `{_TABLE}`
  WHERE ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
)
SELECT * FROM matches LIMIT 1
"""

# BQ's `maximum_bytes_billed` is a PRE-EXECUTION ceiling. The spatial query
# planner cannot predict S2-cell pruning selectivity ahead of time, so the
# pre-execution estimate is roughly the size of the geom column (~1.4 GB).
# Set the ceiling above that worst-case estimate; actual cost after pruning
# is typically <50 MB processed (~0.03 cents). The ceiling here catches a
# JOIN-gone-wrong or accidentally-missing WHERE clause, not normal queries.
_MAX_BYTES = 2_500_000_000  # ~1.5 cent absolute ceiling; ~50x typical actual cost


def _cache_key(lat: float, lng: float) -> str:
    return f"parcel:{lat:.6f},{lng:.6f}"


def _to_float(v: object) -> float | None:
    """BigQuery NUMERIC -> Decimal; coerce to float for Pydantic. None pass-through."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def lookup_by_point(lat: float, lng: float) -> tuple[ParcelData | None, bool]:
    """Returns (parcel_data, cache_hit).

    parcel_data is None when no LA County parcel contains the point (out of
    county, or a road / right-of-way gap). Truth-first: never substitute.
    """
    key = _cache_key(lat, lng)
    hit = cache.get(key)
    if hit is not None:
        return (ParcelData(**hit["parcel"]) if hit["parcel"] else None, True)

    settings = get_settings()
    project = settings.google_cloud_project or "sky-eye-496604"
    client = bigquery.Client(project=project, location="us-west1")

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lat", "FLOAT64", lat),
            bigquery.ScalarQueryParameter("lng", "FLOAT64", lng),
        ],
        maximum_bytes_billed=_MAX_BYTES,
    )
    rows = list(client.query(_LOOKUP_SQL, job_config=job_config).result())

    if not rows:
        cache.set(key, {"parcel": None}, ttl_days=30)
        return None, False

    row = dict(rows[0])
    # The 9999 sentinel comes from LEAST(..., 9999) in script 08 when both
    # land_base_year and improvement_base_year are missing. Map to None
    # so downstream tenure logic routes to low_confidence (truth-first).
    arms_length = row.get("arms_length_year")
    if arms_length is not None and arms_length >= 9999:
        arms_length = None

    ains_at_point = int(row.get("ains_at_point") or 1)
    resolution = "building" if ains_at_point > 1 else "parcel"

    parcel = ParcelData(
        apn=row["apn"],
        address_situs=row.get("address_situs") or "",
        city=row.get("city") or "",
        zip=row.get("zip") or "",
        use_category=row.get("use_category") or "",
        use_subcategory=row.get("use_subcategory") or "",
        use_code=row.get("use_code") or "",
        is_residential=bool(row.get("is_residential")),
        is_taxable=bool(row.get("is_taxable")),
        stream=row.get("stream") or "not_residential",
        has_homeowners_exemption=bool(row.get("has_homeowners_exemption")),
        homeowners_exemption_amount=_to_float(row.get("homeowners_exemption_amount")),
        arms_length_year=arms_length,
        recording_year=row.get("recording_year"),
        year_built=row.get("year_built"),
        sqft_main=row.get("sqft_main"),
        total_value=_to_float(row.get("total_value")),
        land_value=_to_float(row.get("land_value")),
        improvement_value=_to_float(row.get("improvement_value")),
        area_m2=row.get("area_m2"),
        resolution_confidence=resolution,
        ains_at_point=ains_at_point,
    )
    cache.set(key, {"parcel": parcel.model_dump(mode="json")}, ttl_days=30)
    return parcel, False
