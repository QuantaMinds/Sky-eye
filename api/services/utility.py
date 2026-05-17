"""Electric utility lookup by (lat, lng).

Phase 1.5d. Resolves a point to a service-territory polygon
(parcels_raw.utility_territories), joins to parcels_raw.utility_rates for
the representative rate + tariff + NEM regime + confidence_level.

If no polygon contains the point (e.g. Burbank, Glendale, other small munis),
falls back to the 'unknown' row from utility_rates with confidence='fallback'.

Same caching pattern as parcel_lookup: SQLite as a double-click shield, not
a warm-path accelerator (fresh leads still pay the BQ cost once).
"""
from __future__ import annotations

from google.cloud import bigquery

from api import cache
from api.config import get_settings
from api.models.lead import UtilityInfo

# ST_CONTAINS gatekeeper, LEFT JOIN rates so we always get a row.
# If no territory polygon matches, the territories CTE is empty and we
# fall through to the 'unknown' fallback row.
_LOOKUP_SQL = """
WITH matched AS (
  SELECT utility_name
  FROM `sky-eye-496604.parcels_raw.utility_territories`
  WHERE ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
  LIMIT 1
),
resolved AS (
  SELECT COALESCE((SELECT utility_name FROM matched), 'unknown') AS utility_name
)
SELECT r.utility_name,
       rates.representative_rate,
       rates.tariff_variant,
       rates.nem_regime,
       rates.confidence_level,
       rates.rate_source_note
FROM resolved r
LEFT JOIN `sky-eye-496604.parcels_raw.utility_rates` rates
  ON rates.utility_name = r.utility_name
"""

_MAX_BYTES = 2_500_000_000  # same ceiling pattern as parcel_lookup


def _cache_key(lat: float, lng: float) -> str:
    return f"utility:{lat:.6f},{lng:.6f}"


def _to_float(v: object) -> float:
    if v is None:
        return 0.30  # fallback
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.30


async def lookup_by_point(lat: float, lng: float) -> tuple[UtilityInfo, bool]:
    """Returns (utility, cache_hit). Always returns a UtilityInfo — falls
    through to the 'unknown' fallback row if no territory matches."""
    key = _cache_key(lat, lng)
    hit = cache.get(key)
    if hit is not None:
        return UtilityInfo(**hit["utility"]), True

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
        # Shouldn't happen — utility_rates always has 'unknown'. Guard anyway.
        util = UtilityInfo()
    else:
        row = dict(rows[0])
        util = UtilityInfo(
            utility_name=row.get("utility_name") or "unknown",
            representative_rate=_to_float(row.get("representative_rate")),
            tariff_variant=row.get("tariff_variant"),
            nem_regime=row.get("nem_regime"),
            confidence_level=row.get("confidence_level") or "fallback",
            rate_source_note=row.get("rate_source_note") or "",
        )
    cache.set(key, {"utility": util.model_dump(mode="json")}, ttl_days=30)
    return util, False
