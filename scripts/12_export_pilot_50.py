"""Phase 1.5c.2b pilot export: 50 LB residential **NON-EXEMPT** parcels,
fully baseline-scored (real Solar/Census/NREL/utility/DAC) and ordered by
descending score for the manual mailing-enrichment workflow.

WHY NON-EXEMPT: the 4-tier classifier short-circuits at Tier 1 for any
parcel with has_homeowners_exemption=TRUE -> returns OWNER_OCCUPIED 0.95
and skips every Tier 2-7 branch. Sampling exempt parcels would produce a
0.00 delta across all 50 rows. The non-exempt cohort is where the
corporate / out-of-state / family-trust / situs-match signal actually
fires — the only sample population that exercises the classifier.

Workflow:
  1. Run this -> writes out/pilot_50_baseline.csv (50 non-exempt rows, sorted)
  2. Open the CSV side-by-side with portal.assessor.lacounty.gov
  3. For each row top-down: open verification_url, copy owner_name +
     mailing_address into the three empty columns, stamp enrichment_timestamp
  4. ** SAVE EVERY 10 ROWS ** (Excel crashes happen)
  5. ** 20-MINUTE TIMER ** — ship 30 enriched > fight for 50
  6. Run scripts/13_score_pilot_filled.py to apply the 4-tier classifier

Solar API: 50 calls x $0.10 = ~$5. Acceptable for pilot delivery.
"""
from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery  # noqa: E402

from api.services import census, dac, nrel, parcel_lookup, solar_api, utility  # noqa: E402
from api.services.dimensions._ownership_classifier import (  # noqa: E402
    LABEL_TO_TIER,
    determine_ownership_profile,
)
from api.services.scoring import compute_score  # noqa: E402

PORTAL_BASE = "https://portal.assessor.lacounty.gov/parceldetail"
OUT_PATH = Path(__file__).parent.parent / "out" / "pilot_50_baseline.csv"

SAMPLE_SQL = """
-- Non-exempt LB residential parcels — the cohort where the 4-tier
-- classifier's Tiers 2-7 actually fire. Filter by ZIP (the city column has
-- formatting variants), and dedupe by APN with QUALIFY since the unified
-- table carries multiple roll-year rows per AIN.
SELECT apn, address_situs, city, zip, center_lat, center_lon
FROM `sky-eye-496604.parcels.la_county`
WHERE is_residential = TRUE
  AND is_taxable = TRUE
  AND has_homeowners_exemption = FALSE
  AND zip IN ('90802','90803','90804','90805','90806','90807','90808','90813','90814','90815')
  AND geom IS NOT NULL
  AND center_lat IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY apn ORDER BY apn) = 1
ORDER BY RAND()
LIMIT 50
"""

CSV_FIELDS = [
    "apn", "situs", "city", "zip", "lat", "lng", "verification_url",
    "baseline_score", "baseline_ownership_tier", "baseline_ownership_label",
    "baseline_stream",
    "roof_score", "income_score", "bill_pain_score",
    "equity_score", "ownership_score_baseline",
    "mail_owner_name", "mail_full_address", "mail_state", "enrichment_timestamp",
]


def _val(dim) -> str:
    return f"{dim.value:.4f}" if dim.value is not None else ""


async def score_one(p: dict) -> dict | None:
    lat, lng = float(p["center_lat"]), float(p["center_lon"])
    address = f"{p['address_situs']} {p['city']} CA {p['zip']}"
    (roof, _), (cens, _), (pv, _), (parcel, _), (util, _), (dac_info, _) = await asyncio.gather(
        solar_api.get_roof_data(lat, lng, address),
        census.get_block_group_data(lat, lng),
        nrel.get_production(lat, lng),
        parcel_lookup.lookup_by_point(lat, lng),
        utility.lookup_by_point(lat, lng),
        dac.lookup_by_point(lat, lng),
    )
    if parcel is None:
        return None
    score, dims, _, _ = compute_score(roof, cens, pv, parcel, util, dac_info)
    label, _ = determine_ownership_profile(parcel, scraped_mail_data=None)
    return {
        "apn": parcel.apn, "situs": parcel.address_situs,
        "city": parcel.city, "zip": parcel.zip, "lat": lat, "lng": lng,
        "verification_url": f"{PORTAL_BASE}/{parcel.apn}",
        "baseline_score": f"{score:.4f}",
        "baseline_ownership_tier": LABEL_TO_TIER[label],
        "baseline_ownership_label": label,
        "baseline_stream": parcel.stream,
        "roof_score": _val(dims.roof_potential),
        "income_score": _val(dims.income_qualification),
        "bill_pain_score": _val(dims.bill_pain),
        "equity_score": _val(dims.equity_proxy),
        "ownership_score_baseline": _val(dims.ownership),
        "mail_owner_name": "", "mail_full_address": "",
        "mail_state": "", "enrichment_timestamp": "",
    }


async def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bq = bigquery.Client(project="sky-eye-496604", location="us-west1")
    parcels = [dict(r) for r in bq.query(SAMPLE_SQL).result()]
    print(f"sampled {len(parcels)} LB residential exempt parcels", flush=True)
    rows: list[dict] = []
    for i, p in enumerate(parcels, 1):
        try:
            r = await asyncio.wait_for(score_one(p), 90.0)
            if r is not None:
                rows.append(r)
                print(f"  [{i:2}/{len(parcels)}] {r['apn']}  score={r['baseline_score']}", flush=True)
        except Exception as exc:
            print(f"  [{i:2}/{len(parcels)}] FAIL {p['apn']}: {type(exc).__name__}: {str(exc)[:60]}", flush=True)
    rows.sort(key=lambda r: -float(r["baseline_score"]))
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} rows to {OUT_PATH}", flush=True)
    print("Next: fill mail_owner_name / mail_full_address / mail_state / enrichment_timestamp", flush=True)
    print("      SAVE EVERY 10 ROWS. 20-MIN TIMER. Then run scripts/13_score_pilot_filled.py", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
