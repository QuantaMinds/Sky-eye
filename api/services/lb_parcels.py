"""Long Beach parcel geometry lookup.

Inverse of parcel_lookup.py (which goes lat/lng -> APN). Phase 5 needs:
  - geometry-by-APN for the labeling tool and chip extractor
  - APN list within a bbox for change_detector candidate selection

Both queries hit `sky-eye-496604.parcels.la_county` (Long Beach is in LA
County, so no separate table). City filter is exact-match 'Long Beach'.

Truth-first: returns None / [] when the APN / bbox has no coverage. Never
substitute a placeholder polygon.
"""
from __future__ import annotations

from typing import Any

from google.cloud import bigquery

from api.config import get_settings

_TABLE = "sky-eye-496604.parcels.la_county"
_LOCATION = "us-west1"
_MAX_BYTES = 2_500_000_000  # same ceiling as parcel_lookup.py


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or "sky-eye-496604"
    return bigquery.Client(project=project, location=_LOCATION)


def get_parcel_geometry(apn: str) -> dict[str, Any] | None:
    """Returns {apn, centroid_lat, centroid_lng, geojson, sqft_main,
    use_category, use_subcategory, address_situs, city} or None if APN
    not in LA County.

    use_subcategory is the column the classifier prompt reads. Until the
    Phase 5 forensic pass this column was missing from the SELECT, so
    every Gemini Pro call received an empty 'Existing use:' line —
    silent quality loss on the classifier prompt.
    """
    sql = f"""
    SELECT
      apn,
      ST_Y(ST_CENTROID(geom)) AS centroid_lat,
      ST_X(ST_CENTROID(geom)) AS centroid_lng,
      ST_ASGEOJSON(geom) AS geojson,
      sqft_main,
      use_category,
      use_subcategory,
      address_situs,
      city
    FROM `{_TABLE}`
    WHERE apn = @apn
    LIMIT 1
    """
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("apn", "STRING", apn)],
        maximum_bytes_billed=_MAX_BYTES,
    )
    row = next(iter(_client().query(sql, job_config=cfg).result()), None)
    if row is None:
        return None
    import json
    return {
        "apn": row["apn"],
        "centroid_lat": float(row["centroid_lat"]),
        "centroid_lng": float(row["centroid_lng"]),
        "geojson": json.loads(row["geojson"]) if row["geojson"] else None,
        "sqft_main": row.get("sqft_main"),
        "use_category": row.get("use_category") or "",
        "use_subcategory": row.get("use_subcategory") or "",
        "address_situs": row.get("address_situs") or "",
        "city": row.get("city") or "",
    }


def list_apns_in_bbox(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
    *, residential_only: bool = True, limit: int = 5000,
) -> list[str]:
    """List APNs whose parcel polygon intersects the bbox. Long Beach only.

    `residential_only=True` filters to is_residential parcels — the
    primary TaxLens target (ADU / pool / addition). Set False for the
    commercial flavor later.
    """
    res_clause = "AND is_residential = TRUE" if residential_only else ""
    # The LA County roll writes city as 'LONG BEACH CA' for 103,478 rows
    # ('Long Beach' matches only 86). Without the uppercase literal this
    # query silently returned ~0 candidates — load-bearing silent failure
    # found in the Phase 5 forensic pass. See feedback_parser_contract.
    sql = f"""
    SELECT apn
    FROM `{_TABLE}`
    WHERE city = 'LONG BEACH CA'
      {res_clause}
      AND ST_INTERSECTS(
        geom,
        ST_MAKEPOLYGON(ST_MAKELINE([
          ST_GEOGPOINT(@lon_min, @lat_min),
          ST_GEOGPOINT(@lon_max, @lat_min),
          ST_GEOGPOINT(@lon_max, @lat_max),
          ST_GEOGPOINT(@lon_min, @lat_max),
          ST_GEOGPOINT(@lon_min, @lat_min)
        ]))
      )
    LIMIT @lim
    """
    cfg = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lon_min", "FLOAT64", lon_min),
            bigquery.ScalarQueryParameter("lat_min", "FLOAT64", lat_min),
            bigquery.ScalarQueryParameter("lon_max", "FLOAT64", lon_max),
            bigquery.ScalarQueryParameter("lat_max", "FLOAT64", lat_max),
            bigquery.ScalarQueryParameter("lim", "INT64", limit),
        ],
        maximum_bytes_billed=_MAX_BYTES,
    )
    return [row["apn"] for row in _client().query(sql, job_config=cfg).result()]
