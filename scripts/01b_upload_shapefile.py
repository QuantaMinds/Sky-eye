"""Upload the local parcels.zip shapefile archive to GCS.

Phase 1.5c — sister to script 01. Browser-downloaded; this just uploads.
"""
from __future__ import annotations

import sys
from pathlib import Path

from google.cloud import storage

PROJECT = "sky-eye-496604"
BUCKET = "satellite-platform-raw"
LOCAL = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\parcels.zip")
KEY = "lacounty/2025/parcels.zip"


def main() -> int:
    if not LOCAL.exists():
        print(f"ERROR: {LOCAL} not found")
        return 1
    size_mb = LOCAL.stat().st_size / (1024 * 1024)
    print(f"local: {LOCAL}  ({size_mb:.1f} MB)")
    client = storage.Client(project=PROJECT)
    blob = client.bucket(BUCKET).blob(KEY)
    if blob.exists() and blob.size == LOCAL.stat().st_size:
        print(f"[skip] gs://{BUCKET}/{KEY} already at {blob.size / 1024 / 1024:.1f} MB")
        return 0
    print(f"upload -> gs://{BUCKET}/{KEY} ...")
    blob.upload_from_filename(str(LOCAL), timeout=1800)
    print(f"done   {blob.size / 1024 / 1024:.1f} MB in GCS  md5={blob.md5_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
