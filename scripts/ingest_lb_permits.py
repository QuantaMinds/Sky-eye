"""Long Beach permits ingest CLI.

Drives api.services.permit_ingest in a paginated loop.

The Socrata dataset URL and the field-name mapping are NOT hardcoded here.
Long Beach's open-data portal changes dataset IDs and field names without
warning; baking them in once means quiet drift. Pass them in:

  python scripts/ingest_lb_permits.py \\
      --dataset-url https://data.longbeach.gov/resource/<ID>.json \\
      --mapping fixtures/lb_permits_mapping.json \\
      --pages 10

mapping.json shape: {"our_column": "their_socrata_field", ...}. Keys we
look for (any may be omitted -> NULL in BQ): permit_id, ain, permit_type,
permit_status, application_date, issued_date, finaled_date, description,
estimated_value, zip. See api/services/permit_ingest.py:normalize_row.

Truth-first: rows missing permit_id are dropped (we can't dedupe them).
Rows missing apn are written with apn=NULL; permit_matcher returns
source='unavailable' for those rather than False.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.services import permit_ingest  # noqa: E402

PAGE_SIZE = 1000


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-url", required=True,
                   help="Full Socrata JSON endpoint, e.g. https://data.longbeach.gov/resource/XXXX.json")
    p.add_argument("--mapping", required=True,
                   help="Path to JSON mapping {our_col: socrata_field}")
    p.add_argument("--pages", type=int, default=10,
                   help="Max pages of PAGE_SIZE to fetch (default 10 = 10k rows)")
    p.add_argument("--where",
                   help="Optional Socrata $where clause (e.g. \"issue_date >= '2022-01-01'\")")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch + normalize + log; skip BigQuery write")
    args = p.parse_args()

    mapping_path = Path(args.mapping)
    if not mapping_path.exists():
        print(f"error: mapping file not found: {mapping_path}", file=sys.stderr)
        return 2
    mapping = json.loads(mapping_path.read_text())

    total_fetched = 0
    total_written = 0
    apn_present = 0
    for page in range(args.pages):
        offset = page * PAGE_SIZE
        rows = permit_ingest.fetch_page(
            args.dataset_url, limit=PAGE_SIZE, offset=offset, where=args.where,
        )
        if not rows:
            print(f"page {page}: empty, stopping")
            break
        normalized = [
            permit_ingest.normalize_row(r, mapping, args.dataset_url) for r in rows
        ]
        apn_present += sum(1 for r in normalized if r.get("ain"))
        total_fetched += len(rows)

        if args.dry_run:
            print(f"page {page}: {len(rows)} rows fetched (dry-run, not writing)")
            if page == 0 and normalized:
                print("  sample row (normalized):")
                print("  " + json.dumps(normalized[0], default=str, indent=2)[:1000])
            continue

        written = permit_ingest.upsert_rows(normalized)
        total_written += written
        print(f"page {page}: fetched={len(rows)} written={written}")

    pct_apn = (100 * apn_present / total_fetched) if total_fetched else 0
    print(
        f"\ntotal fetched: {total_fetched}, written: {total_written}, "
        f"rows with apn: {apn_present} ({pct_apn:.1f}%)"
    )
    if pct_apn < 50 and total_fetched > 0:
        print(
            "WARNING: <50% of permits have an APN. permit_matcher will return "
            "source='unavailable' for the others — the confidence pipeline will "
            "drop the permit gate for those parcels (Rule 3)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
