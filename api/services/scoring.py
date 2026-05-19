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
    DacInfo,
    DimensionValue,
    NRELData,
    ParcelData,
    ScoreDimensions,
    SolarRoofData,
    UtilityInfo,
)
from api.services.dimensions import (
    bill_pain_dim,
    equity_proxy_dim_from_parcel,
    income_dim,
    ownership_dim_from_parcel,
    roof_potential_dim,
)

# Architectural baseline weights. Sum to 1.0. These are the long-term
# design weights — the values the scoring matrix would use if every
# dimension were live and producing real signal.
_BASELINE_WEIGHTS: dict[str, float] = {
    "roof_potential": 0.25,
    "income_qualification": 0.20,
    "ownership": 0.15,
    "bill_pain": 0.15,
    "equity_proxy": 0.10,
    "no_existing_solar": 0.10,
    "intent_signal": 0.05,
}

# Dimensions that are STRUCTURALLY UNAVAILABLE on every lead until their
# Phase 2 source ships. Distinct from per-lead missing data (e.g. parcel
# not resolved) — these dims emit value=None for 100% of leads currently.
# Leaving them at their baseline weight gives them 15% of total weight that
# can never produce signal — a 15% dead weight that compresses variance
# (empirically: stdev capped near 0.10 on the 100-parcel distribution test).
#
# TODO(Phase 2): when no_existing_solar gets a real detector (CV on Solar
# dataLayers or partner feed) AND intent_signal gets a CRM integration,
# remove the corresponding entries from this set. Weights snap back to
# _BASELINE_WEIGHTS automatically.
_PHASE_2_DEFERRED: frozenset[str] = frozenset({"no_existing_solar", "intent_signal"})


def _compute_effective_weights() -> dict[str, float]:
    """Static redistribution of Phase-2-deferred weight to active dimensions.

    This is NOT per-lead renormalization (the Phase 1.5a rule against that
    still holds — see feedback-no-score-renormalization). It's a one-time
    architectural correction that drops the always-NULL dims from the
    weight vector and proportionally redistributes their share to the
    dims that actually produce signal. The math:

      active_baseline_sum = sum(_BASELINE_WEIGHTS[k] for k not in _PHASE_2_DEFERRED)
                          = 0.85
      W'_i = _BASELINE_WEIGHTS[i] / active_baseline_sum  for active dims
      W'_i = 0.0                                          for Phase-2 deferred dims

    Per-lead missing data (e.g. parcel didn't resolve -> ownership/equity
    are None on that specific lead) STILL depresses the headline: those
    dims contribute 0 to the weighted_sum without being divided out.
    """
    active_sum = sum(
        w for k, w in _BASELINE_WEIGHTS.items() if k not in _PHASE_2_DEFERRED
    )
    return {
        k: (0.0 if k in _PHASE_2_DEFERRED else w / active_sum)
        for k, w in _BASELINE_WEIGHTS.items()
    }


WEIGHTS: dict[str, float] = _compute_effective_weights()


def _clip(x: float) -> float:
    return max(0.0, min(x, 1.0))


def _unavailable(note: str) -> DimensionValue:
    return DimensionValue(value=None, source="unavailable", note=note)


def _apply_dac_sash_union(parcel: ParcelData, dac: DacInfo | None) -> str:
    """DAC-SASH eligibility UNION rule (Phase 1.5e). NOT an override.

    A residential parcel qualifies for the DAC-SASH stream if EITHER:
      - the parcel sits inside an SB-535 DAC tract (in_dac), OR
      - the parcel is non-taxable residential (parsonage, community land
        trust, university-owned grad housing, etc.)

    Both populations are GRID Alternatives' DAC-SASH program targets.
    The two signals don't fight each other; they're additive — a union
    of two distinct qualifying segments mapped onto one program stream.
    Non-residential always routes to 'not_residential' regardless.
    """
    if not parcel.is_residential:
        return "not_residential"
    is_dac = bool(dac and dac.is_dac)
    if is_dac or not parcel.is_taxable:
        return "dac_sash"
    return "private"


def compute_score(
    roof: SolarRoofData,
    census: CensusData,
    nrel: NRELData,
    parcel: ParcelData | None,
    utility: UtilityInfo | None = None,
    dac: DacInfo | None = None,
) -> tuple[float, ScoreDimensions, str, float]:
    """Returns (score, dimensions, weighting_mode, score_confidence).
    Applies the DAC-SASH eligibility union rule by overriding parcel.stream
    in-place when DAC qualification applies (parcel objects are not shared
    state — they're built per-request from the BQ lookup).
    """
    if parcel is not None:
        ownership = ownership_dim_from_parcel(parcel)
        equity = equity_proxy_dim_from_parcel(parcel)
        # DAC-SASH eligibility union (Phase 1.5e). The parcel.stream as built
        # by the BQ unified table considers only is_taxable; here we widen it
        # to also pick up DAC residential parcels.
        parcel.stream = _apply_dac_sash_union(parcel, dac)
    else:
        ownership = _unavailable("Address not resolved to any LA County parcel")
        equity = _unavailable("Address not resolved to any LA County parcel")
    dims = ScoreDimensions(
        roof_potential=roof_potential_dim(roof),
        income_qualification=income_dim(census),
        ownership=ownership,
        bill_pain=bill_pain_dim(nrel, utility),
        equity_proxy=equity,
        no_existing_solar=_unavailable(
            "Public Solar API does not expose detected arrays. "
            "Phase-2-deferred — weight redistributed to active dimensions."
        ),
        intent_signal=_unavailable(
            "Requires CRM / web-signal integration (Phase 2). "
            "Phase-2-deferred — weight redistributed to active dimensions."
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
