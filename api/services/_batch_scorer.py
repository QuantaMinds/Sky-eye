"""Single-address scoring helper used by batch_processor.

Mirrors the pipeline in api/routers/lead_score.py and returns a flat dict
shaped for leadlens.batch_results. Kept as a private module so batch_processor
stays under the 100-LOC rule.

Truth-first (CLAUDE.md Rule 3): every dim value/source/note is preserved.
None is preserved as None — never substituted with a constant.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

from api.services import (
    census,
    dac,
    geocoding,
    nrel,
    parcel_lookup,
    scoring,
    solar_api,
    utility,
)
# NOTE: narrative is INTENTIONALLY not imported here. Vertex AI text
# generation takes 1.5-4s per call. At 500 leads that adds 12-33 minutes
# of single-worker latency, freezing the batch path. Narratives are
# generated lazily by POST /api/v1/score-lead when an installer drills
# into a specific row. See feedback-no-narrative-in-batch.

_DIM_NAMES = (
    "roof_potential", "income_qualification", "ownership", "bill_pain",
    "equity_proxy", "no_existing_solar", "intent_signal",
)
# leadlens.batch_results column prefix mapping (income_qualification -> income_qualified).
_DIM_TO_COL = {
    "roof_potential": "roof_potential",
    "income_qualification": "income_qualified",
    "ownership": "ownership",
    "bill_pain": "bill_pain",
    "equity_proxy": "equity_strength",
    "no_existing_solar": "no_existing_solar",
    "intent_signal": "intent_signal",
}


def _now_iso() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


async def score_one_address(job_id: str, index: int, address: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "job_id": job_id,
        "result_index": index,
        "input_address": address,
        "scored_at": _now_iso(),
    }
    try:
        geo, _ = await geocoding.geocode(address)
    except Exception as exc:
        msg = str(exc) or repr(exc)
        return {**base, "scored_status": "api_failure", "error_message": msg[:500]}

    base["geocoded_lat"] = geo.lat
    base["geocoded_lng"] = geo.lng

    (roof, _), (cens, _), (pv, _), (parcel, _), (util, _), (dac_info, _) = (
        await asyncio.gather(
            solar_api.get_roof_data(geo.lat, geo.lng, address),
            census.get_block_group_data(geo.lat, geo.lng),
            nrel.get_production(geo.lat, geo.lng),
            parcel_lookup.lookup_by_point(geo.lat, geo.lng),
            utility.lookup_by_point(geo.lat, geo.lng),
            dac.lookup_by_point(geo.lat, geo.lng),
        )
    )

    # Multi-unit building: the spatial lookup returned a polygon shared by
    # multiple AINs (condo siblings). Per C-46 residential-rooftop scope,
    # individual units have no unit-level roof ownership signal, so the
    # priority_score would be the same for every sibling and stack the
    # top decile. Surface the row honestly instead of ranking it. The
    # Phase 2.0.1 follow-up will also catch units > 1 on a single AIN
    # (single-AIN apartment buildings) once `units` lands in the projection.
    if parcel is not None and parcel.resolution_confidence == "building":
        return {
            **base,
            "scored_status": "multi_unit_skipped",
            "resolved_ain": parcel.apn,
            "resolution_confidence": parcel.resolution_confidence,
            "stream": parcel.stream,
            "error_message": (
                f"Multi-unit building detected ({parcel.ains_at_point} AINs share "
                f"this polygon). Per C-46 residential-rooftop scope, individual "
                f"units cannot be scored without unit-level roof ownership data. "
                f"Excluded from ranking."
            ),
        }

    score, dims, _, _ = scoring.compute_score(roof, cens, pv, parcel, util, dac_info)

    out: dict[str, Any] = {
        **base,
        "scored_status": "scored",
        "priority_score": score,
        "stream": parcel.stream if parcel else None,
        "resolved_ain": parcel.apn if parcel else None,
        "resolution_confidence": parcel.resolution_confidence if parcel else "unresolved",
        # Narrative is intentionally NULL in batch — lazy-loaded via
        # POST /api/v1/score-lead/{apn}/narrative when the user drills in.
        "gemini_narrative": None,
    }
    for dim_name in _DIM_NAMES:
        dv = getattr(dims, dim_name)
        col = _DIM_TO_COL[dim_name]
        out[col] = dv.value
        # Phase-2-deferred dims map to ..._status (always 'unavailable').
        # Live dims map to ..._source + ..._confidence per the DDL.
        if dim_name in ("no_existing_solar", "intent_signal"):
            out[f"{col}_status"] = "unavailable"
        else:
            out[f"{col}_source"] = dv.source
            out[f"{col}_confidence"] = (
                "precise" if dv.value is not None else "unavailable"
            )
    if parcel is not None:
        out["has_homeowners_exemption"] = parcel.has_homeowners_exemption
        out["total_value"] = parcel.total_value
        out["sqft_main"] = parcel.sqft_main
        out["year_built"] = parcel.year_built
    return out
