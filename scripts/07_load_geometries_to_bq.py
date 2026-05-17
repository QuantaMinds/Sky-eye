"""Load LA County parcel geometries into BigQuery.

Phase 1.5c — sister to script 05 (CSV load). Three sub-steps:
  1. Gzip the reprojected NDJSON locally (2.7 GB -> ~500-700 MB).
  2. Upload the .jsonl.gz to gs://satellite-platform-raw/.
  3. BigQuery load: GeoJSON Features -> parcels_raw.la_county_geometries
     with native GEOGRAPHY type (via --json_extension=GEOJSON equivalent
     in the Python SDK = `parse_geojson=True`).

Idempotent: skips steps whose outputs already exist.
"""
from __future__ import annotations

import gzip
import shutil
import sys
import time
from pathlib import Path

from google.cloud import bigquery, storage

PROJECT = "sky-eye-496604"
BUCKET = "satellite-platform-raw"
DATASET = "parcels_raw"
TABLE = "la_county_geometries"

LOCAL_JSONL = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\parcels.jsonl")
LOCAL_GZ = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\parcels.jsonl.gz")
GCS_KEY = "lacounty/2025/parcels.jsonl.gz"
GCS_URI = f"gs://{BUCKET}/{GCS_KEY}"


def _human(n: int) -> str:
    return f"{n / 1024 / 1024:.0f} MB" if n < 1 << 30 else f"{n / 1024 / 1024 / 1024:.2f} GB"


def step_1_gzip() -> None:
    if not LOCAL_JSONL.exists():
        print(f"ERROR: {LOCAL_JSONL} not found. Run scripts/03_reproject_shapefile.sh first.")
        sys.exit(1)
    if LOCAL_GZ.exists() and LOCAL_GZ.stat().st_size > 0:
        print(f"[1/3] skip gzip: {LOCAL_GZ.name} already at {_human(LOCAL_GZ.stat().st_size)}")
        return
    print(f"[1/3] gzipping {LOCAL_JSONL.name} ({_human(LOCAL_JSONL.stat().st_size)}) -> .gz")
    t0 = time.time()
    with LOCAL_JSONL.open("rb") as src, gzip.open(LOCAL_GZ, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=4 << 20)
    print(f"    done in {time.time() - t0:.0f}s; "
          f"gz size {_human(LOCAL_GZ.stat().st_size)}")


def step_2_upload() -> None:
    client = storage.Client(project=PROJECT)
    blob = client.bucket(BUCKET).blob(GCS_KEY)
    if blob.exists() and blob.size == LOCAL_GZ.stat().st_size:
        print(f"[2/3] skip upload: {GCS_URI} already at {_human(blob.size)}")
        return
    print(f"[2/3] uploading {LOCAL_GZ.name} -> {GCS_URI}")
    t0 = time.time()
    blob.upload_from_filename(str(LOCAL_GZ), timeout=3600)
    print(f"    done in {time.time() - t0:.0f}s")


def step_3_bq_load() -> None:
    bq = bigquery.Client(project=PROJECT, location="us-west1")
    table_id = f"{PROJECT}.{DATASET}.{TABLE}"

    # The NDJSON file is one GeoJSON Feature per line. BigQuery natively
    # ingests this via NEWLINE_DELIMITED_JSON + json_extension="GEOJSON".
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        json_extension="GEOJSON",
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        max_bad_records=100,
    )

    print(f"[3/3] BQ load: {GCS_URI} -> {table_id}")
    t0 = time.time()
    job = bq.load_table_from_uri(GCS_URI, table_id, job_config=job_config)
    print(f"    job id: {job.job_id}")
    print(f"    waiting (NDJSON.gz parse + GEOGRAPHY validation takes a few min)...")
    job.result()
    elapsed = time.time() - t0

    table = bq.get_table(table_id)
    print(f"    done in {elapsed:.0f}s")
    print(f"    rows: {table.num_rows:,}")
    print(f"    cols: {len(table.schema)}")
    print(f"    schema: {[(f.name, f.field_type) for f in table.schema[:8]]}")
    if job.errors:
        print(f"    job errors: {job.errors[:5]}")


def main() -> int:
    step_1_gzip()
    step_2_upload()
    step_3_bq_load()
    print("\nDONE. inspect with:")
    print(f"  SELECT COUNT(*), ST_ISVALID(geometry) AS valid FROM `{PROJECT}.{DATASET}.{TABLE}` GROUP BY 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
