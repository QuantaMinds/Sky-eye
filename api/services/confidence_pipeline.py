"""TaxLens 5-gate confidence pipeline.

Each gate returns:
  True  -- gate fires (evidence consistent with unpermitted construction)
  False -- gate fails (counter-evidence — e.g. permit found, low conf)
  None  -- input unavailable; drop from the score and re-normalize

The final score is (passing gates) / (available gates). If every gate
is None the score is None — never substitute 0.0 (Rule 3).

Why drop-and-renormalize: a None gate is NOT a 0.5 ambiguous signal.
A missing permits dataset shouldn't penalize a parcel any more than it
should reward one. Re-normalizing the remaining gates gives the honest
answer: 'of the data we have, X% says unpermitted construction.'

Thresholds are constants here, not config, by design — drift in
thresholds without a code review is the kind of change Rule 4 was
written to catch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ALPHAEARTH_DISTANCE_THRESHOLD = 0.4
GEMINI_CONFIDENCE_THRESHOLD = 0.7
# $250/sqft is the rough LB residential improvement value blend; 100 sqft -> $25K uplift
VALUE_UPLIFT_SQFT_THRESHOLD = 100.0
NO_CHANGE_TYPE = "no_significant_change"

_GATE_NAMES = (
    "embedding_distance", "no_permit", "naip_visual_change",
    "classifier_confidence", "value_uplift",
)


@dataclass(frozen=True)
class GateOutcome:
    """Per-gate result + the raw input value for audit trail."""
    fired: Optional[bool]      # True | False | None
    raw_input: float | str | bool | None
    note: str


@dataclass(frozen=True)
class ConfidenceResult:
    gates: dict[str, GateOutcome]
    final_score: float | None     # None when every gate is unavailable
    available_gates: int
    fired_gates: int


def _gate_embedding(distance: float | None) -> GateOutcome:
    if distance is None:
        return GateOutcome(None, None, "alphaearth distance unavailable")
    fired = distance > ALPHAEARTH_DISTANCE_THRESHOLD
    return GateOutcome(fired, distance,
                       f"distance={distance:.3f} vs threshold {ALPHAEARTH_DISTANCE_THRESHOLD}")


def _gate_permit(has_permit_result: Optional[bool]) -> GateOutcome:
    if has_permit_result is None:
        return GateOutcome(None, None, "permits dataset coverage unavailable")
    # has_permit=True  -> permit found    -> gate fails (NOT unpermitted)
    # has_permit=False -> no permit found -> gate fires (POSSIBLY unpermitted)
    return GateOutcome(not has_permit_result, has_permit_result,
                       "permit found" if has_permit_result else "no permit in window")


def _gate_naip_visual(change_type: str | None) -> GateOutcome:
    if change_type is None:
        return GateOutcome(None, None, "classifier did not run")
    fired = change_type != NO_CHANGE_TYPE
    return GateOutcome(fired, change_type, f"change_type={change_type}")


def _gate_classifier_conf(conf: float | None) -> GateOutcome:
    if conf is None:
        return GateOutcome(None, None, "classifier confidence unavailable")
    fired = conf > GEMINI_CONFIDENCE_THRESHOLD
    return GateOutcome(fired, conf,
                       f"conf={conf:.2f} vs threshold {GEMINI_CONFIDENCE_THRESHOLD}")


def _gate_value(added_sqft: float | None) -> GateOutcome:
    if added_sqft is None:
        return GateOutcome(None, None, "estimated_added_sqft unavailable")
    fired = added_sqft > VALUE_UPLIFT_SQFT_THRESHOLD
    return GateOutcome(fired, added_sqft,
                       f"added_sqft={added_sqft:.0f} vs threshold {VALUE_UPLIFT_SQFT_THRESHOLD}")


def evaluate(
    *, alphaearth_distance: float | None,
    has_permit_result: Optional[bool],
    gemini_change_type: str | None,
    gemini_confidence: float | None,
    gemini_added_sqft: float | None,
) -> ConfidenceResult:
    """Run all 5 gates. Final score is (passes / available)."""
    gates = {
        "embedding_distance":    _gate_embedding(alphaearth_distance),
        "no_permit":             _gate_permit(has_permit_result),
        "naip_visual_change":    _gate_naip_visual(gemini_change_type),
        "classifier_confidence": _gate_classifier_conf(gemini_confidence),
        "value_uplift":          _gate_value(gemini_added_sqft),
    }
    available = sum(1 for g in gates.values() if g.fired is not None)
    fired = sum(1 for g in gates.values() if g.fired is True)
    score = (fired / available) if available > 0 else None
    return ConfidenceResult(
        gates=gates, final_score=score,
        available_gates=available, fired_gates=fired,
    )
