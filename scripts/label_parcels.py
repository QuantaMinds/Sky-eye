"""Phase 5 ground-truth labeling CLI.

Given a list of candidate APNs and two years, pulls NAIP+S2 chips for
each parcel, saves a 2x2 montage to fixtures/known_changes/chips/, and
prompts the labeler for a verdict. Appends to fixtures/known_changes/
labels.csv. Resumable: APNs already in labels.csv are skipped.

Usage:
  python scripts/label_parcels.py --apns apns.txt --year-a 2020 --year-b 2022
  python scripts/label_parcels.py --bbox -118.20,33.75,-118.10,33.82 --limit 30 \
      --year-a 2020 --year-b 2022

NAIP coverage (verified 2026-05-19 via EE): California NAIP flights
fired in 2018, 2020, 2022. NO 2024 imagery exists yet — the cycle is
biennial and the 2024 season isn't in EE. Asking for year_b=2024 makes
every chip pair fail with 'no NAIP pair' and skip the parcel. The
working pair today is (2020, 2022); use (2018, 2020) if you need the
older comparison. AlphaEarth has 2024 but the human-labeling
foundation depends on NAIP, so the labeler MUST use NAIP-available years.

Why this exists: Rule 3. The Phase 5 precision gate is meaningless
without real labels. Inventing fake labels to make the test pass is
exactly the Edison-Theatre failure mode the rules forbid.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.services import chip_extractor, lb_parcels  # noqa: E402

CHIPS_DIR = Path("fixtures/known_changes/chips")
LABELS_CSV = Path("fixtures/known_changes/labels.csv")
CHANGE_TYPES = ("new_adu", "addition", "pool", "garage_conv", "demolition", "no_change")
LABEL_HEADER = ("apn", "year_a", "year_b", "has_change", "change_type", "notes",
                "naip_a_date", "naip_b_date", "labeled_at")


def _existing_apns() -> set[str]:
    if not LABELS_CSV.exists():
        return set()
    with LABELS_CSV.open(newline="") as f:
        return {row["apn"] for row in csv.DictReader(f)}


def _ensure_csv() -> None:
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not LABELS_CSV.exists():
        with LABELS_CSV.open("w", newline="") as f:
            csv.writer(f).writerow(LABEL_HEADER)


def _prompt_label(apn: str, png_path: Path) -> dict[str, str] | None:
    print(f"\n--- APN {apn} ---  open: {png_path}")
    raw = input("change? [y/n/skip] > ").strip().lower()
    if raw == "skip":
        return None
    if raw not in ("y", "n"):
        print("  invalid, skipping"); return None
    has_change = raw == "y"
    if has_change:
        print("  type:", " ".join(f"{i}={t}" for i, t in enumerate(CHANGE_TYPES[:-1])))
        ti = input("  > ").strip()
        try:
            change_type = CHANGE_TYPES[int(ti)]
        except (ValueError, IndexError):
            print("  invalid index, skipping"); return None
    else:
        change_type = "no_change"
    notes = input("  notes (optional) > ").strip()
    return {"has_change": str(has_change), "change_type": change_type, "notes": notes}


def _load_apns(args: argparse.Namespace) -> list[str]:
    if args.apns:
        return [a.strip() for a in Path(args.apns).read_text().splitlines() if a.strip()]
    if args.bbox:
        lon_min, lat_min, lon_max, lat_max = (float(x) for x in args.bbox.split(","))
        return lb_parcels.list_apns_in_bbox(
            lon_min, lat_min, lon_max, lat_max, limit=args.limit,
        )
    print("error: pass --apns FILE or --bbox lon_min,lat_min,lon_max,lat_max")
    sys.exit(2)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apns"); p.add_argument("--bbox"); p.add_argument("--limit", type=int, default=30)
    p.add_argument("--year-a", type=int, required=True); p.add_argument("--year-b", type=int, required=True)
    args = p.parse_args()

    CHIPS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_csv()
    done = _existing_apns()
    apns = [a for a in _load_apns(args) if a not in done]
    print(f"labeling {len(apns)} parcels ({len(done)} already done)")

    import datetime as dt
    for apn in apns:
        chips = chip_extractor.fetch_pair(apn, args.year_a, args.year_b)
        if chips.parcel is None:
            print(f"  {apn}: no parcel geometry, skipping"); continue
        if not chips.has_naip_pair:
            print(f"  {apn}: no NAIP pair (a={chips.naip_a.source} b={chips.naip_b.source}), skipping"); continue
        png_path = CHIPS_DIR / f"{apn}.png"
        png_path.write_bytes(chip_extractor.montage(chips, args.year_a, args.year_b))
        label = _prompt_label(apn, png_path)
        if label is None:
            continue
        with LABELS_CSV.open("a", newline="") as f:
            csv.writer(f).writerow([
                apn, args.year_a, args.year_b,
                label["has_change"], label["change_type"], label["notes"],
                chips.naip_a.image_date or "", chips.naip_b.image_date or "",
                dt.datetime.now(dt.timezone.utc).isoformat(),
            ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
