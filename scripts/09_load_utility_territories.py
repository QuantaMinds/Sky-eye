"""Load utility service territories into BigQuery.

Phase 1.5d. Two polygons:
  1. SCE   — from CPUC Utility_Territory FeatureServer layer 2 (Electric IOU)
              filtered to Acronym='SCE'. Authoritative for IOU coverage.
  2. LADWP — proxied via the LA County DRP "City Of Los Angeles Boundary"
              feature service. LADWP is municipal (not in CPUC layer).
              Phase 1.5d.2 will replace with the real LADWP polygon.

Each row in `parcels_raw.utility_territories`: (utility_name, geom, source_url,
ingested_at). Both polygons are normalized to WGS84 (4326) before insert.
"""
from __future__ import annotations

import json
import sys

import httpx
from google.cloud import bigquery

PROJECT = "sky-eye-496604"
DATASET = "parcels_raw"
TABLE = "utility_territories"
TABLE_ID = f"{PROJECT}.{DATASET}.{TABLE}"

SCE_URL = ("https://services2.arcgis.com/VofPZYDe2pLxSP5G/arcgis/rest/services/"
           "Utility_Territory/FeatureServer/2/query")
LA_CITY_URL = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
               "admin_dist_SDE_DIST_DRP_CITY_COMM_BDY/FeatureServer/0/query")

SCHEMA = [
    bigquery.SchemaField("utility_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("geom", "GEOGRAPHY", mode="REQUIRED"),
    bigquery.SchemaField("source_url", "STRING"),
    bigquery.SchemaField("source_note", "STRING"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]


def fetch_geojson(url: str, where: str) -> dict:
    params = {
        "where": where, "outFields": "*", "returnGeometry": "true",
        "f": "geojson", "outSR": 4326,
    }
    r = httpx.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> int:
    bq = bigquery.Client(project=PROJECT, location="us-west1")

    print("Creating / truncating parcels_raw.utility_territories ...")
    table = bigquery.Table(TABLE_ID, schema=SCHEMA)
    bq.delete_table(TABLE_ID, not_found_ok=True)
    bq.create_table(table)

    print("Fetching SCE polygon (CPUC IOU layer 2)...")
    sce = fetch_geojson(SCE_URL, "Acronym = 'SCE'")
    feats = sce.get("features") or []
    print(f"  features returned: {len(feats)}")
    if not feats:
        print("  ERROR: no SCE feature returned")
        return 1
    sce_geojson = json.dumps(feats[0]["geometry"])

    print("Fetching LA City polygon (LADWP proxy, LA County DRP)...")
    # DRP layer schema: CITYNAME_ALF is the city name; JURISDICTION filters
    # out unincorporated areas/communities/islands.
    la = fetch_geojson(
        LA_CITY_URL,
        "CITYNAME_ALF = 'LOS ANGELES' AND JURISDICTION = 'INCORPORATED CITY'",
    )
    feats = la.get("features") or []
    print(f"  features returned: {len(feats)}")
    if not feats:
        print("  ERROR: no LA City feature returned — check DRP layer schema")
        return 1
    la_geojson = json.dumps(feats[0]["geometry"])

    # GEOGRAPHY columns can't be set via insert_rows_json (no WKT/GeoJSON
    # auto-conversion). Use INSERT ... SELECT with ST_GEOGFROMGEOJSON.
    print("Inserting via INSERT ... ST_GEOGFROMGEOJSON ...")
    insert_sql = f"""
    INSERT INTO `{TABLE_ID}` (utility_name, geom, source_url, source_note, ingested_at)
    SELECT
      utility_name,
      ST_GEOGFROMGEOJSON(geom_json, make_valid => TRUE) AS geom,
      source_url, source_note, CURRENT_TIMESTAMP()
    FROM UNNEST([
      STRUCT(
        'SCE' AS utility_name,
        @sce_geom AS geom_json,
        @sce_url AS source_url,
        'CPUC Utility_Territory layer 2 (Electric IOU); authoritative' AS source_note
      ),
      STRUCT(
        'LADWP' AS utility_name,
        @la_geom AS geom_json,
        @la_url AS source_url,
        ('LA County DRP City-of-LA boundary used as LADWP proxy. LADWP is '
         'municipal — not in CPUC IOU layer. Phase 1.5d.2 to replace with '
         'real LADWP polygon.') AS source_note
      )
    ])
    """
    job = bq.query(insert_sql, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("sce_geom", "STRING", sce_geojson),
        bigquery.ScalarQueryParameter("la_geom",  "STRING", la_geojson),
        bigquery.ScalarQueryParameter("sce_url",  "STRING", SCE_URL),
        bigquery.ScalarQueryParameter("la_url",   "STRING", LA_CITY_URL),
    ]))
    job.result()
    print(f"  inserted {job.num_dml_affected_rows} rows")

    # Sanity-check via direct query
    print("\nVerifying load:")
    for row in bq.query(f"""
        SELECT utility_name,
               ST_AREA(geom) AS area_m2,
               ST_NUMPOINTS(geom) AS n_vertices
        FROM `{TABLE_ID}` ORDER BY utility_name
    """).result():
        print(f"  {row.utility_name:8}  area_km2={row.area_m2 / 1_000_000:>10.0f}  vertices={row.n_vertices}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
