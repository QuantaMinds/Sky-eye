"""Phase 5 precision/recall benchmark against hand-labeled ground truth.

Reads fixtures/known_changes/labels.csv (built by scripts/label_parcels.py),
runs the full TaxLens pipeline against each labeled parcel, and reports
precision, recall, F1, and per-parcel timing.

Usage:
  python scripts/benchmark_phase5.py
  python scripts/benchmark_phase5.py --labels fixtures/known_changes/labels.csv \\
      --min-confidence 0.6

Publishable-claim policy (per feedback_precision_claim_validation_minimum):
A precision number is "publishable" — i.e., usable in customer-facing
communication like "TaxLens beats EagleView's 8% precision" — only when
ALL of:
  - N >= 100 hand-labeled parcels
  - labels were created by a non-author (Dhanush, not Claude)
  - any one labeler accounts for <= 80% of rows (mixed labeler reduces bias)

Below N=100 the script reports the number and explicitly flags it as
a SMOKE result, not a benchmark. Running with fewer parcels is fine for
catching pipeline regressions; just don't quote the precision number.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.services import (  # noqa: E402
    change_detector, chip_extractor, confidence_pipeline,
    ee_alphaearth, lb_parcels, multimodal_classifier, permit_matcher,
)

PUBLISHABLE_MIN_N = 100


def _label_is_change(row: dict[str, str]) -> bool:
    """Parse the 'has_change' CSV column. labels.csv writes 'True'/'False'."""
    return row.get("has_change", "").strip().lower() in ("true", "1", "yes")


async def _score_one(row: dict[str, str], min_confidence: float) -> tuple[bool, float, float | None]:
    """Run the full pipeline against one labeled parcel. Returns
    (predicted_change, elapsed_seconds, final_score). predicted_change
    is True iff final_score is not None AND >= min_confidence."""
    apn = row["apn"]
    year_a, year_b = int(row["year_a"]), int(row["year_b"])
    started = time.perf_counter()

    parcel = lb_parcels.get_parcel_geometry(apn)
    if parcel is None or parcel.get("geojson") is None:
        return False, time.perf_counter() - started, None
    geo = parcel["geojson"]

    emb_a = ee_alphaearth.get_alphaearth_embeddings(geo, year_a)
    emb_b = ee_alphaearth.get_alphaearth_embeddings(geo, year_b)
    if emb_a.vector is None or emb_b.vector is None:
        return False, time.perf_counter() - started, None
    distance = change_detector.cosine_distance(emb_a.vector, emb_b.vector)

    chips = chip_extractor.fetch_pair(apn, year_a, year_b)
    cls_result, _ = await multimodal_classifier.classify(
        apn=apn, sqft=parcel.get("sqft_main"),
        use_subcategory=parcel.get("use_subcategory", ""),
        png_a=chips.naip_a.png, png_b=chips.naip_b.png,
        naip_a_date=chips.naip_a.image_date or "",
        naip_b_date=chips.naip_b.image_date or "",
    )

    permit_start = dt.date(year_a - 1, 1, 1)
    permit_end = dt.date(year_b, 12, 31)
    permit_hit = permit_matcher.has_permit(apn, permit_start, permit_end)

    conf = confidence_pipeline.evaluate(
        alphaearth_distance=distance,
        has_permit_result=permit_hit,
        gemini_change_type=cls_result.change_type,
        gemini_confidence=cls_result.confidence_0_1,
        gemini_added_sqft=cls_result.estimated_added_sqft,
    )
    elapsed = time.perf_counter() - started
    predicted = (
        conf.final_score is not None and conf.final_score >= min_confidence
    )
    return predicted, elapsed, conf.final_score


def _print_header(n: int) -> None:
    if n < PUBLISHABLE_MIN_N:
        print(
            f"\n=== SMOKE RESULT (N={n} < {PUBLISHABLE_MIN_N}) ===\n"
            "This is a structural smoke test, NOT a publishable benchmark.\n"
            "Per feedback_precision_claim_validation_minimum:\n"
            f"  - need >= {PUBLISHABLE_MIN_N} hand-labeled cases for any\n"
            "    customer-facing precision claim\n"
            "  - labels must be by a non-author (Dhanush, not Claude)\n"
            "DO NOT use this number in a deck, email, or UI.\n"
        )
    else:
        print(f"\n=== BENCHMARK RESULT (N={n}) ===\n")


def _print_metrics(tp: int, fp: int, fn: int, tn: int, elapsed_per: list[float]) -> None:
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall else None
    )
    print(f"TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"Precision: {precision:.3f}" if precision is not None else "Precision: n/a (no predicted positives)")
    print(f"Recall:    {recall:.3f}" if recall is not None else "Recall:    n/a (no actual positives)")
    print(f"F1:        {f1:.3f}" if f1 is not None else "F1:        n/a")
    if elapsed_per:
        avg = sum(elapsed_per) / len(elapsed_per)
        print(f"Per-parcel: avg={avg:.2f}s  min={min(elapsed_per):.2f}s  max={max(elapsed_per):.2f}s")


async def _run(labels_path: Path, min_confidence: float) -> int:
    rows = list(csv.DictReader(labels_path.open()))
    if not rows:
        print(f"error: {labels_path} has no labeled rows yet — run scripts/label_parcels.py first")
        return 2
    _print_header(len(rows))

    tp = fp = fn = tn = 0
    elapsed_per: list[float] = []
    for row in rows:
        truth = _label_is_change(row)
        predicted, elapsed, score = await _score_one(row, min_confidence)
        elapsed_per.append(elapsed)
        if predicted and truth:    tp += 1
        elif predicted and not truth: fp += 1
        elif not predicted and truth: fn += 1
        else:                       tn += 1
        score_str = f"{score:.2f}" if score is not None else "None"
        verdict = "TP" if predicted and truth else (
            "FP" if predicted else ("FN" if truth else "TN")
        )
        print(f"  {row['apn']:>14} truth={truth!s:<5} pred={predicted!s:<5} score={score_str:>5}  [{verdict}]  {elapsed:.1f}s")

    _print_metrics(tp, fp, fn, tn, elapsed_per)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--labels", type=Path, default=Path("fixtures/known_changes/labels.csv"))
    p.add_argument("--min-confidence", type=float, default=0.6)
    args = p.parse_args()

    if not args.labels.exists():
        print(f"error: {args.labels} not found — run scripts/label_parcels.py first")
        return 2
    return asyncio.run(_run(args.labels, args.min_confidence))


if __name__ == "__main__":
    sys.exit(main())
