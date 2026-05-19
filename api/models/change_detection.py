"""Pydantic request/response shapes for POST /api/v1/detect-changes.

Truth-first contract: every numeric output that might be unknown is
Optional with a sibling `source` field, and the per-gate breakdown
preserves the raw input value the gate saw so callers can audit.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DetectChangesRequest(BaseModel):
    # bbox order matches GeoJSON / Earth Engine: [west, south, east, north]
    bbox: tuple[float, float, float, float] = Field(
        description="[lon_min, lat_min, lon_max, lat_max] WGS84",
    )
    year_a: int = Field(ge=2010, le=2030, description="Before year")
    year_b: int = Field(ge=2010, le=2030, description="After year (year_b > year_a)")
    min_confidence: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Filter out detections with final_score below this",
    )
    top_n: int = Field(
        default=50, ge=1, le=500,
        description="Cap the candidates considered before classifier/permit/score",
    )


class GateBreakdown(BaseModel):
    """Per-gate result. `fired=None` means input was unavailable and the
    gate was dropped from the score (Rule 3, no synthetic 0.5)."""
    fired: bool | None
    raw_input: float | str | bool | None
    note: str


class Detection(BaseModel):
    apn: str
    final_score: float | None
    available_gates: int
    fired_gates: int
    gates: dict[str, GateBreakdown]

    # Inputs that fed the gates (audit trail)
    alphaearth_distance: float | None
    change_type: str | None
    classifier_confidence: float | None
    estimated_added_sqft: float | None
    evidence: str | None

    # Provenance
    naip_a_date: str | None
    naip_b_date: str | None
    embedding_a_date: str
    embedding_b_date: str
    classifier_source: str   # 'gemini_pro' | 'unavailable'
    permit_source: str       # 'permits_bq' | 'unavailable'


class DetectChangesResponse(BaseModel):
    bbox: tuple[float, float, float, float]
    year_a: int
    year_b: int
    candidates_considered: int
    detections_above_threshold: int
    detections: list[Detection]
    persisted_rows: int = Field(
        description="Rows actually written to leadlens.change_events. "
                    "Less than detections_above_threshold when some had "
                    "final_score=None (truth-first: no fake confidence persisted)."
    )
    persistence_skipped: int = Field(
        description="Detections returned in the response but NOT persisted "
                    "(missing NOT NULL fields — e.g. final_score=None)."
    )
