"""Empirical test: does the centroid bbox prefilter actually save bytes,
and how many parcels are at risk of the 'large-parcel edge miss' failure mode?

Two questions:
  Q1 Cost:   does WHERE center_lon/center_lat BETWEEN... reduce bytes scanned
             on top of BQ's native S2-cluster pruning on geom?
  Q2 Risk:   how many parcels have any vertex farther than 0.002 degrees
             from center_lat/center_lon? Those are parcels where a point near
             the edge would be inside the polygon but outside the bbox.
"""
from __future__ import annotations

import time
from google.cloud import bigquery

bq = bigquery.Client(project="sky-eye-496604", location="us-west1")

# Edison Theatre coords from earlier audit (small parcel — easy case)
LAT, LNG = 33.7683013, -118.1887403

# --- Q1: cost comparison ---
print("=" * 72)
print("Q1: Does the centroid bbox prefilter save bytes vs ST_CONTAINS alone?")
print("=" * 72)

QUERY_WITH_BBOX = """
SELECT apn FROM `sky-eye-496604.parcels.la_county`
WHERE center_lon BETWEEN (@lng - 0.002) AND (@lng + 0.002)
  AND center_lat BETWEEN (@lat - 0.002) AND (@lat + 0.002)
  AND ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
LIMIT 1
"""
QUERY_ST_CONTAINS_ONLY = """
SELECT apn FROM `sky-eye-496604.parcels.la_county`
WHERE ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
LIMIT 1
"""

params = [
    bigquery.ScalarQueryParameter("lat", "FLOAT64", LAT),
    bigquery.ScalarQueryParameter("lng", "FLOAT64", LNG),
]

for label, sql in [("WITH bbox + ST_CONTAINS", QUERY_WITH_BBOX),
                   ("ST_CONTAINS only",        QUERY_ST_CONTAINS_ONLY)]:
    # Use dry_run for a clean bytes-processed estimate (no cache contamination)
    cfg = bigquery.QueryJobConfig(query_parameters=params, dry_run=True, use_query_cache=False)
    job = bq.query(sql, job_config=cfg)
    bytes_est = job.total_bytes_processed or 0
    print(f"  {label:30}  estimated bytes processed: {bytes_est:>13,}  "
          f"({bytes_est / 1024 / 1024:>8.1f} MB)")

print()
# Also do real runs and measure wall-clock
print("Real-execution latency (no cache):")
for label, sql in [("WITH bbox + ST_CONTAINS", QUERY_WITH_BBOX),
                   ("ST_CONTAINS only",        QUERY_ST_CONTAINS_ONLY)]:
    cfg = bigquery.QueryJobConfig(query_parameters=params, use_query_cache=False)
    t0 = time.time()
    job = bq.query(sql, job_config=cfg)
    rows = list(job.result())
    elapsed_ms = (time.time() - t0) * 1000
    bytes_actual = job.total_bytes_processed or 0
    print(f"  {label:30}  {elapsed_ms:>6.0f} ms   "
          f"{bytes_actual / 1024 / 1024:>6.1f} MB actual   "
          f"rows={len(rows)}")

print()
print("=" * 72)
print("Q2: How many parcels are at risk of the 'large parcel edge miss'?")
print("=" * 72)
RISK_QUERY = """
WITH bounds AS (
  SELECT apn,
         use_category,
         center_lat, center_lon,
         -- ST_BOUNDINGBOX gives polygon corners; extract max distance from centroid.
         ABS(ST_X(ST_CENTROID(geom)) - center_lon) AS centroid_lng_offset,
         ABS(ST_Y(ST_CENTROID(geom)) - center_lat) AS centroid_lat_offset,
         -- Use the polygon's extent as the worst-case edge distance from centroid.
         -- (Half the bbox-width is the max edge distance for a perfectly centered centroid.)
         (ST_BOUNDINGBOX(geom).xmax - ST_BOUNDINGBOX(geom).xmin) / 2 AS half_width_lng,
         (ST_BOUNDINGBOX(geom).ymax - ST_BOUNDINGBOX(geom).ymin) / 2 AS half_height_lat
  FROM `sky-eye-496604.parcels.la_county`
  WHERE geom IS NOT NULL
)
SELECT
  use_category,
  COUNT(*) AS total,
  COUNTIF(half_width_lng > 0.002 OR half_height_lat > 0.002) AS at_risk_count,
  ROUND(SAFE_DIVIDE(
    COUNTIF(half_width_lng > 0.002 OR half_height_lat > 0.002), COUNT(*)
  ) * 100, 4) AS at_risk_pct
FROM bounds
GROUP BY use_category
ORDER BY at_risk_count DESC
"""
print()
for row in bq.query(RISK_QUERY).result():
    d = dict(row)
    print(f"  {d['use_category']:18}  total={d['total']:>10,}  "
          f"at_risk={d['at_risk_count']:>8,}  ({d['at_risk_pct']}%)")
