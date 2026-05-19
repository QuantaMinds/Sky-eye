"""Shared helpers for per-dimension builders.

Kept intentionally tiny — anything that grows beyond 5-10 lines and is used
by more than one dimension belongs in its own module. Region calibration
constants flow from api.services.region_calibration; this module just
exposes a single bound instance to avoid every dimension file importing it.
"""
from __future__ import annotations

from api.models.lead import ParcelData
from api.services.region_calibration import get_calibration

CAL = get_calibration()


def clip(x: float) -> float:
    return max(0.0, min(x, 1.0))


def resolve_arms_length_year(parcel: ParcelData) -> tuple[int | None, str]:
    """Best-available tenure-start year for Prop 13 mechanics.

    Uses arms_length_year (already LEAST(land_base_year, improvement_base_year)
    with NULLIF sentinel guards in BQ). Falls back to recording_year if the
    base years are missing. Returns (year, source_tag) so dimensions can
    surface provenance in their DimensionValue.source field.
    """
    if parcel.arms_length_year is not None and parcel.arms_length_year > 0:
        return parcel.arms_length_year, "LEAST(land_base_year, improvement_base_year)"
    if parcel.recording_year is not None and parcel.recording_year > 0:
        return parcel.recording_year, "recording_year (fallback — may include trust transfers)"
    return None, "no tenure signal available"
