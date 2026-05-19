"""POST /api/v1/score-lead/{apn}/narrative — lazy narrative for an already-scored AIN.

Why a separate endpoint (vs reusing POST /api/v1/score-lead):
  - /score-lead takes an address and runs the whole pipeline. This route
    takes an APN that has ALREADY been scored (in batch_results or
    score_cache) and only invokes Vertex AI.
  - Frontend detail page: render score row instantly from BQ, then fire
    this endpoint async, swap narrative in when ready (~2-3s).
  - Narrative-on-demand keeps bulk Vertex spend near zero — installers
    only burn tokens on the ~5-10% of leads they actually drill into.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.models.lead import DimensionValue, ScoreDimensions
from api.services import bigquery_writer, narrative as narrative_svc

router = APIRouter(prefix="/api/v1", tags=["narrative"])


class NarrativeResponse(BaseModel):
    apn: str
    narrative: str
    cached: bool


_DIM_COLS = (
    ("roof_potential", "roof_potential"),
    ("income_qualification", "income_qualified"),
    ("ownership", "ownership"),
    ("bill_pain", "bill_pain"),
    ("equity_proxy", "equity_strength"),
    ("no_existing_solar", "no_existing_solar"),
    ("intent_signal", "intent_signal"),
)


def _row_to_dims(row: dict) -> ScoreDimensions:
    kwargs: dict[str, DimensionValue] = {}
    for model_name, col in _DIM_COLS:
        kwargs[model_name] = DimensionValue(
            value=row.get(col),
            source=row.get(f"{col}_source") or "unavailable",
        )
    return ScoreDimensions(**kwargs)


@router.post("/score-lead/{apn}/narrative", response_model=NarrativeResponse)
async def generate_for_apn(apn: str) -> NarrativeResponse:
    row = await bigquery_writer.lookup_latest_by_apn(apn)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"AIN {apn} has not been scored — submit it via /score-lead or /batch-score first",
        )
    existing = row.get("gemini_narrative")
    if existing:
        return NarrativeResponse(apn=apn, narrative=existing, cached=True)

    address = row.get("input_address") or ""
    score = float(row.get("priority_score") or 0.0)
    dims = _row_to_dims(row)
    text, _ = await narrative_svc.generate_narrative(address, score, dims, 1.0)
    await bigquery_writer.write_narrative_back(apn, text)
    return NarrativeResponse(apn=apn, narrative=text, cached=False)
