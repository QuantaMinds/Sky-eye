"""Forensic tear-down of the Phase 1.5e distribution test.

Re-processes the 100 parcels from .cache.db (set by the prior run) and prints:
  - per-dimension value distribution (histogram-style)
  - per-dimension variance contribution
  - top-5 and bottom-5 parcels with full dimension breakdown
  - silent-failure scan: dims that look "stuck" (low variance, all-same-value)
  - stream distribution explanation
  - score formula application traced for one mid-tier parcel
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.models.lead import (  # noqa: E402
    CensusData, DacInfo, NRELData, ParcelData, SolarRoofData, UtilityInfo,
)
from api.services.scoring import compute_score, WEIGHTS, _BASELINE_WEIGHTS, _PHASE_2_DEFERRED  # noqa: E402

CACHE_DB = Path(r"D:\EYE-Lead\Sky-eye\.cache.db")
SOLAR_MEAN_KWH = 30_000
SOLAR_STDEV_KWH = 15_000
SOLAR_MIN_KWH = 4_400
RANDOM_SEED = 17


def gather_parcels() -> list[dict]:
    """Walk the cache and assemble (coord, all_inputs) for every parcel
    where all five service caches are present."""
    con = sqlite3.connect(CACHE_DB)
    rows = con.execute("SELECT k, v FROM cache").fetchall()
    by_point: dict[tuple[float, float], dict] = {}
    for k, v in rows:
        if ":" not in k:
            continue
        prefix, coord = k.split(":", 1)
        coord = coord.split(":")[0]  # strip ":4.0" suffix on nrel keys
        try:
            lat, lng = [float(x) for x in coord.split(",")]
        except (ValueError, IndexError):
            continue
        d = by_point.setdefault((round(lat, 4), round(lng, 4)), {})
        try:
            d[prefix] = json.loads(v)
        except json.JSONDecodeError:
            pass
    complete = [
        (c, d) for c, d in by_point.items()
        if all(p in d for p in ("parcel", "utility", "dac", "census", "nrel"))
    ]
    return complete


def score_one(rng: random.Random, raw: dict) -> dict | None:
    p_raw = raw["parcel"].get("parcel")
    if not p_raw:
        return None
    parcel = ParcelData(**p_raw)
    utility = UtilityInfo(**raw["utility"]["utility"]) if raw["utility"].get("utility") else None
    dac_info = DacInfo(**raw["dac"]["dac"]) if raw["dac"].get("dac") else None
    census = CensusData(**raw["census"])
    nrel = NRELData(**raw["nrel"])
    kwh = max(SOLAR_MIN_KWH, rng.gauss(SOLAR_MEAN_KWH, SOLAR_STDEV_KWH))
    roof = SolarRoofData(max_kwh_year=kwh, has_existing_solar=None)
    score, dims, mode, conf = compute_score(roof, census, nrel, parcel, utility, dac_info)
    return {
        "score": score, "stream": parcel.stream, "confidence": conf,
        "roof_potential": dims.roof_potential.value,
        "income_qualification": dims.income_qualification.value,
        "ownership": dims.ownership.value,
        "bill_pain": dims.bill_pain.value,
        "equity_proxy": dims.equity_proxy.value,
        "no_existing_solar": dims.no_existing_solar.value,
        "intent_signal": dims.intent_signal.value,
        "raw_kwh": kwh,
        "raw_income": census.median_household_income,
        "raw_tenure": parcel.arms_length_year,
        "raw_exemption": parcel.has_homeowners_exemption,
        "raw_taxable": parcel.is_taxable,
        "raw_residential": parcel.is_residential,
        "raw_dac": (dac_info.is_dac if dac_info else False),
        "raw_utility": (utility.utility_name if utility else None),
        "raw_nrel_kwh": nrel.ac_annual_kwh,
        "apn": parcel.apn,
        "address": parcel.address_situs,
    }


def _hist(values: list[float], n_bins: int = 10, lo: float = 0.0, hi: float = 1.0) -> None:
    """Quick ascii histogram for a dimension's values."""
    if not values:
        print("    (no data)")
        return
    bin_w = (hi - lo) / n_bins
    buckets = [0] * n_bins
    for v in values:
        if v is None:
            continue
        idx = min(int((v - lo) / bin_w), n_bins - 1)
        if 0 <= idx < n_bins:
            buckets[idx] += 1
    max_count = max(buckets) if buckets else 1
    for i, c in enumerate(buckets):
        bar = "#" * int((c / max_count) * 30)
        print(f"    {lo + i*bin_w:.2f}-{lo + (i+1)*bin_w:.2f}  {c:>4} {bar}")


def main() -> int:
    print("=" * 72)
    print("  EFFECTIVE WEIGHTS (after Phase-2-deferred redistribution)")
    print("=" * 72)
    print(f"  Phase-2 deferred set: {sorted(_PHASE_2_DEFERRED)}")
    print(f"  Active baseline sum:  {sum(w for k, w in _BASELINE_WEIGHTS.items() if k not in _PHASE_2_DEFERRED):.4f}")
    print()
    print(f"  {'dim':<22} {'baseline':>10} {'effective':>10} {'lift':>8}")
    for k, w in _BASELINE_WEIGHTS.items():
        eff = WEIGHTS[k]
        lift = (eff - w) / w * 100 if w else 0
        marker = "   <- deferred" if k in _PHASE_2_DEFERRED else ""
        print(f"  {k:<22} {w:>10.4f} {eff:>10.4f} {lift:>+7.1f}% {marker}")
    print()

    print("=" * 72)
    print("  LOADING CACHED PARCELS")
    print("=" * 72)
    cache_rows = gather_parcels()
    print(f"  parcels with all 5 services cached: {len(cache_rows)}")
    print()

    rng = random.Random(RANDOM_SEED)
    results: list[dict] = []
    for coord, raw in cache_rows:
        r = score_one(rng, raw)
        if r is not None:
            results.append(r)
    print(f"  scoreable parcels: {len(results)}")
    if not results:
        return 1

    scores = [r["score"] for r in results]
    print()
    print("=" * 72)
    print(f"  HEADLINE STATS (n={len(results)})")
    print("=" * 72)
    print(f"  mean:   {statistics.mean(scores):.4f}")
    print(f"  stdev:  {statistics.stdev(scores):.4f}")
    print(f"  median: {statistics.median(scores):.4f}")
    print(f"  min:    {min(scores):.4f}")
    print(f"  max:    {max(scores):.4f}")
    print(f"  >0.8 fraction: {sum(1 for s in scores if s > 0.8) / len(scores):.2%}")

    print()
    print("=" * 72)
    print("  PER-DIMENSION VALUE DISTRIBUTION")
    print("=" * 72)
    for dim in ("roof_potential", "income_qualification", "ownership",
                "bill_pain", "equity_proxy", "no_existing_solar", "intent_signal"):
        vals = [r[dim] for r in results if r[dim] is not None]
        nulls = sum(1 for r in results if r[dim] is None)
        if not vals:
            print(f"\n  {dim}  ({nulls}/{len(results)} NULL — Phase-2-deferred or unavailable)")
            continue
        s_mean = statistics.mean(vals)
        s_std = statistics.stdev(vals) if len(vals) > 1 else 0
        unique = len(set(round(v, 4) for v in vals))
        print(f"\n  {dim}  (n={len(vals)}, NULLs={nulls}, unique={unique}, mean={s_mean:.3f}, stdev={s_std:.3f}, weight={WEIGHTS[dim]:.3f})")
        _hist(vals)

    print()
    print("=" * 72)
    print("  PER-DIMENSION VARIANCE CONTRIBUTION TO SCORE")
    print("=" * 72)
    print("  contribution = weight * stdev(dim_value)")
    print()
    print(f"  {'dim':<22} {'weight':>8} {'value_stdev':>12} {'contribution':>14}")
    total_var = 0.0
    for dim in ("roof_potential", "income_qualification", "ownership",
                "bill_pain", "equity_proxy", "no_existing_solar", "intent_signal"):
        vals = [r[dim] for r in results if r[dim] is not None]
        if not vals or len(vals) < 2:
            print(f"  {dim:<22} {WEIGHTS[dim]:>8.3f} {'NULL':>12} {'0.0000':>14}")
            continue
        s_std = statistics.stdev(vals)
        contrib = WEIGHTS[dim] * s_std
        total_var += contrib ** 2
        print(f"  {dim:<22} {WEIGHTS[dim]:>8.3f} {s_std:>12.4f} {contrib:>14.4f}")
    print(f"\n  theoretical_max_stdev_if_independent = sqrt(sum(contribution^2)) = {total_var**0.5:.4f}")

    print()
    print("=" * 72)
    print("  STREAM DISTRIBUTION (and DAC raw breakdown)")
    print("=" * 72)
    stream_counts = Counter(r["stream"] for r in results)
    for s, c in stream_counts.most_common():
        print(f"  {s:<20}  {c:>3}  ({c/len(results):.1%})")
    dac_raw = Counter(r["raw_dac"] for r in results)
    print(f"\n  raw is_dac flag: True={dac_raw[True]}  False={dac_raw[False]}")

    util_counts = Counter(r["raw_utility"] for r in results)
    print(f"\n  utility resolution:")
    for u, c in util_counts.most_common():
        print(f"    {u or 'unknown':<10}  {c}")

    print()
    print("=" * 72)
    print("  TOP 5 PARCELS (highest scores)")
    print("=" * 72)
    for r in sorted(results, key=lambda x: -x["score"])[:5]:
        print(f"\n  apn {r['apn']}  score={r['score']:.4f}  conf={r['confidence']:.4f}  stream={r['stream']}")
        print(f"    address: {r['address']}")
        inc = f"{r['income_qualification']:.3f}" if r['income_qualification'] is not None else "None"
        print(f"    roof={r['roof_potential']:.3f} (raw_kwh={r['raw_kwh']:.0f})  income={inc} (raw=${r['raw_income'] or 0:.0f})")
        bp = f"{r['bill_pain']:.3f}" if r['bill_pain'] is not None else "None"
        eq = f"{r['equity_proxy']:.3f}" if r['equity_proxy'] is not None else "None"
        ow = f"{r['ownership']:.3f}" if r['ownership'] is not None else "None"
        print(f"    ownership={ow}  bill_pain={bp}  equity={eq}")
        print(f"    raw: tenure_yr={r['raw_tenure']}  exemption={r['raw_exemption']}  taxable={r['raw_taxable']}  utility={r['raw_utility']}")

    print()
    print("=" * 72)
    print("  BOTTOM 5 PARCELS (lowest scores)")
    print("=" * 72)
    for r in sorted(results, key=lambda x: x["score"])[:5]:
        print(f"\n  apn {r['apn']}  score={r['score']:.4f}  conf={r['confidence']:.4f}  stream={r['stream']}")
        print(f"    address: {r['address']}")
        print(f"    roof={r['roof_potential']:.3f} (raw_kwh={r['raw_kwh']:.0f})  "
              f"income={r['income_qualification']!s:<8} (raw=${r['raw_income'] or 0:.0f})")
        print(f"    ownership={r['ownership']!s:<6}  bill_pain={r['bill_pain']!s:<6}  equity={r['equity_proxy']!s:<6}")
        print(f"    raw: tenure_yr={r['raw_tenure']}  exemption={r['raw_exemption']}  taxable={r['raw_taxable']}  utility={r['raw_utility']}")

    print()
    print("=" * 72)
    print("  SILENT-FAILURE SCAN")
    print("=" * 72)
    for dim in ("roof_potential", "income_qualification", "ownership",
                "bill_pain", "equity_proxy"):
        vals = [r[dim] for r in results if r[dim] is not None]
        if not vals:
            continue
        unique = sorted(set(round(v, 3) for v in vals))
        s_std = statistics.stdev(vals) if len(vals) > 1 else 0
        flag = ""
        if s_std < 0.05:
            flag = "  <- LOW STDEV (variance-starved)"
        if len(unique) <= 5:
            flag += f"  <- DISCRETE ({len(unique)} unique: {unique})"
        if s_std < 0.05 or len(unique) <= 5:
            print(f"  {dim}: stdev={s_std:.4f}, unique={len(unique)}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
