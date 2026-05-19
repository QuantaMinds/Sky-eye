"""Phase 1.5c.2b pilot re-score: applies the 4-tier ownership classifier
to the manually-enriched mailing data from out/pilot_50_baseline.csv and
writes out/pilot_50_scored.csv with per-lead pre/post score deltas.

Only re-runs the ownership dimension (the only thing the mail data changes).
Roof/income/bill_pain/equity scores carry forward from the baseline run —
no extra API spend. Rows without filled mail data carry forward unchanged.

Headline math: post_score = baseline_score + (own_post - own_pre) * W_ownership
where W_ownership = 0.15 / 0.85 ≈ 0.1765 (Phase-2 redistributed weight).
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.models.lead import ParcelData  # noqa: E402
from api.services.dimensions._ownership_classifier import (  # noqa: E402
    LABEL_TO_TIER,
    determine_ownership_profile,
)
from api.services.scoring import WEIGHTS  # noqa: E402

IN_PATH = Path(__file__).parent.parent / "out" / "pilot_35_sfr_only.csv"
OUT_PATH = Path(__file__).parent.parent / "out" / "pilot_35_scored.csv"
TONY_PATH = Path(__file__).parent.parent / "out" / "pilot_tony_private.csv"
DAC_PATH = Path(__file__).parent.parent / "out" / "pilot_dac_sash.csv"

OWNERSHIP_WEIGHT = WEIGHTS["ownership"]


def _f(s: str) -> float | None:
    return float(s) if s and s.strip() else None


def rescore(row: dict) -> dict:
    extra = {
        "post_score": "", "post_ownership_label": "", "post_ownership_tier": "",
        "ownership_score_post": "", "score_delta": "",
        "mail_state_matches_situs_state": "",
    }
    owner = row.get("mail_owner_name", "").strip()
    mail = row.get("mail_full_address", "").strip()
    if not owner and not mail:
        return {**row, **extra}

    parcel = ParcelData(
        apn=row["apn"], address_situs=row["situs"],
        city=row["city"], zip=row["zip"],
        is_residential=True,
        has_homeowners_exemption=(row["baseline_ownership_label"] == "OWNER_OCCUPIED"),
    )
    scraped = {
        "owner_full_name": owner,
        "full_mailing_address": mail,
        "mail_state": row.get("mail_state", "").strip().upper(),
    }
    label, score_own = determine_ownership_profile(parcel, scraped)
    own_pre = _f(row.get("ownership_score_baseline")) or 0.0
    baseline = float(row["baseline_score"])
    post = max(0.0, min(1.0, baseline + (score_own - own_pre) * OWNERSHIP_WEIGHT))
    return {
        **row,
        "post_score": f"{post:.4f}",
        "post_ownership_label": label,
        "post_ownership_tier": LABEL_TO_TIER[label],
        "ownership_score_post": f"{score_own:.4f}",
        "score_delta": f"{post - baseline:+.4f}",
        "mail_state_matches_situs_state": (scraped["mail_state"] in ("", "CA")),
    }


def main() -> int:
    if not IN_PATH.exists():
        print(f"input not found: {IN_PATH}\nrun scripts/12_export_pilot_50.py first")
        return 1
    rows = list(csv.DictReader(IN_PATH.open(encoding="utf-8")))
    print(f"read {len(rows)} rows from {IN_PATH.name}")
    rescored = [rescore(r) for r in rows]

    out_fields = list(rows[0].keys()) + [
        "post_score", "post_ownership_label", "post_ownership_tier",
        "ownership_score_post", "score_delta", "mail_state_matches_situs_state",
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rescored.sort(key=lambda r: -(float(r["post_score"]) if r["post_score"] else float(r["baseline_score"])))
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(rescored)

    # Split by stream — Tony's deliverable (private) is what gets handed off;
    # the dac_sash slice is retained for future GRID Alternatives handoff.
    tony = [r for r in rescored if r["baseline_stream"] == "private"]
    dac = [r for r in rescored if r["baseline_stream"] == "dac_sash"]
    for path, subset in ((TONY_PATH, tony), (DAC_PATH, dac)):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=out_fields)
            w.writeheader()
            w.writerows(subset)
    print(f"  -> {TONY_PATH.name}  ({len(tony)} private-stream rows for Tony)")
    print(f"  -> {DAC_PATH.name}   ({len(dac)} dac-sash-stream rows for GRID Alternatives)")

    enriched = [r for r in rescored if r["post_score"]]
    skipped = len(rescored) - len(enriched)
    print(f"\nenriched: {len(enriched)}  skipped (empty mail): {skipped}")
    if enriched:
        avg_pre = sum(float(r["baseline_score"]) for r in enriched) / len(enriched)
        avg_post = sum(float(r["post_score"]) for r in enriched) / len(enriched)
        print(f"  avg baseline:    {avg_pre:.4f}")
        print(f"  avg post-enrich: {avg_post:.4f}")
        print(f"  avg delta:       {avg_post - avg_pre:+.4f}")
        labels = Counter(r["post_ownership_label"] for r in enriched)
        print("  post-enrichment label distribution:")
        for lab, ct in labels.most_common():
            print(f"    {lab:40} {ct}")
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
