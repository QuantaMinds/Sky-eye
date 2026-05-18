"""Phase 1.5c gate: validate every record in the labeled-addresses fixture.

For each of the 27 fixture records this runner:
  1. Calls parcel_lookup.lookup_by_point(lat, lng) using the geocoded coords
     already in the fixture (no live Google Geocoding spend in the gate).
  2. Asserts the resolved APN matches the fixture's expected AIN
     (validates BQ ST_CONTAINS spatial routing).
  3. Asserts parcel.use_category, is_residential, is_taxable, stream match
     the fixture's expected values.
  4. Computes ownership_dim_from_parcel + equity_proxy_dim_from_parcel and
     asserts both land in the band predicted by the parcel's exemption-state
     and tenure (validates the new scoring math from Phase 1.5c).

Phase 1.5c is gated by this runner returning 0 failures across all 27.

Run with:
    python tests/run_phase_15c_gate.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from api.services import parcel_lookup  # noqa: E402
from api.services._dimension_builders import (  # noqa: E402
    equity_proxy_dim_from_parcel,
    ownership_dim_from_parcel,
)
from api.services.region_calibration import get_calibration  # noqa: E402

LONG_TENURE_YEARS = get_calibration().long_tenure_years

FIXTURE = Path(__file__).parent / "fixtures" / "labeled_addresses.json"
TOLERANCE = 0.02  # allow ±0.02 on equity proxy comparison

# Addresses with these tokens are condo / apartment units. Per LA County data
# structure, many AINs share one building polygon — ST_CONTAINS returns a
# sibling unit, not the queried unit. Same-building AIN counts as a pass.
# See feedback-multi-unit-ain-polygon-ambiguity memory.
_UNIT_MARKERS = (" NO ", " APT ", " UNIT ", " PENT", " SUITE ", " STE ", " #")


def _is_multi_unit(addr: str) -> bool:
    return any(marker in addr.upper() for marker in _UNIT_MARKERS)


def _same_building(apn_a: str, apn_b: str) -> bool:
    """LA County AIN structure: NNNN-NNN-NNN = book-page-parcel.
    Sibling units within one building share the first 7 digits (book+page).
    """
    return apn_a[:7] == apn_b[:7] if len(apn_a) >= 7 and len(apn_b) >= 7 else False


def expected_stream(use_category: str, property_taxable: str) -> str:
    if use_category == "Residential" and property_taxable == "Y":
        return "private"
    if use_category == "Residential" and property_taxable == "N":
        return "dac_sash"
    return "not_residential"


def expected_ownership_score(has_exemption: bool, tenure: int | None) -> float:
    if has_exemption:
        return 0.95
    if tenure is not None and tenure >= LONG_TENURE_YEARS:
        return 0.40
    return 0.15


def expected_equity_score(tenure: int | None) -> float | None:
    if tenure is None:
        return None
    return round(1.0 - (0.95 ** tenure), 2)


def run_assertions(record: dict[str, Any], parcel: Any) -> list[tuple[str, bool, str]]:
    """Returns list of (assertion_name, passed, detail)."""
    results: list[tuple[str, bool, str]] = []

    # 1. parcel exists
    if parcel is None:
        results.append(("parcel_resolved", False,
                        f"parcel_lookup returned None for ({record.get('lat')}, {record.get('lng')})"))
        return results
    results.append(("parcel_resolved", True, f"apn={parcel.apn}"))

    # 2. APN match — strict for SFR, same-building OK for multi-unit
    fixture_ain = str(record.get("ain", "")).strip()
    addr = record.get("property_location", "") or ""
    is_condo = _is_multi_unit(addr)
    if parcel.apn == fixture_ain:
        results.append(("apn_match", True, f"exact match"))
    elif is_condo and _same_building(parcel.apn, fixture_ain):
        results.append(("apn_match_multi_unit", True,
                        f"sibling unit in same building: expected {fixture_ain!r}, "
                        f"got {parcel.apn!r} (structural — see memory)"))
    else:
        results.append(("apn_match", False,
                        f"expected {fixture_ain!r}, got {parcel.apn!r}"))
        return results  # remaining assertions meaningless if wrong building

    # 3. Use category
    fixture_cat = record.get("use_category", "")
    cat_ok = parcel.use_category == fixture_cat
    results.append(("use_category_match", cat_ok,
                    f"expected {fixture_cat!r}, got {parcel.use_category!r}"))

    # 4. is_residential / is_taxable / stream
    expected_taxable = record.get("property_taxable") == "Y"
    results.append(("is_taxable_match", parcel.is_taxable == expected_taxable,
                    f"expected {expected_taxable}, got {parcel.is_taxable}"))

    exp_stream = expected_stream(fixture_cat, record.get("property_taxable", ""))
    results.append(("stream_match", parcel.stream == exp_stream,
                    f"expected {exp_stream!r}, got {parcel.stream!r}"))

    # 5/6. Ownership + equity dimensions — only meaningful for residential
    if not parcel.is_residential:
        results.append(("ownership_equity_skipped", True, "non-residential — N/A"))
        return results

    has_exemption = parcel.has_homeowners_exemption
    if parcel.arms_length_year is not None:
        tenure = max(0, datetime.now().year - parcel.arms_length_year)
    else:
        tenure = None

    ownership = ownership_dim_from_parcel(parcel)
    expected_own = expected_ownership_score(has_exemption, tenure)
    own_ok = ownership.value is not None and abs(ownership.value - expected_own) < TOLERANCE
    results.append(("ownership_score_band", own_ok,
                    f"expected {expected_own}, got {ownership.value} "
                    f"(exemption={has_exemption}, tenure={tenure})"))

    equity = equity_proxy_dim_from_parcel(parcel)
    expected_eq = expected_equity_score(tenure)
    if expected_eq is None:
        eq_ok = equity.value is None
        results.append(("equity_null_when_no_tenure", eq_ok,
                        f"tenure missing -> expected null, got {equity.value}"))
    else:
        eq_ok = equity.value is not None and abs(equity.value - expected_eq) < TOLERANCE
        results.append(("equity_score_formula", eq_ok,
                        f"expected {expected_eq}, got {equity.value} (tenure={tenure})"))

    return results


async def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = fixture["records"]
    print(f"Phase 1.5c gate: {len(records)} records from {FIXTURE.name}\n")

    total_assertions = 0
    failed_records: list[tuple[str, list]] = []

    for i, record in enumerate(records, 1):
        label = record.get("label", record.get("ain", "?"))
        lat, lng = record.get("lat"), record.get("lng")
        if lat is None or lng is None:
            print(f"  {i:2}. {label[:40]:<40} SKIP (no coords in fixture)")
            continue

        parcel, _ = await parcel_lookup.lookup_by_point(float(lat), float(lng))
        results = run_assertions(record, parcel)
        failed = [(n, d) for n, ok, d in results if not ok]
        total_assertions += len(results)

        if failed:
            failed_records.append((label, failed))
            print(f"  {i:2}. {label[:40]:<40} FAIL ({len(failed)} of {len(results)})")
            for n, d in failed:
                print(f"          - {n}: {d}")
        else:
            apn_short = parcel.apn if parcel else "?"
            print(f"  {i:2}. {label[:40]:<40} PASS  apn={apn_short}  ({len(results)} asserts)")

    print()
    print(f"=== Summary ===")
    print(f"  records:    {len(records)}")
    print(f"  passing:    {len(records) - len(failed_records)}")
    print(f"  failing:    {len(failed_records)}")
    print(f"  assertions: {total_assertions}")
    return 0 if not failed_records else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
