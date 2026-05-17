"""POST /api/v1/score-lead — end-to-end solar lead scoring."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException

from api.models.lead import ScoreRequest, ScoreResponse
from api.services import (
    census,
    geocoding,
    narrative,
    nrel,
    parcel_lookup,
    scoring,
    solar_api,
)

router = APIRouter(prefix="/api/v1", tags=["lead-score"])

_DATA_SOURCES = [
    "Google Maps Platform Geocoding API",
    "Google Maps Platform Solar API",
    "US Census ACS 5-year (2024 vintage)",
    "NREL PVWatts V8",
    "LA County Assessor (Rolls 2021-2024, BigQuery)",
    "Google Vertex AI (Gemini 2.5 Flash)",
]


@router.post("/score-lead", response_model=ScoreResponse)
async def score_lead(req: ScoreRequest) -> ScoreResponse:
    started = time.perf_counter()
    cached: dict[str, bool] = {}

    try:
        geo, cached["geocoding"] = await geocoding.geocode(req.address)
        # The four post-geocoding services have no inter-dependencies — fan out.
        # parcel_lookup may return (None, False) if the point is not in any LA
        # County parcel polygon (out of county, or a road/right-of-way gap).
        (roof, c_solar), (cens, c_cen), (pv, c_nrel), (parcel, c_parcel) = await asyncio.gather(
            solar_api.get_roof_data(geo.lat, geo.lng, req.address),
            census.get_block_group_data(geo.lat, geo.lng),
            nrel.get_production(geo.lat, geo.lng),
            parcel_lookup.lookup_by_point(geo.lat, geo.lng),
        )
        cached.update(solar=c_solar, census=c_cen, nrel=c_nrel, parcel=c_parcel)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    score, dims, weighting_mode, confidence = scoring.compute_score(
        roof, cens, pv, parcel
    )
    text, cached["narrative"] = await narrative.generate_narrative(
        geo.formatted_address, score, dims, confidence
    )

    return ScoreResponse(
        address=geo.formatted_address,
        lat=geo.lat,
        lng=geo.lng,
        score=score,
        score_confidence=confidence,
        weighting_mode=weighting_mode,
        dimensions=dims,
        narrative=text,
        data_sources=_DATA_SOURCES,
        cached=cached,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
