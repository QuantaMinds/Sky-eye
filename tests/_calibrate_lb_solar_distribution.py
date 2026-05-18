"""Pull empirical Solar API distribution for Long Beach residential SFRs.

Hits the real Solar API for 15 hardcoded LB SFR coords (pulled from the
verified fixture + earlier probes), computes mean/stdev of max_kwh_year.

Cost: 15 x ~$0.10 = ~$1.50 in Solar API spend. Cached in .cache.db so
the test can reuse without re-spending. Solar API uses GOOGLE_SOLAR_API_KEY
(not ADC) so this works even when BQ auth tokens have expired.
"""
from __future__ import annotations

import asyncio
import statistics
import sys

from dotenv import load_dotenv

load_dotenv()

from api.services import solar_api  # noqa: E402

# 15 LB SFR coords from the labeled_addresses.json fixture + earlier probes.
# Mix of Belmont Shore (small lots, dense), Bixby Knolls (larger lots, mature
# trees), Naples Island, and central LB residential.
LB_PARCELS: list[dict] = [
    {"apn": "7247002013", "address_situs": "156 SAINT JOSEPH AVE LONG BEACH CA",
     "lat": 33.7600,   "lng": -118.1380},
    {"apn": "7264024019", "address_situs": "2701 E OCEAN BLVD LONG BEACH CA",
     "lat": 33.7610,   "lng": -118.1490},
    {"apn": "7264024016", "address_situs": "2725 E OCEAN BLVD LONG BEACH CA",
     "lat": 33.7611,   "lng": -118.1480},
    {"apn": "7245017009", "address_situs": "5710 E OCEAN BLVD LONG BEACH CA",
     "lat": 33.7570,   "lng": -118.1140},
    {"apn": "7204013021", "address_situs": "Bixby Knolls SFR 1 (zip 90807)",
     "lat": 33.8517,   "lng": -118.1820},
    {"apn": "7147014027", "address_situs": "Bixby Knolls SFR 2 (zip 90807)",
     "lat": 33.8400,   "lng": -118.1880},
    {"apn": "lb_belshore_3", "address_situs": "Belmont Shore SFR 3",
     "lat": 33.7595,   "lng": -118.1420},
    {"apn": "lb_naples_1", "address_situs": "Naples Island SFR 1",
     "lat": 33.7530,   "lng": -118.1190},
    {"apn": "lb_naples_2", "address_situs": "Naples Island SFR 2",
     "lat": 33.7545,   "lng": -118.1175},
    {"apn": "lb_bixby_3", "address_situs": "Bixby Knolls SFR 3",
     "lat": 33.8550,   "lng": -118.1800},
    {"apn": "lb_north_1", "address_situs": "North LB SFR 1 (zip 90805)",
     "lat": 33.8650,   "lng": -118.1900},
    {"apn": "lb_north_2", "address_situs": "North LB SFR 2 (zip 90805)",
     "lat": 33.8700,   "lng": -118.2000},
    {"apn": "lb_downtown_1", "address_situs": "LB downtown SFR (zip 90802)",
     "lat": 33.7700,   "lng": -118.1900},
    {"apn": "lb_central_1", "address_situs": "LB central SFR (zip 90806)",
     "lat": 33.8000,   "lng": -118.1800},
    {"apn": "lb_east_1", "address_situs": "East LB SFR (zip 90808)",
     "lat": 33.8200,   "lng": -118.1200},
]


async def fetch_solar(parcels: list[dict]) -> list[tuple[str, float | None]]:
    """Parallel batches of 5 to avoid hitting Solar's 100/min rate limit."""
    results: list[tuple[str, float | None]] = []
    batch_size = 5
    for i in range(0, len(parcels), batch_size):
        batch = parcels[i:i + batch_size]
        coros = [
            solar_api.get_roof_data(float(p["lat"]), float(p["lng"]), p["address_situs"])
            for p in batch
        ]
        batch_results = await asyncio.gather(*coros, return_exceptions=True)
        for p, r in zip(batch, batch_results):
            if isinstance(r, Exception):
                print(f"  FAIL {p['apn']}: {type(r).__name__}: {str(r)[:60]}")
                results.append((p["apn"], None))
            else:
                roof, _ = r
                results.append((p["apn"], roof.max_kwh_year))
                print(f"  {p['apn']:15}  {p['address_situs'][:45]:45}  max_kwh={roof.max_kwh_year}")
    return results


async def main() -> int:
    print(f"Hitting Solar API for {len(LB_PARCELS)} LB SFR coords (parallel batches of 5)...")
    results = await fetch_solar(LB_PARCELS)

    kwhs = [v for _, v in results if v is not None]
    print()
    print(f"Successful Solar calls: {len(kwhs)} / {len(results)}")
    if len(kwhs) < 5:
        print("Not enough data for distribution.")
        return 1

    mean_kwh = statistics.mean(kwhs)
    stdev_kwh = statistics.stdev(kwhs) if len(kwhs) > 1 else 0
    median_kwh = statistics.median(kwhs)
    min_kwh = min(kwhs)
    max_kwh = max(kwhs)
    p25 = statistics.quantiles(kwhs, n=4)[0] if len(kwhs) >= 4 else min_kwh
    p75 = statistics.quantiles(kwhs, n=4)[2] if len(kwhs) >= 4 else max_kwh

    print()
    print(f"=== Empirical Long Beach Solar API distribution (n={len(kwhs)}) ===")
    print(f"  mean kWh/yr:     {mean_kwh:>10,.0f}")
    print(f"  stdev:           {stdev_kwh:>10,.0f}")
    print(f"  median:          {median_kwh:>10,.0f}")
    print(f"  min / max:       {min_kwh:>10,.0f} / {max_kwh:,.0f}")
    print(f"  p25 / p75:       {p25:>10,.0f} / {p75:,.0f}")
    print()
    print(f"Constants for tests/run_phase_15e_distribution.py:")
    print(f"  SOLAR_MEAN_KWH = {round(mean_kwh, -2):.0f}")
    print(f"  SOLAR_STDEV_KWH = {round(stdev_kwh, -2):.0f}")
    print(f"  SOLAR_MIN_KWH = {round(min_kwh * 0.5, -2):.0f}  # half of observed min for tail")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
