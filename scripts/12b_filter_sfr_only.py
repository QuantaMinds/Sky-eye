"""Filter pilot_50_baseline.csv -> pilot_35_sfr_only.csv using BQ-authoritative
canonical fields (units, use_code, sqft_main, is_taxable), not the situs-string
heuristic that missed every apartment-complex parcel in the 2026-05-19 forensic
pass.

The original heuristic looked for " APT ", " UNIT ", " #" markers in the situs
string — apartment-complex parcels list the building's street address with no
unit suffix, so the filter caught 0 of 8 multi-unit parcels in the random
sample. Five contaminated rows (including an 8-unit, 7-unit, 3-unit, and a
171-sqft garbage row) reached pilot_tony_FINAL.csv.

SFR filter (every condition must hold):
  - units = 1                       — BQ canonical unit count
  - use_code = '0100'               — standard SFR; rejects 0106/0109/010D/010E
                                      variants whose use_subcategory lies
  - sqft_main BETWEEN 600 AND 6000  — rejects 171-sqft / 50000-sqft garbage
  - is_taxable = TRUE               — parsonages / university faculty housing
                                      route to dac_sash, not Tony's stream

NULL units treated as suspect (truth-first, [[audit-all-code-paths-for-rule-fixes]]).
Every skip surfaces the actual BQ values so the rejection is auditable.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery  # noqa: E402

IN_PATH = Path(__file__).parent.parent / "out" / "pilot_50_baseline.csv"
OUT_PATH = Path(__file__).parent.parent / "out" / "pilot_35_sfr_only.csv"

SFR_USE_CODE = "0100"
SFR_SQFT_MIN, SFR_SQFT_MAX = 600, 6000


def _fetch_canonical(apns: list[str]) -> dict[str, dict]:
    """One round-trip: canonical SFR-determining fields for every APN.
    QUALIFY dedupes multi-roll-year rows. Mirrors 12_export_pilot_50.py:59
    so both queries see the same row per APN."""
    bq = bigquery.Client(project="sky-eye-496604", location="us-west1")
    apn_list = ",".join(f"'{a}'" for a in apns)
    sql = f"""
    SELECT apn, units, use_code, sqft_main, is_taxable, use_subcategory
    FROM `sky-eye-496604.parcels.la_county`
    WHERE apn IN ({apn_list})
    QUALIFY ROW_NUMBER() OVER (PARTITION BY apn ORDER BY apn) = 1
    """
    return {r["apn"]: dict(r) for r in bq.query(sql).result()}


def _skip_reason(c: dict | None) -> str | None:
    """Return the BQ-grounded reason this APN is NOT an SFR, or None if SFR."""
    if c is None:
        return "APN missing from BQ (data drift)"
    if c["is_taxable"] is False:
        return "is_taxable=FALSE (routes to dac_sash stream, not Tony's pilot)"
    if c["units"] is None:
        return f"units=NULL, use_code={c['use_code']} (suspect — truth-first skip)"
    if c["units"] != 1:
        return f"units={c['units']} ({c.get('use_subcategory') or '?'})"
    if c["use_code"] != SFR_USE_CODE:
        return f"use_code={c['use_code']} (non-standard SFR variant — {c.get('use_subcategory') or '?'})"
    sqft = c["sqft_main"]
    if sqft is None or sqft < SFR_SQFT_MIN or sqft > SFR_SQFT_MAX:
        return f"sqft_main={sqft} (outside {SFR_SQFT_MIN}-{SFR_SQFT_MAX} SFR envelope)"
    return None


def main() -> int:
    if not IN_PATH.exists():
        print(f"input not found: {IN_PATH}")
        return 1
    rows = list(csv.DictReader(IN_PATH.open(encoding="utf-8")))
    canon = _fetch_canonical([r["apn"] for r in rows])

    sfr: list[dict] = []
    skipped: list[tuple[dict, str]] = []
    for r in rows:
        reason = _skip_reason(canon.get(r["apn"]))
        if reason:
            skipped.append((r, reason))
        else:
            sfr.append(r)

    print(f"input:    {len(rows):>3} rows ({IN_PATH.name})")
    print(f"skipped:  {len(skipped):>3} rows (non-SFR per BQ canonical)")
    print(f"SFR pool: {len(sfr):>3} rows -> {OUT_PATH.name}")
    print()
    print("=== skipped (BQ-grounded reason) ===")
    for row, reason in skipped:
        situs = (row.get("situs") or "")[:35]
        print(f"  {row['apn']}  score={row['baseline_score']}  {situs:35}  {reason}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(sfr, key=lambda r: -float(r["baseline_score"])))
    print()
    print(f"wrote {len(sfr)} SFR rows to {OUT_PATH}")
    print("Mail-enrichment columns carry forward from baseline for surviving rows.")
    print("Then run: python scripts/13_score_pilot_filled.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
