"""SB-535 Disadvantaged Community lookup by (lat, lng).

Phase 1.5e. Resolves a point to an OEHHA SB-535 DAC tract via ST_CONTAINS
against parcels_raw.dac_tracts (1,173 LA County tracts). Returns DacInfo
with is_dac flag + CES percentile + source.

Used downstream by scoring.compute_score to apply the DAC-SASH eligibility
UNION rule (residential lead lands in DAC-SASH stream if in_dac OR
non_taxable — both populations qualify for GRID Alternatives' program).
NOT an override of taxability; a union of two qualifying populations.
"""
from __future__ import annotations

from google.cloud import bigquery

from api import cache
from api.config import get_settings
from api.models.lead import DacInfo

_LOOKUP_SQL = """
SELECT tract_geoid, ces_percentile
FROM `sky-eye-496604.parcels_raw.dac_tracts`
WHERE ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
LIMIT 1
"""

_MAX_BYTES = 2_500_000_000  # same ceiling as parcel/utility lookups


def _cache_key(lat: float, lng: float) -> str:
    return f"dac:{lat:.6f},{lng:.6f}"


async def lookup_by_point(lat: float, lng: float) -> tuple[DacInfo, bool]:
    """Returns (dac_info, cache_hit). is_dac=False if no DAC tract contains
    the point (most of LA County is non-DAC)."""
    key = _cache_key(lat, lng)
    hit = cache.get(key)
    if hit is not None:
        return DacInfo(**hit["dac"]), True

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
        info = DacInfo(is_dac=False, source_note="not in any SB-535 DAC tract")
    else:
        row = dict(rows[0])
        info = DacInfo(
            is_dac=True,
            tract_geoid=row.get("tract_geoid"),
            ces_percentile=float(row["ces_percentile"]) if row.get("ces_percentile") is not None else None,
            source_note=(
                f"OEHHA SB-535 DAC tract {row.get('tract_geoid')}; "
                f"CES percentile {row.get('ces_percentile'):.1f}"
            ),
        )
    cache.set(key, {"dac": info.model_dump(mode="json")}, ttl_days=30)
    return info, False
