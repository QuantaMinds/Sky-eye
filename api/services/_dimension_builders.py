"""Per-dimension builders that turn raw service data into DimensionValue.

Kept separate from scoring.py to honor the <100-LOC-per-file rule.
Each builder returns a DimensionValue with either a real value+source or
``value=None`` with ``source="unavailable"`` (NEVER a substitute constant).
"""
from __future__ import annotations

from api.models.lead import (
    AssessorData,
    CensusData,
    DimensionValue,
    NRELData,
    SolarRoofData,
)

# Anchors used to normalize raw measurements into [0, 1].
ROOF_KWH_FULL = 15_000.0
INCOME_FLOOR = 40_000.0
INCOME_CEIL = 120_000.0
BILL_PAIN_FULL_USD = 3_000.0
UTILITY_RATE_USD_PER_KWH = 0.30  # Flat proxy; tiered LADWP/SCE pending Phase 1.5d


def _clip(x: float) -> float:
    return max(0.0, min(x, 1.0))


def roof_potential_dim(roof: SolarRoofData) -> DimensionValue:
    if not roof.max_kwh_year:
        return DimensionValue(
            value=None, source="Google Solar API",
            note="No roof data returned for this building",
        )
    return DimensionValue(
        value=_clip(roof.max_kwh_year / ROOF_KWH_FULL),
        source=f"Google Solar API (anchor: {int(ROOF_KWH_FULL)} kWh/yr = 1.0)",
    )


def income_dim(census: CensusData) -> DimensionValue:
    income = census.median_household_income
    if income is None:
        return DimensionValue(
            value=None, source="US Census ACS 2020-2024",
            note=f"No income data for block group {census.block_group_geoid}",
        )
    return DimensionValue(
        value=_clip((income - INCOME_FLOOR) / (INCOME_CEIL - INCOME_FLOOR)),
        source=(
            f"US Census ACS 2020-2024, block group {census.block_group_geoid} "
            f"(B19013_001E = ${income:,.0f})"
        ),
        note=(
            "Block-group level — neighborhood proxy, not occupant income. "
            "National anchor window; LA-calibrated window pending Phase 1.5e."
        ),
    )


def ownership_dim(assessor: AssessorData) -> DimensionValue:
    if assessor.owner_occupied is None:
        return DimensionValue(
            value=None, source="unavailable",
            note="LA County Assessor integration pending (Phase 1.5c)",
        )
    return DimensionValue(
        value=1.0 if assessor.owner_occupied else 0.0,
        source="LA County Assessor",
    )


def bill_pain_dim(nrel: NRELData) -> DimensionValue:
    if not nrel.ac_annual_kwh:
        return DimensionValue(
            value=None, source="NREL PVWatts v8",
            note="No production estimate returned",
        )
    annual_bill = nrel.ac_annual_kwh * UTILITY_RATE_USD_PER_KWH
    return DimensionValue(
        value=_clip(annual_bill / BILL_PAIN_FULL_USD),
        source=(
            f"NREL PVWatts v8 (4 kW system) × flat ${UTILITY_RATE_USD_PER_KWH}/kWh "
            f"= ~${annual_bill:,.0f}/yr proxy"
        ),
        note="Flat-rate proxy; tiered LADWP/SCE rates pending Phase 1.5d",
    )
