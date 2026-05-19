"""Filter pilot_50_baseline.csv -> pilot_35_sfr_only.csv by stripping rows
whose situs contains a unit marker (NO / APT / UNIT / PENT / PH / STE).

Why: ST_CONTAINS-based parcel lookup against a multi-unit polygon returns
a sibling AIN, not the queried AIN — so the ParcelData (and therefore the
exemption status) may not match the sampled APN. Beyond the lookup
ambiguity, condo/apartment unit owners don't own their roof — they're
non-viable for a private solar installer pilot. Phase 1.5c.3 will add
unit-aware spatial resolution; until then, filter at the post-export step.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

IN = Path(__file__).parent.parent / "out" / "pilot_50_baseline.csv"
OUT = Path(__file__).parent.parent / "out" / "pilot_35_sfr_only.csv"

UNIT_MARKERS = (
    " NO ", " APT ", " UNIT ", " PENT", " PH ", " PH1", " PH2", " PH3",
    " STE ", " SUITE ", " #",
    ", NO ", ", APT ", ", UNIT ", ", PENT", ", PH",
)


def _has_unit_marker(situs: str) -> bool:
    s = (situs or "").upper()
    return any(m in s for m in UNIT_MARKERS)


def main() -> int:
    if not IN.exists():
        print(f"input not found: {IN}")
        return 1
    rows = list(csv.DictReader(IN.open(encoding="utf-8")))
    sfr = [r for r in rows if not _has_unit_marker(r["situs"])]
    skipped = [r for r in rows if _has_unit_marker(r["situs"])]

    print(f"input:    {len(rows):>3} rows ({IN.name})")
    print(f"skipped:  {len(skipped):>3} rows (multi-unit, see below)")
    print(f"SFR pool: {len(sfr):>3} rows -> {OUT.name}")
    print()
    print("=== skipped (multi-unit, Tony cannot service) ===")
    for r in skipped:
        print(f"  {r['apn']}  score={r['baseline_score']}  zip={r['zip']}  {r['situs']}")

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(sfr, key=lambda r: -float(r["baseline_score"])))
    print()
    print(f"wrote {len(sfr)} SFR rows to {OUT}")
    print("Now fill mail_owner_name / mail_full_address / mail_state / enrichment_timestamp on those 35")
    print("Then run: python scripts/13_score_pilot_filled.py  (point it at the SFR-only file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
