"""Inspect the downloaded LA County Assessor CSV archive.

Phase 1.5c — Step 2a. Opens the zipped CSV collection, peeks at file inventory
and the first ~1000 rows of each CSV, and prints column names so we can build
the BigQuery LOAD schema accurately.

Truth-first: this script reads only. Nothing uploaded, nothing modified.
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

ZIP_PATH = Path(r"D:\EYE-Lead\Sky-eye\.stage\lacounty\assessor_parcel_data.zip")
SAMPLE_ROWS = 1_000


def main() -> int:
    if not ZIP_PATH.exists():
        print(f"ERROR: archive not found at {ZIP_PATH}")
        return 1
    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"Archive: {ZIP_PATH}  ({size_mb:.0f} MB)\n")

    with zipfile.ZipFile(ZIP_PATH) as zf:
        members = zf.namelist()
        print(f"=== contents ({len(members)} entries) ===")
        for m in members:
            info = zf.getinfo(m)
            print(f"  {info.file_size:>14,} bytes  {m}")
        print()

        csvs = [m for m in members if m.lower().endswith(".csv")]
        if not csvs:
            print("ERROR: no CSV files inside the archive.")
            return 1

        for csv_name in csvs:
            print(f"=== {csv_name} ===")
            with zf.open(csv_name) as raw:
                # Decode utf-8 with bom-tolerance
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.reader(text)
                try:
                    header = next(reader)
                except StopIteration:
                    print("  (empty)")
                    continue
                print(f"  columns ({len(header)}):")
                for i, col in enumerate(header):
                    print(f"    [{i:3}] {col}")
                # Sample first row to show actual data shape
                try:
                    sample = next(reader)
                    print(f"  first data row:")
                    for col, val in zip(header, sample):
                        s = (val or "")[:60]
                        print(f"    {col:30} = {s!r}")
                except StopIteration:
                    print("  (no data rows)")
                # Count remaining sample rows
                seen = 2  # header + first data row
                for _ in reader:
                    seen += 1
                    if seen >= SAMPLE_ROWS:
                        break
                print(f"  (sampled at least {seen} rows; not counting full file)")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
