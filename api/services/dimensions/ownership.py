"""Ownership dimension public surface: DimensionValue builders.

Classification logic lives in _ownership_classifier.py — this file just
turns (profile_label, score) tuples into DimensionValue for the scoring
engine and preserves the 1.5c.2a byte-identical fallback strings so the
parity snapshot stays green.
"""
from __future__ import annotations

from datetime import datetime

from api.models.lead import AssessorData, DimensionValue, ParcelData
from api.services.dimensions._common import CAL, resolve_arms_length_year
from api.services.dimensions._ownership_classifier import (
    CORP_SHELL_PATTERN,
    PROFILE_NOTES,
    determine_ownership_profile,
)


def ownership_dim(assessor: AssessorData) -> DimensionValue:
    """Legacy AssessorData path (pre-1.5c). Kept for backward compat."""
    if assessor.owner_occupied is None:
        return DimensionValue(value=None, source="unavailable",
                              note="LA County Assessor integration pending (Phase 1.5c)")
    return DimensionValue(
        value=1.0 if assessor.owner_occupied else 0.0,
        source="LA County Assessor",
    )


def ownership_dim_from_parcel(
    parcel: ParcelData,
    scraped_mail_data: dict | None = None,
) -> DimensionValue:
    """DimensionValue wrapper around the classifier.

    For scraped_mail_data=None the source/note strings remain byte-identical
    to the 1.5c.2a baseline (parity snapshot pinned). When scraped data is
    supplied the wrapper builds the DimensionValue from the resolved profile.
    """
    if scraped_mail_data is None:
        if parcel.has_homeowners_exemption:
            return DimensionValue(
                value=0.95, source="LA County Assessor — Homeowner's Exemption claimed",
            )
        year, _ = resolve_arms_length_year(parcel)
        if year is not None and (datetime.now().year - year) >= CAL.long_tenure_years:
            return DimensionValue(
                value=0.40, source="LA County Assessor — long tenure, no exemption",
                note=(
                    f"Property held since {year} ({datetime.now().year - year}+ yr) but no "
                    "Homeowner's Exemption claimed. Likely inherited / family trust / unfiled "
                    "owner-occupant. Disambiguate via mailing-address join (Phase 1.5c.2b)."
                ),
            )
        return DimensionValue(
            value=0.15, source="LA County Assessor — no exemption, short tenure",
            note="No Homeowner's Exemption + short tenure -> likely investor / rental.",
        )

    label, score = determine_ownership_profile(parcel, scraped_mail_data)
    return DimensionValue(
        value=score,
        source=f"LA County Assessor + scraped mailing — {label}",
        note=PROFILE_NOTES[label],
    )
