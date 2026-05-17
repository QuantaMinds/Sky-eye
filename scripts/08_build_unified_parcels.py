"""Build sky-eye-496604.parcels.la_county — unified, cleaned, query-ready.

Phase 1.5c — Step 5. Joins:
  parcels_raw.la_county_attributes  (filtered to latest roll year = 2024)
  parcels_raw.la_county_geometries  (polygon + DBF subset)

On AIN, with the geom table's INTEGER AIN cast to STRING to match.

Applies every guard from infra_bq_and_gdal_patches memory:
  - SAFE_CAST for all type coercions
  - NULLIF(NULLIF(col, '0'), '') for sentinel-zero numeric fields
  - SAFE_CAST WITHOUT NULLIF for home_owners_exemption (0 is meaningful)
  - SAFE.PARSE_DATETIME for the dirty US-locale recording_date string
  - LEAST(land_base_year, improvement_base_year) for Prop 13 tenure

Truth-first: every column is either derived from real data or NULL. No
substitute constants.

Cluster by geom, use_category for the canonical bbox + ST_CONTAINS pattern.
"""
from __future__ import annotations

import sys
import time

from google.cloud import bigquery

PROJECT = "sky-eye-496604"
LOCATION = "us-west1"
TARGET = f"{PROJECT}.parcels.la_county"

SQL = f"""
CREATE OR REPLACE TABLE `{TARGET}`
CLUSTER BY geom, use_category
AS
WITH
  -- Latest roll-year only. The CSV is multi-year; we want one row per APN.
  attr AS (
    SELECT *
    FROM `{PROJECT}.parcels_raw.la_county_attributes`
    WHERE roll_year = '2024'
  ),
  -- Geometry table; cast AIN to STRING so it joins cleanly.
  geom AS (
    SELECT
      CAST(AIN AS STRING) AS apn,
      geometry             AS geom,
      CENTER_LAT           AS center_lat_dbf,
      CENTER_LON           AS center_lon_dbf,
      ST_AREA(geometry)    AS area_m2,
      ST_NUMPOINTS(geometry) AS polygon_vertices
    FROM `{PROJECT}.parcels_raw.la_county_geometries`
    WHERE AIN IS NOT NULL
  )
SELECT
  a.ain AS apn,
  geom.geom,
  geom.center_lat_dbf,
  geom.center_lon_dbf,
  geom.area_m2,
  geom.polygon_vertices,

  -- Pre-baked WGS84 centroid (from CSV; redundant with geom.center_*_dbf but useful).
  SAFE_CAST(a.location_latitude  AS FLOAT64) AS center_lat,
  SAFE_CAST(a.location_longitude AS FLOAT64) AS center_lon,

  -- Address fields.
  a.property_location AS address_situs,
  a.city,
  a.zip_code_1 AS zip,                  -- 5-digit form; zip_code (col 0) has ZIP+4
  a.use_code_1st_digit AS use_category, -- 'Residential', 'Commercial', etc.
  a.use_code_2nd_digit AS use_subcategory,
  a.property_use_code  AS use_code,
  a.property_use_type  AS use_type_short,

  -- Filters.
  a.use_code_1st_digit = 'Residential' AS is_residential,
  a.property_taxable = 'Y'             AS is_taxable,
  CASE
    WHEN a.use_code_1st_digit = 'Residential' AND a.property_taxable = 'Y' THEN 'private'
    WHEN a.use_code_1st_digit = 'Residential' AND a.property_taxable = 'N' THEN 'dac_sash'
    ELSE 'not_residential'
  END AS stream,

  -- Numerics — sentinel-zero NULLIF guard, then SAFE_CAST.
  SAFE_CAST(NULLIF(NULLIF(a.year_built,                   '0'), '') AS INT64)   AS year_built,
  SAFE_CAST(NULLIF(NULLIF(a.square_footage,               '0'), '') AS INT64)   AS sqft_main,
  SAFE_CAST(NULLIF(NULLIF(a.number_of_units,              '0'), '') AS INT64)   AS units,
  SAFE_CAST(NULLIF(NULLIF(a.number_of_bedrooms,           '0'), '') AS INT64)   AS bedrooms,
  SAFE_CAST(NULLIF(NULLIF(a.number_of_bathrooms,          '0'), '') AS INT64)   AS bathrooms,
  SAFE_CAST(NULLIF(NULLIF(a.land_value,                   '0'), '') AS NUMERIC) AS land_value,
  SAFE_CAST(NULLIF(NULLIF(a.improvement_value,            '0'), '') AS NUMERIC) AS improvement_value,
  SAFE_CAST(NULLIF(NULLIF(a.total_value_land_improvement, '0'), '') AS NUMERIC) AS total_value,
  SAFE_CAST(NULLIF(NULLIF(a.land_base_year,               '0'), '') AS INT64)   AS land_base_year,
  SAFE_CAST(NULLIF(NULLIF(a.improvement_base_year,        '0'), '') AS INT64)   AS improvement_base_year,

  -- Homeowner's Exemption — 0 is meaningful ("not claimed"), NO NULLIF.
  SAFE_CAST(a.home_owners_exemption AS NUMERIC) AS homeowners_exemption_amount,
  SAFE_CAST(a.home_owners_exemption AS NUMERIC) > 0 AS has_homeowners_exemption,

  -- Recording date — dirty US-locale string, SAFE.PARSE_DATETIME.
  SAFE.PARSE_DATETIME('%m/%d/%Y %I:%M:%S %p', a.recording_date) AS recording_datetime,
  EXTRACT(YEAR FROM SAFE.PARSE_DATETIME('%m/%d/%Y %I:%M:%S %p', a.recording_date)) AS recording_year,

  -- Prop 13 tenure-start year: older of the two base years (longest tenure wins).
  LEAST(
    COALESCE(SAFE_CAST(NULLIF(NULLIF(a.land_base_year,        '0'), '') AS INT64), 9999),
    COALESCE(SAFE_CAST(NULLIF(NULLIF(a.improvement_base_year, '0'), '') AS INT64), 9999)
  ) AS arms_length_year,

  -- Provenance / debugging.
  a.roll_year AS source_roll_year,
  CURRENT_TIMESTAMP() AS ingested_at
FROM attr a
LEFT JOIN geom ON a.ain = geom.apn
WHERE a.ain IS NOT NULL
"""


def main() -> int:
    bq = bigquery.Client(project=PROJECT, location=LOCATION)
    print(f"Building {TARGET} ...")
    t0 = time.time()
    job = bq.query(SQL)
    job.result()
    elapsed = time.time() - t0

    table = bq.get_table(TARGET)
    print(f"done in {elapsed:.0f}s")
    print(f"  rows:    {table.num_rows:,}")
    print(f"  cols:    {len(table.schema)}")
    print(f"  size:    {table.num_bytes / 1024 / 1024:.0f} MB")
    print(f"  cluster: {table.clustering_fields}")
    print()
    print("Sanity counts:")
    sanity = bq.query(f"""
      SELECT
        COUNT(*) AS total,
        COUNTIF(geom IS NULL) AS missing_geom,
        COUNTIF(is_residential) AS residential,
        COUNTIF(is_residential AND is_taxable) AS res_taxable,
        COUNTIF(is_residential AND NOT is_taxable) AS res_nontaxable,
        COUNTIF(is_residential AND has_homeowners_exemption) AS res_owner_occupied,
        COUNTIF(land_base_year IS NULL) AS null_land_base_year,
        COUNTIF(arms_length_year < 9999) AS has_real_arms_length
      FROM `{TARGET}`
    """).result()
    for row in sanity:
        for k, v in dict(row).items():
            print(f"    {k:30}  {v:,}" if isinstance(v, int) else f"    {k:30}  {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
