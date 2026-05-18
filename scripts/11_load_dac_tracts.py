"""Load LA County SB-535 DAC tracts to BigQuery.

Phase 1.5e. Pulls the 1,173 LA County census-tract polygons from OEHHA's
SB 535 Disadvantaged Communities feature service (Tribal update 2023/2024)
and loads them into parcels_raw.dac_tracts.

The `Tract` field on the source is a 10-digit numeric GEOID (state+county+
6-digit tract). LA County filter: 6037000000 <= Tract <= 6037999999.

Source: OEHHA Kelsey.Ranjbar item 15b93bb7650943dab83038359b6240ec, layer 1
"""
from __future__ import annotations

import json
import sys

import httpx
from google.cloud import bigquery

PROJECT = "sky-eye-496604"
TABLE_ID = f"{PROJECT}.parcels_raw.dac_tracts"

SOURCE_URL = (
    "https://services1.arcgis.com/PCHfdHz4GlDNAhBb/arcgis/rest/services/"
    "SB535_DACupdate20232024/FeatureServer/1/query"
)
LA_FILTER = "Tract >= 6037000000 AND Tract <= 6037999999"

SCHEMA = [
    bigquery.SchemaField("tract_geoid", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("zip", "STRING"),
    bigquery.SchemaField("population", "INTEGER"),
    bigquery.SchemaField("ces_score", "FLOAT"),
    bigquery.SchemaField("ces_percentile", "FLOAT"),
    bigquery.SchemaField("geom", "GEOGRAPHY", mode="REQUIRED"),
    bigquery.SchemaField("source_url", "STRING"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP"),
]


def fetch_la_dac_tracts() -> list[dict]:
    """Paginate through all LA County DAC tracts, returning GeoJSON features."""
    all_features: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        r = httpx.get(SOURCE_URL, params={
            "where": LA_FILTER,
            "outFields": "Tract,ZIP,Population,CIscore,CIscoreP",
            "returnGeometry": "true", "f": "geojson",
            "outSR": 4326,
            "resultRecordCount": page_size,
            "resultOffset": offset,
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features") or []
        if not feats:
            break
        all_features.extend(feats)
        offset += len(feats)
        print(f"  fetched {len(all_features)} so far ...")
        if len(feats) < page_size:
            break
    return all_features


def main() -> int:
    bq = bigquery.Client(project=PROJECT, location="us-west1")

    print(f"(Re)creating {TABLE_ID} ...")
    bq.delete_table(TABLE_ID, not_found_ok=True)
    bq.create_table(bigquery.Table(TABLE_ID, schema=SCHEMA))

    print("Fetching LA County DAC tracts from OEHHA...")
    feats = fetch_la_dac_tracts()
    print(f"  total: {len(feats)} features")
    if not feats:
        print("  ERROR: no features returned")
        return 1

    # Build rows for ST_GEOGFROMGEOJSON insert. Use a per-batch INSERT to keep
    # payload size reasonable; ~1200 polygons fit in one shot.
    print(f"Inserting {len(feats)} tracts via ST_GEOGFROMGEOJSON ...")
    structs = []
    params = []
    for i, feat in enumerate(feats):
        props = feat.get("properties") or {}
        tract = props.get("Tract")
        geom_json = json.dumps(feat["geometry"])
        params.append(bigquery.ScalarQueryParameter(f"g{i}", "STRING", geom_json))
        structs.append(
            f"STRUCT('{int(tract)}' AS tract_geoid, "
            f"{repr(props.get('ZIP') or '')} AS zip, "
            f"{int(props.get('Population') or 0)} AS population, "
            f"{float(props.get('CIscore') or 0)} AS ces_score, "
            f"{float(props.get('CIscoreP') or 0)} AS ces_percentile, "
            f"@g{i} AS geom_json)"
        )

    insert_sql = f"""
    INSERT INTO `{TABLE_ID}` (tract_geoid, zip, population, ces_score, ces_percentile,
                              geom, source_url, ingested_at)
    SELECT tract_geoid, zip, population, ces_score, ces_percentile,
           ST_GEOGFROMGEOJSON(geom_json, make_valid => TRUE) AS geom,
           '{SOURCE_URL}' AS source_url,
           CURRENT_TIMESTAMP() AS ingested_at
    FROM UNNEST([{', '.join(structs)}])
    """
    job = bq.query(insert_sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    print(f"  inserted {job.num_dml_affected_rows} rows")

    # Verify + spot-check Boyle Heights
    print("\nVerifying:")
    for row in bq.query(f"""
        SELECT COUNT(*) AS total, MIN(ces_percentile) AS min_p, MAX(ces_percentile) AS max_p,
               AVG(ces_percentile) AS mean_p
        FROM `{TABLE_ID}`
    """).result():
        print(f"  rows={row.total:,}  CES percentile: min={row.min_p:.2f} mean={row.mean_p:.2f} max={row.max_p:.2f}")

    print("\nTop 3 LA County DAC tracts by CES percentile:")
    for row in bq.query(f"""
        SELECT tract_geoid, zip, population, ces_percentile,
               ST_ASTEXT(ST_CENTROID(geom)) AS centroid
        FROM `{TABLE_ID}` ORDER BY ces_percentile DESC LIMIT 3
    """).result():
        print(f"  {row.tract_geoid}  zip={row.zip}  pop={row.population:,}  "
              f"ces_p={row.ces_percentile:.2f}  centroid={row.centroid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
