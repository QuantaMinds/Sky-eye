"""Create BigQuery datasets in us-west1 for the LA Assessor ingest.

Phase 1.5c — uses the Python SDK (ADC), bypassing the broken gcloud CLI auth.
Idempotent: skips datasets that already exist.

Datasets:
- parcels_raw  : raw ingested data (CSV + GEOJSONL + use_codes)
- parcels      : cleaned, joined, query-ready (parcels.la_county is the main table)
- leadlens     : application data (request logs, future tables for lead scoring)
"""
from __future__ import annotations

import sys

from google.api_core.exceptions import Conflict
from google.cloud import bigquery

PROJECT = "sky-eye-496604"
LOCATION = "us-west1"
DATASETS = [
    ("parcels_raw", "Raw ingested LA County Assessor data (untransformed)"),
    ("parcels", "Cleaned, joined, query-ready parcel data"),
    ("leadlens", "Lead-scoring application data"),
]


def main() -> int:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    print(f"Project: {client.project}  Region: {LOCATION}\n")
    for name, desc in DATASETS:
        ds_id = f"{PROJECT}.{name}"
        ds = bigquery.Dataset(ds_id)
        ds.location = LOCATION
        ds.description = desc
        try:
            ds = client.create_dataset(ds, exists_ok=False)
            print(f"  CREATED  {ds_id}  ({LOCATION})")
        except Conflict:
            existing = client.get_dataset(ds_id)
            print(f"  EXISTS   {ds_id}  (location={existing.location})")
    print()
    print("=== inventory ===")
    for ds in client.list_datasets():
        full = f"{PROJECT}.{ds.dataset_id}"
        d = client.get_dataset(full)
        print(f"  {full}  location={d.location}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
