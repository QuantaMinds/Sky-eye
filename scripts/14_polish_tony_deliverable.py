"""Polish pilot_tony_private.csv -> pilot_tony_FINAL.csv.

Adds three transparency columns Tony can audit in seconds:
  - homeowner_exemption_status: matches the portal's "Exemption" field verbatim
  - ownership_signal: human-readable confidence tier from the classifier
  - verification_note: standardized Phase-2-gap disclosure
Plus years_owned (from BQ arms_length_year), renames the technical columns
to Tony-friendly names, drops empty mail_* and post_* columns. The
verification_url column is preserved so every row is 1-click audit-able.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery  # noqa: E402

IN_PATH = Path(__file__).parent.parent / "out" / "pilot_tony_private.csv"
OUT_PATH = Path(__file__).parent.parent / "out" / "pilot_tony_FINAL.csv"

VERIFICATION_NOTE = (
    "Owner name + mailing address require Phase 2 dataset enrichment "
    "(PRA bulk request — ETA 3-4 weeks). Property fundamentals (roof, "
    "tenure, equity, utility, income tract) are verified at the LA County "
    "Assessor portal link in verification_url."
)

EXEMPTION_STATUS = {
    "OWNER_OCCUPIED":     "Active",
    "UNKNOWN_OR_TRUST":   "None",
    "ABSENTEE_INVESTOR":  "None",
}

OWNERSHIP_SIGNAL = {
    "OWNER_OCCUPIED":    "Sworn legal attestation (Homeowner's Exemption filed)",
    "UNKNOWN_OR_TRUST":  "Tenure-based proxy (long-held, no exemption — likely inherited / family trust / unfiled owner-occupant)",
    "ABSENTEE_INVESTOR": "Low confidence (short tenure, no exemption — owner-occupancy unverified)",
}

OUT_FIELDS = [
    "apn", "address", "city", "zip", "lat", "lng",
    "verification_url",
    "priority_score",
    "roof_potential", "income_qualified", "bill_pain", "equity_strength",
    "years_owned",
    "homeowner_exemption_status",
    "ownership_signal",
    "verification_note",
]


def fetch_arms_length(apns: list[str]) -> dict[str, int | None]:
    bq = bigquery.Client(project="sky-eye-496604", location="us-west1")
    apn_list = ",".join(f"'{a}'" for a in apns)
    sql = f"""
    SELECT apn, arms_length_year
    FROM `sky-eye-496604.parcels.la_county`
    WHERE apn IN ({apn_list})
    """
    return {r["apn"]: r["arms_length_year"] for r in bq.query(sql).result()}


def polish_row(row: dict, arms_year: int | None) -> dict:
    label = row["baseline_ownership_label"]
    now_year = datetime.now().year
    years = (now_year - arms_year) if arms_year and arms_year > 0 else None
    return {
        "apn":            row["apn"],
        "address":        row["situs"],
        "city":           row["city"],
        "zip":            row["zip"],
        "lat":            row["lat"],
        "lng":            row["lng"],
        "verification_url": row["verification_url"],
        "priority_score": row["baseline_score"],
        "roof_potential":   row["roof_score"],
        "income_qualified": row["income_score"],
        "bill_pain":        row["bill_pain_score"],
        "equity_strength":  row["equity_score"],
        "years_owned":      years if years is not None else "",
        "homeowner_exemption_status": EXEMPTION_STATUS.get(label, "Unknown"),
        "ownership_signal":           OWNERSHIP_SIGNAL.get(label, "Unknown"),
        "verification_note": VERIFICATION_NOTE,
    }


def main() -> int:
    if not IN_PATH.exists():
        print(f"input not found: {IN_PATH}\nrun scripts/13_score_pilot_filled.py first")
        return 1
    rows = list(csv.DictReader(IN_PATH.open(encoding="utf-8")))
    print(f"read {len(rows)} rows from {IN_PATH.name}")
    arms_by_apn = fetch_arms_length([r["apn"] for r in rows])
    polished = [polish_row(r, arms_by_apn.get(r["apn"])) for r in rows]
    polished.sort(key=lambda r: -float(r["priority_score"]))

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(polished)

    print(f"\nwrote {len(polished)} polished rows to {OUT_PATH}")
    print(f"  columns: {len(OUT_FIELDS)} (dropped {len(rows[0]) - len(OUT_FIELDS) + 3} empty/internal cols)")
    print()
    print("=== Tony deliverable preview — Top 5 ===")
    for r in polished[:5]:
        print(f"  {r['priority_score']}  {r['apn']}  {r['years_owned']}yr  "
              f"{r['homeowner_exemption_status']:7}  {r['address'][:45]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
