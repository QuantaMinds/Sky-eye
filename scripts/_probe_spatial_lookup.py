"""Probe the canonical bbox + ST_CONTAINS lookup pattern."""
import time
from google.cloud import bigquery

bq = bigquery.Client(project="sky-eye-496604", location="us-west1")

LAT, LNG = 33.7683013, -118.1887403  # Edison Theatre from Phase 1.5a audit

SQL = """
SELECT apn, address_situs, use_category, use_subcategory,
       is_residential, is_taxable, stream,
       has_homeowners_exemption, arms_length_year, area_m2
FROM `sky-eye-496604.parcels.la_county`
WHERE center_lon BETWEEN (@lng - 0.002) AND (@lng + 0.002)
  AND center_lat BETWEEN (@lat - 0.002) AND (@lat + 0.002)
  AND ST_CONTAINS(geom, ST_GEOGPOINT(@lng, @lat))
LIMIT 1
"""

cfg = bigquery.QueryJobConfig(query_parameters=[
    bigquery.ScalarQueryParameter("lat", "FLOAT64", LAT),
    bigquery.ScalarQueryParameter("lng", "FLOAT64", LNG),
])

t0 = time.time()
job = bq.query(SQL, job_config=cfg)
rows = list(job.result())
elapsed_ms = (time.time() - t0) * 1000

bytes_processed = job.total_bytes_processed or 0
cost_cents = bytes_processed * 6.25 / (1024 ** 4) * 100
print(f"cold lookup: {elapsed_ms:.0f} ms  bytes: {bytes_processed:,}  cost: {cost_cents:.5f} cents")
print(f"cache hit:   {job.cache_hit}")
print()
if rows:
    for k, v in dict(rows[0]).items():
        print(f"  {k:30} = {v}")
else:
    print("  no parcel contains that point")

# Warm re-run
t0 = time.time()
job2 = bq.query(SQL, job_config=cfg)
list(job2.result())
print(f"\nwarm re-run: {(time.time() - t0) * 1000:.0f} ms  cache_hit={job2.cache_hit}")
