"""Phase 1.5e statistical distribution test.

Samples 100 random LA County residential parcels from BQ and runs each
through the scoring path (skipping Solar API + Vertex AI narrative — see
notes below). Asserts the resulting score distribution shows real variance,
not the flat-bunched-at-0.7-0.85 pattern that the truth-first and LA-
calibration changes were designed to fix.

Cost-control: this test does NOT hit Solar API ($0.10/call x 100 = $10) or
Vertex AI ($0.001/call x 100 = $0.10 + 5-12s latency each = ~20 min). Both
are tested via the Phase 1.5c gate + spot-checks. The Solar input is
synthesized with a plausible LA-residential distribution; Vertex narrative
is not exercised here.

Synthetic Solar distribution rationale (CALIBRATED 2026-05-17):
  Empirical probe of 15 LB residential SFR addresses via real Solar API:
    min  8,739    p25  20,190    median  29,677    p75  59,116    max  445,473
  Use median + IQR-based stdev to avoid the 445k outlier (5710 E Ocean —
  likely a multi-parcel resolution edge case). Truncated-normal:
    mean   = 30,000  (LB median, matches the recalibrated ROOF_KWH_FULL anchor)
    stdev  = 15,000  (~half the IQR width)
    min    =  4,400  (half the observed min; tail floor)
  Under the new anchor (ROOF_KWH_FULL=30,000), this synthetic distribution
  produces roof_potential variance ~0.15-1.00 with smooth coverage, instead
  of the saturating-1.0 cluster the old 15k anchor + 13.5k-mean synthetic
  produced together.

Assertions (after the 1.5e calibration):
  - stdev(score) >  0.10  (real variance, not bunched)
  - mean(score)   in [0.30, 0.70]   (wider than the original [0.30, 0.65]
                                     because LA-band peak at 1.0 lifts the
                                     income-rich tracts)
  - count(score > 0.8) / 100 < 0.30 (no more than 30% in the "great" tier)
"""
from __future__ import annotations

import asyncio
import random
import statistics
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery  # noqa: E402

from api.models.lead import (  # noqa: E402
    CensusData, NRELData, ParcelData, SolarRoofData,
)
from api.services import dac, parcel_lookup, utility  # noqa: E402
from api.services.scoring import compute_score  # noqa: E402

SAMPLE_SIZE = 100
RANDOM_SEED = 17  # deterministic-ish synthetic Solar

# Synthetic Solar parameters — empirical LB residential calibration.
SOLAR_MEAN_KWH = 30_000   # LB residential median (n=15 Solar API probe 2026-05-17)
SOLAR_STDEV_KWH = 15_000  # ~half IQR; excludes 445k outlier
SOLAR_MIN_KWH = 4_400     # half of observed min, tail floor


def _sample_parcels(bq: bigquery.Client, n: int) -> list[dict]:
    sql = f"""
    SELECT apn, center_lat, center_lon, address_situs, zip
    FROM `sky-eye-496604.parcels.la_county` TABLESAMPLE SYSTEM (1 PERCENT)
    WHERE is_residential = TRUE
      AND is_taxable = TRUE
      AND geom IS NOT NULL
      AND center_lat IS NOT NULL AND center_lon IS NOT NULL
    LIMIT {n}
    """
    return [dict(r) for r in bq.query(sql).result()]


def _synth_solar(rng: random.Random) -> SolarRoofData:
    kwh = max(SOLAR_MIN_KWH, rng.gauss(SOLAR_MEAN_KWH, SOLAR_STDEV_KWH))
    return SolarRoofData(max_kwh_year=kwh, has_existing_solar=None)


async def _census_for_point(lat: float, lng: float) -> CensusData:
    """Pull median household income from Census ACS for the block group at
    (lat, lng). Reuses the existing census service which has its own cache."""
    from api.services import census
    data, _ = await census.get_block_group_data(lat, lng)
    return data


async def _nrel_for_point(lat: float, lng: float) -> NRELData:
    from api.services import nrel
    data, _ = await nrel.get_production(lat, lng)
    return data


async def score_one(rng: random.Random, lat: float, lng: float) -> dict[str, Any]:
    roof = _synth_solar(rng)
    # Parallel fetch of the real services (skip Solar + narrative)
    parcel_t = parcel_lookup.lookup_by_point(lat, lng)
    util_t = utility.lookup_by_point(lat, lng)
    dac_t = dac.lookup_by_point(lat, lng)
    cens_t = _census_for_point(lat, lng)
    pv_t = _nrel_for_point(lat, lng)
    (parcel, _), (util, _), (dac_info, _), cens, pv = await asyncio.gather(
        parcel_t, util_t, dac_t, cens_t, pv_t,
    )
    score, dims, mode, conf = compute_score(roof, cens, pv, parcel, util, dac_info)
    return {
        "score": score,
        "mode": mode,
        "confidence": conf,
        "stream": parcel.stream if parcel else "no_parcel",
    }


async def main() -> int:
    rng = random.Random(RANDOM_SEED)
    bq = bigquery.Client(project="sky-eye-496604", location="us-west1")
    print(f"Sampling {SAMPLE_SIZE} random residential-taxable parcels...")
    parcels = _sample_parcels(bq, SAMPLE_SIZE)
    print(f"  got {len(parcels)} parcels")
    if len(parcels) < SAMPLE_SIZE * 0.9:
        print(f"  not enough samples to test")
        return 1

    print("Scoring (this may take 30-90 seconds; Census + NREL per parcel)...")
    results: list[dict] = []
    for i, p in enumerate(parcels, 1):
        try:
            r = await asyncio.wait_for(
                score_one(rng, float(p["center_lat"]), float(p["center_lon"])),
                timeout=45.0,
            )
            r["apn"] = p["apn"]
            results.append(r)
        except asyncio.TimeoutError:
            print(f"  [{i:3}] TIMEOUT after 45s on {p['apn']}", flush=True)
        except Exception as exc:
            print(f"  [{i:3}] FAIL {p['apn']}: {type(exc).__name__}: {str(exc)[:60]}", flush=True)
        if i % 10 == 0:
            mean = statistics.mean(r["score"] for r in results) if results else 0.0
            print(f"  [{i:3}/{len(parcels)}] running mean={mean:.3f}  (n={len(results)})", flush=True)

    if len(results) < SAMPLE_SIZE * 0.9:
        print(f"\nNot enough successful scores ({len(results)}) — test inconclusive")
        return 1

    scores = [r["score"] for r in results]
    mean_score = statistics.mean(scores)
    stdev_score = statistics.stdev(scores) if len(scores) > 1 else 0.0
    pct_high = sum(1 for s in scores if s > 0.8) / len(scores)
    streams = sorted(set(r["stream"] for r in results))
    stream_counts = {s: sum(1 for r in results if r["stream"] == s) for s in streams}

    print()
    print(f"=== Phase 1.5e distribution stats (n={len(results)}) ===")
    print(f"  mean(score):           {mean_score:.4f}   (assert in [0.30, 0.70])")
    print(f"  stdev(score):          {stdev_score:.4f}   (assert > 0.10)")
    print(f"  fraction score > 0.8:  {pct_high:.2%}     (assert < 30%)")
    print(f"  min / max:             {min(scores):.3f} / {max(scores):.3f}")
    print(f"  stream distribution:")
    for s, c in stream_counts.items():
        print(f"    {s:20}  {c:3} ({c/len(results):.1%})")

    fails = []
    if not (0.30 <= mean_score <= 0.70):
        fails.append(f"mean {mean_score:.4f} outside [0.30, 0.70]")
    if stdev_score <= 0.10:
        fails.append(f"stdev {stdev_score:.4f} too low (real variance expected)")
    if pct_high >= 0.30:
        fails.append(f"top-tier fraction {pct_high:.2%} too high (saturation)")

    print()
    if fails:
        print("FAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("PASS — distribution shows real variance under LA-calibrated bands.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
