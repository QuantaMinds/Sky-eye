"""LA County assessor lookup — UNAVAILABLE in Phase 1.

Truth-first: we don't have real ownership / year-built data yet, so this
service returns explicit Nones. Real integration lands in Phase 1.5c
(LA County Assessor Open Data -> BigQuery -> spatial lookup, with
Homeowner's Exemption as the ownership signal).
"""
from __future__ import annotations

from api.models.lead import AssessorData


async def get_parcel_data(
    lat: float, lng: float, address: str
) -> tuple[AssessorData, bool]:
    """Returns (data, cache_hit). All fields are None — see module docstring."""
    return AssessorData(owner_occupied=None, year_built=None), False
