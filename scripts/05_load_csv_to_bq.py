"""Load LA County Assessor CSV into BigQuery (parcels_raw.la_county_attributes_2025).

Phase 1.5c — Step that follows dataset creation. Three sub-steps:
  1. Stream-extract Parcel_Data_0.csv out of the local ZIP, gzip on the fly.
     (~4 GB CSV -> ~700 MB gzip; saves both disk and GCS upload time.)
  2. Upload the gzipped CSV to gs://satellite-platform-raw/lacounty/2025/.
  3. Trigger a BigQuery load job (CSV.gz, all columns STRING).

Idempotent: skips steps whose outputs already exist with matching size.
"""
from __future__ import annotations

import gzip
import sys
import time
import zipfile
from pathlib import Path

from google.cloud import bigquery, storage

PROJECT = "sky-eye-496604"
BUCKET = "satellite-platform-raw"
DATASET = "parcels_raw"
# No year suffix — roll_year is a COLUMN inside the data, not table metadata.
# Future re-ingests overwrite this single table; script 07 filters to
# WHERE roll_year = (SELECT MAX(roll_year) FROM ...) for latest-wins.
TABLE = "la_county_attributes"

LOCAL_ZIP = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\assessor_parcel_data.zip")
LOCAL_GZ = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\assessor_parcel_data.csv.gz")
GCS_KEY = "lacounty/2025/assessor_parcel_data.csv.gz"
GCS_URI = f"gs://{BUCKET}/{GCS_KEY}"


def step_1_gzip_local() -> None:
    if LOCAL_GZ.exists() and LOCAL_GZ.stat().st_size > 0:
        print(f"[1/3] skip gzip: {LOCAL_GZ} already at "
              f"{LOCAL_GZ.stat().st_size / 1024 / 1024:.1f} MB")
        return
    print(f"[1/3] streaming gzip extract -> {LOCAL_GZ.name}")
    t0 = time.time()
    bytes_in = 0
    with zipfile.ZipFile(LOCAL_ZIP) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as src, gzip.open(LOCAL_GZ, "wb", compresslevel=6) as dst:
            while True:
                chunk = src.read(1 << 22)  # 4 MB
                if not chunk:
                    break
                dst.write(chunk)
                bytes_in += len(chunk)
                if bytes_in % (256 << 20) == 0:  # log every 256 MB
                    print(f"    read {bytes_in / 1024 / 1024:.0f} MB...")
    elapsed = time.time() - t0
    out_mb = LOCAL_GZ.stat().st_size / 1024 / 1024
    print(f"    done in {elapsed:.0f}s; gzipped to {out_mb:.0f} MB "
          f"({100 * out_mb / (bytes_in / 1024 / 1024):.0f}% of uncompressed)")


def step_2_upload() -> None:
    storage_client = storage.Client(project=PROJECT)
    blob = storage_client.bucket(BUCKET).blob(GCS_KEY)
    if blob.exists() and blob.size == LOCAL_GZ.stat().st_size:
        print(f"[2/3] skip upload: {GCS_URI} already at {blob.size / 1024 / 1024:.0f} MB")
        return
    print(f"[2/3] uploading {LOCAL_GZ.name} -> {GCS_URI}")
    t0 = time.time()
    blob.upload_from_filename(str(LOCAL_GZ), timeout=3600)
    print(f"    done in {time.time() - t0:.0f}s")


def step_3_bq_load() -> None:
    bq = bigquery.Client(project=PROJECT, location="us-west1")
    table_id = f"{PROJECT}.{DATASET}.{TABLE}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        # All columns STRING — let the unified-table SQL do casts. Avoids
        # coercion failures on dirty data per the plan's Section 2.1.
        autodetect=False,
        schema=_sanitized_string_schema(),
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        allow_quoted_newlines=True,
        allow_jagged_rows=False,
        max_bad_records=100,  # tolerate a small number of dirty rows
    )

    print(f"[3/3] BQ load: {GCS_URI} -> {table_id}")
    t0 = time.time()
    job = bq.load_table_from_uri(GCS_URI, table_id, job_config=job_config)
    print(f"    job id: {job.job_id}")
    print(f"    waiting (this may take 1-5 min for 4 GB CSV.gz)...")
    job.result()  # blocks until done
    elapsed = time.time() - t0

    table = bq.get_table(table_id)
    print(f"    done in {elapsed:.0f}s")
    print(f"    rows: {table.num_rows:,}")
    print(f"    columns: {len(table.schema)}")
    if job.errors:
        print(f"    job errors: {job.errors[:5]}")


def _sanitized_string_schema() -> list[bigquery.SchemaField]:
    """51 columns from the inspected CSV header, sanitized to snake_case."""
    raw_names = [
        "Zip Code", "City Tax Rate Area", "AIN", "Roll Year", "Tax Rate Area Code",
        "Assessor ID", "Property Location", "Property Use Type", "Property Use Code",
        "Use Code 1st Digit", "Use Code 2nd Digit", "Use Code 3rd Digit", "Use Code 4th Digit",
        "Number of Buildings", "Year Built", "Effective Year", "Square Footage",
        "Number of Bedrooms", "Number of Bathrooms", "Number of Units", "Recording Date",
        "Land Value", "Land Base Year", "Improvement Value", "Improvement Base Year",
        "Total Value Land Improvement", "Home Owners Exemption", "Real Estate Exemption",
        "Fixture Value", "Fixture Exemption", "Personal Property Value", "Personal Property Exemption",
        "Property taxable?", "Total Value", "Total Exemption", "Taxable Value",
        "Classification", "Region Number", "Cluster Code", "Parcel Legal Description",
        "Address House Number", "Address House Number Fraction", "Direction", "Street",
        "Unit Number", "City", "Zip Code", "Row ID", "Location Latitude",
        "Location Longitude", "OBJECTID",
    ]
    sanitized = _make_unique([_sanitize(n) for n in raw_names])
    return [bigquery.SchemaField(name, "STRING", mode="NULLABLE") for name in sanitized]


def _sanitize(name: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in name).strip("_").lower()
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe


def _make_unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def main() -> int:
    step_1_gzip_local()
    step_2_upload()
    step_3_bq_load()
    print("\nDONE. inspect with:")
    print(f"  bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.{TABLE}`'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
