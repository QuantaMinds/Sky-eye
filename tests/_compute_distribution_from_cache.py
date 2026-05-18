"""Salvage analysis: compute the Phase 1.5e score distribution from the
76 parcels whose inputs are already cached, bypassing the hung main run.

The cache key format from each service:
  parcel:{lat:.6f},{lng:.6f}    -> {"parcel": {...ParcelData fields...}}
  utility:{lat:.6f},{lng:.6f}   -> {"utility": {...UtilityInfo fields...}}
  dac:{lat:.6f},{lng:.6f}       -> {"dac": {...DacInfo fields...}}
  census:{lat:.5f},{lng:.5f}    -> CensusData fields
  nrel:{lat:.4f},{lng:.4f}:4.0  -> NRELData fields
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.models.lead import (  # noqa: E402
    CensusData, DacInfo, NRELData, ParcelData, SolarRoofData, UtilityInfo,
)
from api.services.scoring import compute_score  # noqa: E402

CACHE_DB = Path(r"D:\EYE-Lead\Sky-eye\.cache.db")
SOLAR_MEAN_KWH = 13_500
SOLAR_STDEV_KWH = 4_500
SOLAR_MIN_KWH = 3_000
RANDOM_SEED = 17


def _all_cache_rows(con: sqlite3.Connection) -> list[tuple[str, str]]:
    return list(con.execute("SELECT k, v FROM cache").fetchall())


def main() -> int:
    con = sqlite3.connect(CACHE_DB)
    rows = _all_cache_rows(con)
    print(f"Cache entries: {len(rows)}")

    # Group by point. cache prefixes use lat:6dp,lng:6dp (parcel/utility/dac)
    # or 5dp/4dp (census/nrel) — we need to align by best-effort coord match.
    by_point: dict[tuple[float, float], dict] = {}

    def _key_to_coord(k: str) -> tuple[float, float] | None:
        # k looks like 'parcel:33.768301,-118.188740' or 'census:33.76830,-118.18874'
        if ":" not in k:
            return None
        _, coord = k.split(":", 1)
        coord = coord.split(":")[0]  # drop trailing ':4.0' from nrel
        try:
            lat, lng = [float(x) for x in coord.split(",")]
            return (round(lat, 4), round(lng, 4))
        except (ValueError, IndexError):
            return None

    # First pass: collect every prefix per coord
    for k, v in rows:
        coord = _key_to_coord(k)
        if not coord:
            continue
        d = by_point.setdefault(coord, {})
        prefix = k.split(":")[0]
        try:
            d[prefix] = json.loads(v)
        except json.JSONDecodeError:
            pass

    # Only points that have ALL five services cached are scoreable
    complete = {
        c: d for c, d in by_point.items()
        if all(p in d for p in ("parcel", "utility", "dac", "census", "nrel"))
    }
    print(f"Points with all 5 services cached: {len(complete)}")

    rng = random.Random(RANDOM_SEED)
    results: list[dict] = []
    for coord, d in complete.items():
        p_raw = d["parcel"].get("parcel")
        if not p_raw:
            continue  # parcel lookup returned None
        u_raw = d["utility"].get("utility")
        dac_raw = d["dac"].get("dac")
        cens_raw = d["census"]
        nrel_raw = d["nrel"]

        parcel = ParcelData(**p_raw)
        utility = UtilityInfo(**u_raw) if u_raw else None
        dac_info = DacInfo(**dac_raw) if dac_raw else None
        census = CensusData(**cens_raw)
        nrel = NRELData(**nrel_raw)
        kwh = max(SOLAR_MIN_KWH, rng.gauss(SOLAR_MEAN_KWH, SOLAR_STDEV_KWH))
        roof = SolarRoofData(max_kwh_year=kwh, has_existing_solar=None)

        score, dims, mode, conf = compute_score(roof, census, nrel, parcel, utility, dac_info)
        results.append({"score": score, "stream": parcel.stream, "confidence": conf})

    print(f"Scoreable parcels: {len(results)}")
    if not results:
        print("Nothing to analyze.")
        return 1

    scores = [r["score"] for r in results]
    mean_score = statistics.mean(scores)
    stdev_score = statistics.stdev(scores) if len(scores) > 1 else 0.0
    pct_high = sum(1 for s in scores if s > 0.8) / len(scores)

    print()
    print(f"=== Phase 1.5e distribution stats (n={len(results)}) ===")
    print(f"  mean(score):           {mean_score:.4f}   (assert in [0.30, 0.70])")
    print(f"  stdev(score):          {stdev_score:.4f}   (assert > 0.10)")
    print(f"  fraction score > 0.8:  {pct_high:.2%}     (assert < 30%)")
    print(f"  min / max:             {min(scores):.3f} / {max(scores):.3f}")

    streams: dict[str, int] = {}
    for r in results:
        streams[r["stream"]] = streams.get(r["stream"], 0) + 1
    print(f"  stream distribution:")
    for s, c in sorted(streams.items(), key=lambda x: -x[1]):
        print(f"    {s:20}  {c:3} ({c/len(results):.1%})")

    fails = []
    if not (0.30 <= mean_score <= 0.70):
        fails.append(f"mean {mean_score:.4f} outside [0.30, 0.70]")
    if stdev_score <= 0.10:
        fails.append(f"stdev {stdev_score:.4f} too low")
    if pct_high >= 0.30:
        fails.append(f"top-tier fraction {pct_high:.2%} too high")

    print()
    if fails:
        print("FAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("PASS — distribution shows real variance under LA-calibrated bands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
