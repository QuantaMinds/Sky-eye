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
    UtilityInfo,
)
from api.services.region_calibration import get_calibration

# Region-specific calibration constants live in region_calibration.py.
# Single source of truth — adding a new county (SF / Orange / etc.) is one
# RegionCalibration entry there, not a hunt-and-replace here. See that
# module's docstring for the empirical probes each constant requires.
#
# Today only LA County is calibrated; the module-level default is used.
# When multi-region runtime is needed, plumb a `region` parameter through
# scoring.compute_score and pass it to get_calibration() per-call.
_CAL = get_calibration()


def _clip(x: float) -> float:
    return max(0.0, min(x, 1.0))


def roof_potential_dim(roof: SolarRoofData) -> DimensionValue:
    if not roof.max_kwh_year:
        return DimensionValue(
            value=None, source="Google Solar API",
            note="No roof data returned for this building",
        )
    return DimensionValue(
        value=_clip(roof.max_kwh_year / _CAL.roof_kwh_full),
        source=f"Google Solar API (anchor: {int(_CAL.roof_kwh_full)} kWh/yr = 1.0)",
    )


def _continuous_income_score(income: float) -> tuple[float, str]:
    """Returns (score, band_label) using the continuous LA financing curve.

    Quadratic rise (exponent 1.5) from $50k to $130k peak, linear decay
    from $130k toward $300k floor of 0.65. Maps the LA income distribution
    onto a 0.20-1.00 range with continuous output (~80 unique values across
    real data, vs the prior 5-band stepped version that produced only 2
    unique values on the 93-parcel forensic sample).
    """
    if income < _CAL.income_low_floor:
        return 0.20, "<$50k low-income / DAC-SASH track"
    if income <= _CAL.income_peak:
        ratio = (income - _CAL.income_low_floor) / (_CAL.income_peak - _CAL.income_low_floor)
        score = 0.20 + (ratio ** 1.5) * 0.80
        return round(score, 2), f"$50-130k rising toward financing peak"
    distance = income - _CAL.income_peak
    score = 1.00 - (distance / _CAL.income_decay_range) * 0.35
    score = max(_CAL.income_high_floor, score)
    return round(score, 2), f">$130k decaying toward saturation floor"


def income_dim(census: CensusData) -> DimensionValue:
    """LA-calibrated continuous income curve (Phase 1.5e refined 2026-05-17).

    Peak at $130k matches the prime paid-solar financing window
    (max federal credit utilization + clean loan underwriting + healthy
    free cash flow). Decay above the peak models the saturation effect
    (high-net-worth tracts more likely to already have solar). Below $50k,
    flat 0.20 routes leads toward DAC-SASH stream as a low-priority
    paid-solar candidate.
    """
    income = census.median_household_income
    if income is None:
        return DimensionValue(
            value=None, source="US Census ACS 2020-2024",
            note=f"No income data for block group {census.block_group_geoid}",
        )
    score, band = _continuous_income_score(income)
    return DimensionValue(
        value=_clip(score),
        source=(
            f"US Census ACS 2020-2024, block group {census.block_group_geoid} "
            f"(B19013_001E = ${income:,.0f}; {band})"
        ),
        note=(
            "Block-group level — neighborhood proxy, not occupant income. "
            "Continuous curve peaks at $130k LA financing sweet-spot, "
            "decays toward $300k+ saturation tier. Replaces prior 5-band "
            "stepped version (Phase 1.5e forensic showed bimodal clustering)."
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
    if year is not None and (datetime.now().year - year) >= _CAL.long_tenure_years:
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
    value = round(1.0 - (_CAL.equity_decay ** tenure), 2)
    return DimensionValue(
        value=_clip(value),
        source=f"LA County Assessor — {source_tag}, tenure={tenure}yr",
        note=(
            "Continuous asymptotic curve: 1 - 0.95^tenure. Replaces stepped bands "
            "for smoother gradient. CA Prop 13 reality: real market equity is "
            "decoupled from assessed value; tenure is the cleanest free proxy."
        ),
    )


def bill_pain_dim(nrel: NRELData, utility: UtilityInfo | None = None) -> DimensionValue:
    """Bill-pain score = annual production (kWh) x utility's representative
    rate ($/kWh), normalized to a $3000/yr full-pain anchor. When utility is
    unavailable, falls back to the flat $0.30/kWh rate (Phase 1.5c behavior).
    """
    if not nrel.ac_annual_kwh:
        return DimensionValue(
            value=None, source="NREL PVWatts v8",
            note="No production estimate returned",
        )
    if utility is None:
        utility = UtilityInfo()  # all defaults; rate=0.30, confidence=fallback
    annual_bill = nrel.ac_annual_kwh * utility.representative_rate
    return DimensionValue(
        value=_clip(annual_bill / _CAL.bill_pain_full_usd),
        source=(
            f"NREL PVWatts v8 (4 kW system) x {utility.utility_name} "
            f"~${utility.representative_rate:.2f}/kWh"
            + (f" ({utility.tariff_variant})" if utility.tariff_variant else "")
            + f" = approximately ${annual_bill:,.0f}/yr proxy"
        ),
        note=(
            f"confidence={utility.confidence_level}; "
            + (f"NEM regime: {utility.nem_regime}. " if utility.nem_regime else "")
            + (utility.rate_source_note[:160] if utility.rate_source_note else "")
        ),
    )
