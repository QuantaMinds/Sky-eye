"""Per-dimension builders that turn raw service data into DimensionValue.

Kept separate from scoring.py to honor the <100-LOC-per-file rule.
Each builder returns a DimensionValue with either a real value+source or
``value=None`` with ``source="unavailable"`` (NEVER a substitute constant).

# Cohesion exception accepted per CLAUDE.md Rule 1, with a HARD CEILING of
# 200 LOC tracked in the backlog (see project_phase15_backlog memory entry
# "File-size: _dimension_builders.py 200-LOC hard ceiling"). Whichever later
# phase pushes this file past 200 lines must split it into
# api/services/dimensions/{roof,income,ownership,bill_pain,equity}.py.
"""
from __future__ import annotations

from datetime import datetime

from api.models.lead import (
    AssessorData,
    CensusData,
    DimensionValue,
    NRELData,
    ParcelData,
    SolarRoofData,
)

# Anchors used to normalize raw measurements into [0, 1].
ROOF_KWH_FULL = 15_000.0
INCOME_FLOOR = 40_000.0
INCOME_CEIL = 120_000.0
BILL_PAIN_FULL_USD = 3_000.0
UTILITY_RATE_USD_PER_KWH = 0.30  # Flat proxy; tiered LADWP/SCE pending Phase 1.5d
# Equity formula constants — continuous asymptotic curve (see Prop 13 memory).
EQUITY_DECAY = 0.95
# Long-tenure threshold for the "owner without claimed exemption" cohort
# (Belmont Shore-style: 50-year SFR with no Homeowner's Exemption claimed).
LONG_TENURE_YEARS = 25


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


def _resolve_arms_length_year(parcel: ParcelData) -> tuple[int | None, str]:
    """Returns (year, source_tag). Uses arms_length_year from BQ (already
    computed as LEAST(land_base_year, improvement_base_year) with NULLIF
    sentinel guards). Falls back to recording_year if base years missing.
    """
    if parcel.arms_length_year is not None and parcel.arms_length_year > 0:
        return parcel.arms_length_year, "LEAST(land_base_year, improvement_base_year)"
    if parcel.recording_year is not None and parcel.recording_year > 0:
        return parcel.recording_year, "recording_year (fallback — may include trust transfers)"
    return None, "no tenure signal available"


def ownership_dim_from_parcel(parcel: ParcelData) -> DimensionValue:
    """3-bucket classification using exemption + tenure heuristic.

    Until Phase 1.5c.2 (mailing-address join), absentee-investor vs
    long-held-unfiled-owner-occupant cannot be cleanly separated. The 25-year
    threshold catches the Belmont Shore pattern (50yr hold, no exemption,
    likely inherited or trust-held) as `UNKNOWN_OR_TRUST` rather than
    misclassifying it as an investor.
    """
    if parcel.has_homeowners_exemption:
        return DimensionValue(
            value=0.95, source="LA County Assessor — Homeowner's Exemption claimed",
        )
    year, _ = _resolve_arms_length_year(parcel)
    if year is not None and (datetime.now().year - year) >= LONG_TENURE_YEARS:
        return DimensionValue(
            value=0.40, source="LA County Assessor — long tenure, no exemption",
            note=(
                f"Property held since {year} ({datetime.now().year - year}+ yr) but no "
                "Homeowner's Exemption claimed. Likely inherited / family trust / unfiled "
                "owner-occupant. Disambiguate via mailing-address join (Phase 1.5c.2)."
            ),
        )
    return DimensionValue(
        value=0.15, source="LA County Assessor — no exemption, short tenure",
        note="No Homeowner's Exemption + short tenure -> likely investor / rental.",
    )


def equity_proxy_dim_from_parcel(parcel: ParcelData) -> DimensionValue:
    """Prop 13 tenure-based equity proxy: 1 - 0.95^tenure (continuous curve)."""
    year, source_tag = _resolve_arms_length_year(parcel)
    if year is None:
        return DimensionValue(
            value=None, source="unavailable",
            note="No base year, arms_length_year, or recording date in parcel record",
        )
    tenure = max(0, datetime.now().year - year)
    value = round(1.0 - (EQUITY_DECAY ** tenure), 2)
    return DimensionValue(
        value=_clip(value),
        source=f"LA County Assessor — {source_tag}, tenure={tenure}yr",
        note=(
            "Continuous asymptotic curve: 1 - 0.95^tenure. Replaces stepped bands "
            "for smoother gradient. CA Prop 13 reality: real market equity is "
            "decoupled from assessed value; tenure is the cleanest free proxy."
        ),
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
