"""7-dimensional lead score — truth-first, NON-renormalized.

Each dimension is a ``DimensionValue`` carrying its origin. When a dim has
``value=None`` (unavailable), it contributes 0 to the headline score. We
DO NOT divide by ``sum(available_weights)`` — absent data must visibly
depress the headline number (see feedback-no-score-renormalization).

``score_confidence`` is reported separately = fraction of total weight
backed by real data (1.0 = every dim available; 0.0 = nothing known).
A property with only 60% of dims available can therefore score AT MOST 0.60.
"""
from __future__ import annotations

from api.models.lead import (
    CensusData,
    DimensionValue,
    NRELData,
    ParcelData,
    ScoreDimensions,
    SolarRoofData,
)
from api.services._dimension_builders import (
    bill_pain_dim,
    equity_proxy_dim_from_parcel,
    income_dim,
    ownership_dim_from_parcel,
    roof_potential_dim,
)

WEIGHTS: dict[str, float] = {
    "roof_potential": 0.25,
    "income_qualification": 0.20,
    "ownership": 0.15,
    "bill_pain": 0.15,
    "equity_proxy": 0.10,
    "no_existing_solar": 0.10,
    "intent_signal": 0.05,
}


def _clip(x: float) -> float:
    return max(0.0, min(x, 1.0))


def _unavailable(note: str) -> DimensionValue:
    return DimensionValue(value=None, source="unavailable", note=note)


def compute_score(
    roof: SolarRoofData,
    census: CensusData,
    nrel: NRELData,
    parcel: ParcelData | None,
) -> tuple[float, ScoreDimensions, str, float]:
    """Returns (score, dimensions, weighting_mode, score_confidence)."""
    if parcel is not None:
        ownership = ownership_dim_from_parcel(parcel)
        equity = equity_proxy_dim_from_parcel(parcel)
    else:
        ownership = _unavailable("Address not resolved to any LA County parcel")
        equity = _unavailable("Address not resolved to any LA County parcel")
    dims = ScoreDimensions(
        roof_potential=roof_potential_dim(roof),
        income_qualification=income_dim(census),
        ownership=ownership,
        bill_pain=bill_pain_dim(nrel),
        equity_proxy=equity,
        no_existing_solar=_unavailable(
            "Public Solar API does not expose detected arrays"
        ),
        intent_signal=_unavailable(
            "Requires CRM / web-signal integration (Phase 2)"
        ),
    )

    available_weight_sum = 0.0
    weighted_sum = 0.0
    for name, weight in WEIGHTS.items():
        dim: DimensionValue = getattr(dims, name)
        if dim.value is None:
            continue
        weighted_sum += dim.value * weight
        available_weight_sum += weight

    if available_weight_sum == 0.0:
        return 0.0, dims, "no_signals", 0.0

    # NON-renormalized: missing dims contribute 0 to the headline.
    # Confidence stays separate so callers can distinguish "low data" from "low fit".
    score = _clip(weighted_sum)
    confidence = available_weight_sum  # already in [0, 1] since weights sum to 1
    mode = (
        "all_signals_available"
        if available_weight_sum >= 0.9999
        else "available_signals_only"
    )
    return score, dims, mode, confidence
