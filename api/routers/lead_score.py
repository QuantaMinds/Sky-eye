"""POST /api/v1/score-lead — end-to-end solar lead scoring."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException

from api.models.lead import ScoreRequest, ScoreResponse
from api.services import (
    census,
    dac,
    geocoding,
    narrative,
    nrel,
    parcel_lookup,
    scoring,
    solar_api,
    utility,
)

router = APIRouter(prefix="/api/v1", tags=["lead-score"])

_DATA_SOURCES = [
    "Google Maps Platform Geocoding API",
    "Google Maps Platform Solar API",
    "US Census ACS 5-year (2024 vintage)",
    "NREL PVWatts V8",
    "LA County Assessor (Rolls 2021-2024, BigQuery)",
    "CPUC Electric IOU Territory + LA County DRP city boundaries (utility)",
    "OEHHA SB-535 Disadvantaged Communities (Tribal update 2023/2024)",
    "Google Vertex AI (Gemini 2.5 Flash)",
]


@router.post("/score-lead", response_model=ScoreResponse)
async def score_lead(req: ScoreRequest) -> ScoreResponse:
    started = time.perf_counter()
    cached: dict[str, bool] = {}

    try:
        geo, cached["geocoding"] = await geocoding.geocode(req.address)
        # Six post-geocoding services, all independent — fan out in parallel.
        # parcel_lookup returns (None, False) if outside LA County parcel layer.
        # utility.lookup_by_point always returns a UtilityInfo (falls back to
        # 'unknown' row when outside SCE/LADWP territories).
        # dac.lookup_by_point returns is_dac=False for ~53% of LA County
        # (non-DAC tracts); is_dac=True triggers DAC-SASH stream routing.
        (
            (roof, c_solar), (cens, c_cen), (pv, c_nrel),
            (parcel, c_parcel), (util, c_util), (dac_info, c_dac),
        ) = await asyncio.gather(
            solar_api.get_roof_data(geo.lat, geo.lng, req.address),
            census.get_block_group_data(geo.lat, geo.lng),
            nrel.get_production(geo.lat, geo.lng),
            parcel_lookup.lookup_by_point(geo.lat, geo.lng),
            utility.lookup_by_point(geo.lat, geo.lng),
            dac.lookup_by_point(geo.lat, geo.lng),
        )
        cached.update(
            solar=c_solar, census=c_cen, nrel=c_nrel,
            parcel=c_parcel, utility=c_util, dac=c_dac,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    score, dims, weighting_mode, confidence = scoring.compute_score(
        roof, cens, pv, parcel, util, dac_info,
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
        stream=parcel.stream if parcel else None,
        is_dac=dac_info.is_dac if dac_info else None,
        ces_percentile=dac_info.ces_percentile if dac_info else None,
        dimensions=dims,
        narrative=text,
        data_sources=_DATA_SOURCES,
        cached=cached,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
