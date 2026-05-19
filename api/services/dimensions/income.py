"""Income-qualification dimension: continuous LA-calibrated financing curve.

Quadratic rise from income_low_floor ($50k) to income_peak ($130k); linear
decay from peak toward income_high_floor (0.65 saturation). Replaces the
prior stepped 5-band scheme that collapsed to 2 unique values on real LA
block-group medians (Phase 1.5e forensic 2026-05-17). See
feedback-continuous-curves-over-stepped-bands.
"""
from __future__ import annotations

from api.models.lead import CensusData, DimensionValue
from api.services.dimensions._common import CAL, clip


def _continuous_income_score(income: float) -> tuple[float, str]:
    """Returns (score, band_label) — the continuous LA financing curve."""
    if income < CAL.income_low_floor:
        return 0.20, "<$50k low-income / DAC-SASH track"
    if income <= CAL.income_peak:
        ratio = (income - CAL.income_low_floor) / (CAL.income_peak - CAL.income_low_floor)
        score = 0.20 + (ratio ** 1.5) * 0.80
        return round(score, 2), "$50-130k rising toward financing peak"
    distance = income - CAL.income_peak
    score = 1.00 - (distance / CAL.income_decay_range) * 0.35
    score = max(CAL.income_high_floor, score)
    return round(score, 2), ">$130k decaying toward saturation floor"


def income_dim(census: CensusData) -> DimensionValue:
    income = census.median_household_income
    if income is None:
        return DimensionValue(
            value=None, source="US Census ACS 2020-2024",
            note=f"No income data for block group {census.block_group_geoid}",
        )
    score, band = _continuous_income_score(income)
    return DimensionValue(
        value=clip(score),
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
