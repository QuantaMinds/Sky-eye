"""Download LA County Assessor parcel data to GCS.

Phase 1.5c — Step 1 of the ingest. Pulls the attribute CSV collection from
ArcGIS Online (item 785f54236d1644dc975a55af19b3dd70) and the parcel geometry
archive to a local staging path, then uploads to gs://satellite-platform-raw/.

Idempotent: skips downloads whose local file already matches the expected size,
re-uploads to GCS if the object is missing or wrong size.

Run with: python scripts/01_download_assessor_data.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import httpx
from google.cloud import storage

PROJECT = "sky-eye-496604"
BUCKET = "satellite-platform-raw"
ROLL_YEAR = 2025
LOCAL_STAGE = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty")
GCS_PREFIX = f"lacounty/{ROLL_YEAR}"

CSV_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    "785f54236d1644dc975a55af19b3dd70/data"
)


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def download(url: str, dest: Path, expected_size: int | None = None) -> Path:
    """Stream download with progress; resumes if local file already matches."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if expected_size and dest.exists() and dest.stat().st_size == expected_size:
        print(f"  [skip] {dest.name} already at {_human(expected_size)}")
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or expected_size or 0)
        start = time.time()
        downloaded = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start
                rate = downloaded / elapsed if elapsed > 0 else 0
                pct = f"{100 * downloaded / total:5.1f}%" if total else "  ?  "
                print(
                    f"\r  {dest.name}  {_human(downloaded)} / {_human(total) if total else '?'}  "
                    f"{pct}  {_human(int(rate))}/s",
                    end="", flush=True,
                )
    print()
    tmp.replace(dest)
    return dest


def upload(local: Path, bucket: str, key: str) -> None:
    client = storage.Client(project=PROJECT)
    b = client.bucket(bucket)
    blob = b.blob(key)
    if blob.exists() and blob.size == local.stat().st_size:
        print(f"  [skip] gs://{bucket}/{key} already at {_human(local.stat().st_size)}")
        return
    print(f"  upload {local.name} -> gs://{bucket}/{key} ...")
    blob.upload_from_filename(str(local), timeout=600)
    print(f"  done   {_human(blob.size)} in GCS")


def main() -> int:
    csv_local = LOCAL_STAGE / "assessor_parcel_data.zip"
    print(f"[1/2] Download attribute CSV collection ({CSV_URL[:80]}...)")
    download(CSV_URL, csv_local, expected_size=673_759_681)

    print(f"\n[2/2] Upload to gs://{BUCKET}/{GCS_PREFIX}/")
    upload(csv_local, BUCKET, f"{GCS_PREFIX}/assessor_parcel_data.zip")

    # Geometry archive deferred — direct download URLs return HTML wrappers.
    # See scripts/01b_resolve_geometry.py for ongoing investigation.
    print("\n[geometry] DEFERRED — see scripts/01b_resolve_geometry.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
