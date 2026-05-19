"""POST /api/v1/detect-changes — TaxLens change detection endpoint.

Orchestrates the full pipeline:
  bbox -> AlphaEarth top-N candidates (cheap filter)
    -> NAIP chip pair for each candidate
    -> Gemini Pro classifier (expensive — only on candidates)
    -> permit_matcher lookup (tri-state)
    -> 5-gate confidence pipeline
    -> filter by min_confidence, return ranked detections

Sync endpoint. For a typical small bbox this runs in 30-90s — the
inner-loop Gemini Pro vision call dominates. If a customer needs
larger bboxes, split this into batch/poll (like /batch-score did).
That's deferred until a real consumer asks.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter

from api.models.change_detection import (
    Detection, DetectChangesRequest, DetectChangesResponse, GateBreakdown,
)
from api.services import (
    change_detector, change_events_writer, chip_extractor, confidence_pipeline,
    lb_parcels, multimodal_classifier, permit_matcher,
)

router = APIRouter(prefix="/api/v1", tags=["taxlens"])


def _permit_window(year_a: int, year_b: int) -> tuple[dt.date, dt.date]:
    """The change happened between the two imagery years; a legitimate
    permit could have been issued any time from 12mo BEFORE year_a (some
    construction shows up the year after the permit) through year_b."""
    return dt.date(year_a - 1, 1, 1), dt.date(year_b, 12, 31)


def _detection_for(
    cand: change_detector.ChangeCandidate,
    cls_result: multimodal_classifier.ClassificationResult,
    cls_inputs: dict[str, Any],
    has_permit_result: bool | None,
    permit_source: str,
) -> Detection:
    """Run the confidence pipeline for one candidate and pack the
    response shape (gate breakdown + audit trail)."""
    conf = confidence_pipeline.evaluate(
        alphaearth_distance=cand.distance,
        has_permit_result=has_permit_result,
        gemini_change_type=cls_result.change_type,
        gemini_confidence=cls_result.confidence_0_1,
        gemini_added_sqft=cls_result.estimated_added_sqft,
    )
    return Detection(
        apn=cand.apn,
        final_score=conf.final_score,
        available_gates=conf.available_gates,
        fired_gates=conf.fired_gates,
        gates={
            name: GateBreakdown(
                fired=g.fired, raw_input=g.raw_input, note=g.note,
            ) for name, g in conf.gates.items()
        },
        alphaearth_distance=cand.distance,
        change_type=cls_result.change_type,
        classifier_confidence=cls_result.confidence_0_1,
        estimated_added_sqft=cls_result.estimated_added_sqft,
        evidence=cls_result.evidence,
        naip_a_date=cls_inputs.get("naip_a_date"),
        naip_b_date=cls_inputs.get("naip_b_date"),
        embedding_a_date=cand.embedding_a_date,
        embedding_b_date=cand.embedding_b_date,
        classifier_source=cls_result.source,
        permit_source=permit_source,
    )


@router.post("/detect-changes", response_model=DetectChangesResponse)
async def detect_changes(req: DetectChangesRequest) -> DetectChangesResponse:
    lon_min, lat_min, lon_max, lat_max = req.bbox
    permit_start, permit_end = _permit_window(req.year_a, req.year_b)

    candidates = change_detector.detect_changes_in_bbox(
        lon_min, lat_min, lon_max, lat_max,
        req.year_a, req.year_b, top_n=req.top_n,
    )

    detections: list[Detection] = []
    for cand in candidates:
        parcel = lb_parcels.get_parcel_geometry(cand.apn)
        chips = chip_extractor.fetch_pair(cand.apn, req.year_a, req.year_b)
        cls_result, _ = await multimodal_classifier.classify(
            apn=cand.apn,
            sqft=(parcel or {}).get("sqft_main"),
            use_subcategory=(parcel or {}).get("use_subcategory", ""),
            png_a=chips.naip_a.png, png_b=chips.naip_b.png,
            naip_a_date=chips.naip_a.image_date or "",
            naip_b_date=chips.naip_b.image_date or "",
        )
        permit_hit = permit_matcher.has_permit(cand.apn, permit_start, permit_end)
        permit_source = (
            "permits_bq" if permit_hit is not None else "unavailable"
        )
        detections.append(_detection_for(
            cand, cls_result,
            {"naip_a_date": chips.naip_a.image_date,
             "naip_b_date": chips.naip_b.image_date},
            permit_hit, permit_source,
        ))

    # Filter by min_confidence (None scores are kept — they signal "we
    # don't know" and may still be worth reviewing).
    kept = [
        d for d in detections
        if d.final_score is None or d.final_score >= req.min_confidence
    ]
    kept.sort(key=lambda d: (d.final_score or 0.0), reverse=True)

    written, skipped = await change_events_writer.persist_detections(
        kept, req.year_a, req.year_b,
    )

    return DetectChangesResponse(
        bbox=req.bbox, year_a=req.year_a, year_b=req.year_b,
        candidates_considered=len(candidates),
        detections_above_threshold=len(kept),
        detections=kept,
        persisted_rows=written,
        persistence_skipped=skipped,
    )
