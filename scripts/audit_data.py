"""Data-quality audit for one address — prints every raw value with a
verification URL so a human can spot-check against ground truth.

Run with:
    python scripts/audit_data.py "100 Long Beach Blvd, Long Beach, CA"
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

from api.services import (  # noqa: E402
    assessor, census, geocoding, narrative, nrel, scoring, solar_api,
)
from api.services.scoring import WEIGHTS  # noqa: E402


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}")


def _decode_geoid(geoid: str) -> str:
    # GEOID = state(2) + county(3) + tract(6) + bg(1) = 12 chars
    if len(geoid) < 12:
        return geoid
    return (
        f"state={geoid[:2]} county={geoid[2:5]} "
        f"tract={geoid[5:11]} block_group={geoid[11:]}"
    )


async def main(address: str) -> None:
    print(f"\nAuditing: {address}")

    section("[1] GEOCODING  —  Google Maps Geocoding API")
    geo, _ = await geocoding.geocode(address)
    print(f"  lat                 = {geo.lat}")
    print(f"  lng                 = {geo.lng}")
    print(f"  formatted_address   = {geo.formatted_address}")
    print(f"  verify              https://www.google.com/maps/place/{geo.lat},{geo.lng}")

    section("[2] SOLAR API  —  Google Solar buildingInsights:findClosest")
    roof, _ = await solar_api.get_roof_data(geo.lat, geo.lng, address)
    print(f"  building_name       = {roof.building_name!r}")
    print(f"  max_array_panels    = {roof.max_array_panels}")
    print(f"  max_kwh_year        = {roof.max_kwh_year}")
    print(f"  max_sunshine_hours  = {roof.max_sunshine_hours}")
    print(f"  has_existing_solar  = {roof.has_existing_solar}  (Phase 1 MOCK: always False)")
    print(f"  verify              https://sunroof.withgoogle.com/building/{geo.lat:.6f}/{geo.lng:.6f}/details")

    section("[3] CENSUS  —  ACS 5-year 2024 (released Dec 2025)")
    cens, _ = await census.get_block_group_data(geo.lat, geo.lng)
    income_str = (
        f"${cens.median_household_income:,.0f}/yr"
        if cens.median_household_income else "(no data)"
    )
    print(f"  block_group_geoid   = {cens.block_group_geoid}")
    print(f"  decoded             {_decode_geoid(cens.block_group_geoid)}")
    print(f"  median_hh_income    = {income_str}")
    print(f"  vintage             = ACS 2020-2024 (latest available)")
    print(f"  verify              https://data.census.gov/table/ACSDT5Y2024.B19013?g=1500000US{cens.block_group_geoid}")

    section("[4] NREL PVWATTS V8  —  4 kW system, 20° tilt, south-facing")
    pv, _ = await nrel.get_production(geo.lat, geo.lng)
    print(f"  ac_annual_kwh       = {pv.ac_annual_kwh:.0f} kWh/yr")
    print(f"  capacity_factor     = {pv.capacity_factor}")
    print(f"  solar_radiation     = {pv.solar_radiation} kWh/m²/day")
    print(f"  verify              https://pvwatts.nrel.gov/pvwatts.php  (lat={geo.lat:.4f}, lon={geo.lng:.4f})")

    section("[5] ASSESSOR  —  LA County (MOCK in Phase 1)")
    parc, _ = await assessor.get_parcel_data(geo.lat, geo.lng, address)
    print(f"  owner_occupied      = {parc.owner_occupied}  *** MOCK — not real data ***")
    print(f"  year_built          = {parc.year_built}      *** MOCK — not real data ***")
    print(f"  real source         https://assessor.lacounty.gov/ (Phase 2 integration)")

    section("[6] SCORING  —  truth-first 7-dimensional weighted sum")
    score, dims, mode, conf = scoring.compute_score(roof, cens, pv, parc)
    print(f"  weighting_mode      = {mode}")
    print(f"  score_confidence    = {conf:.2f}  ({conf:.0%} of weight backed by real data)")
    print(f"  reported score      = {score:.4f}")
    print()
    print(f"  {'dimension':<22} {'value':>8}  weight   contribution   source")
    print(f"  {'-' * 92}")
    available_sum = 0.0
    for name in WEIGHTS:
        dv = getattr(dims, name)
        w = WEIGHTS[name]
        if dv.value is None:
            print(f"  {name:<22} {'UNAVAIL':>8}  {w:>6.2f}   {'(excluded)':>12}   {dv.source}")
        else:
            contrib = dv.value * w
            available_sum += contrib
            print(f"  {name:<22} {dv.value:>8.4f}  {w:>6.2f}   {contrib:>12.4f}   {dv.source[:48]}")
    print(f"  {'-' * 92}")
    print(f"  available_weighted_sum = {available_sum:.4f}")
    print(f"  renormalized score     = {available_sum / conf if conf else 0:.4f}")

    section("[7] NARRATIVE  —  Gemini 2.5 Flash via Vertex AI (google-genai SDK)")
    txt, _ = await narrative.generate_narrative(geo.formatted_address, score, dims, conf)
    print(f"  length              = {len(txt)} chars")
    print(f"  text:\n{txt}")

    section("INDEPENDENT CROSS-CHECKS  --  raw input -> dimension derivations")
    if cens.median_household_income:
        print(f"  Census income -> income_qualification: (${cens.median_household_income:,.0f} - 40000) / 80000 = {(cens.median_household_income - 40000) / 80000:.4f}")
    if pv.ac_annual_kwh:
        print(f"  NREL kWh -> bill_pain:                 {pv.ac_annual_kwh:.0f} x $0.30 / $3000 = {pv.ac_annual_kwh * 0.30 / 3000:.4f}")
    if roof.max_kwh_year:
        print(f"  Solar kWh -> roof_potential:           {roof.max_kwh_year:.0f} / 15000 = {roof.max_kwh_year / 15000:.4f}")


if __name__ == "__main__":
    addr = sys.argv[1] if len(sys.argv) > 1 else "100 Long Beach Blvd, Long Beach, CA"
    asyncio.run(main(addr))
