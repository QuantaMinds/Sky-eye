"""Phase 1.5a — 10 tests covering services, truth-first scoring, narrative honesty,
full pipeline, and cache. Live tests skip when credentials are missing.

This file is intentionally one cohesive module (the Phase 1 gate) per CLAUDE.md.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from api import cache  # noqa: E402
from api.models.lead import (  # noqa: E402
    AssessorData,
    CensusData,
    DimensionValue,
    NRELData,
    ScoreDimensions,
    SolarRoofData,
)
from api.services import (  # noqa: E402
    census,
    geocoding,
    narrative,
    nrel,
    scoring,
    solar_api,
)


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "_DB_PATH", tmp_path / "test_cache.db")


def _have(*keys: str) -> bool:
    return all(bool(os.environ.get(k)) for k in keys)


def _all_dims_unavailable() -> ScoreDimensions:
    u = DimensionValue(value=None, source="unavailable")
    return ScoreDimensions(
        roof_potential=u, income_qualification=u, ownership=u, bill_pain=u,
        equity_proxy=u, no_existing_solar=u, intent_signal=u,
    )


# --- 1. Geocoding ----------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not _have("GOOGLE_SOLAR_API_KEY"), reason="needs Google API key")
async def test_geocoding_returns_lat_lng() -> None:
    result, _ = await geocoding.geocode("1 Apple Park Way, Cupertino, CA")
    assert -90 <= result.lat <= 90 and -180 <= result.lng <= 180
    assert "Cupertino" in result.formatted_address or "Apple" in result.formatted_address


# --- 2. Solar API ----------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not _have("GOOGLE_SOLAR_API_KEY"), reason="needs Google API key")
async def test_solar_api_returns_roof_data() -> None:
    data, _ = await solar_api.get_roof_data(37.3318, -122.0312, "Apple HQ")
    if data.max_kwh_year is not None:
        assert data.max_kwh_year > 0
    # Truth-first: has_existing_solar is unknown, NOT a fake False.
    assert data.has_existing_solar is None


# --- 3. Census -------------------------------------------------------------

@pytest.mark.asyncio
async def test_census_returns_income() -> None:
    data, _ = await census.get_block_group_data(34.0522, -118.2437)
    assert len(data.block_group_geoid) >= 12
    if data.median_household_income is not None:
        assert data.median_household_income > 0


# --- 4. NREL ---------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not _have("NREL_API_KEY"), reason="needs NREL key")
async def test_nrel_returns_production() -> None:
    data, _ = await nrel.get_production(34.0522, -118.2437, system_kw=4.0)
    assert data.ac_annual_kwh is not None and data.ac_annual_kwh > 4000


# --- 5. Scoring math (with full real signals) ------------------------------

def test_scoring_computes_correctly() -> None:
    """Truth-first NON-renormalized math: missing dims must depress the headline."""
    roof = SolarRoofData(max_array_panels=20, max_kwh_year=15_000, has_existing_solar=None)
    cens = CensusData(median_household_income=120_000, block_group_geoid="060371234001")
    pv = NRELData(ac_annual_kwh=10_000)
    parcel = AssessorData(owner_occupied=True)  # synthetic real signal for this test
    score, dims, mode, conf = scoring.compute_score(roof, cens, pv, parcel)
    # Available: roof(1.0,w=0.25) income(1.0,w=0.20) own(1.0,w=0.15) bill(1.0,w=0.15)
    # equity / no_existing_solar / intent are unavailable -> contribute 0.
    # NON-renormalized headline = 0.25 + 0.20 + 0.15 + 0.15 = 0.75
    assert abs(score - 0.75) < 1e-9
    assert abs(conf - 0.75) < 1e-9
    assert mode == "available_signals_only"
    assert dims.roof_potential.value == 1.0
    assert dims.equity_proxy.value is None
    assert dims.equity_proxy.source == "unavailable"


# --- 6. Narrative uses Gemini 2.5 Flash ------------------------------------

@pytest.mark.asyncio
async def test_narrative_uses_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return "This lead has strong roof potential and..."

    monkeypatch.setattr(narrative, "_call_gemini", fake_call)
    dims = _all_dims_unavailable()
    dims.roof_potential = DimensionValue(value=0.8, source="Google Solar API")
    text, was_cached = await narrative.generate_narrative("123 Main St", 0.8, dims, 0.25)
    assert text.startswith("This lead has strong")
    assert was_cached is False
    assert narrative._MODEL_NAME == "gemini-2.5-flash"
    assert "123 Main St" in captured["prompt"]
    assert "0.80" in captured["prompt"]
    # The prompt MUST explicitly tell Gemini not to fabricate.
    assert "NEVER" in captured["prompt"]
    assert "UNAVAILABLE" in captured["prompt"]


# --- 7. Full pipeline integration ------------------------------------------

@pytest.mark.skipif(
    not _have("GOOGLE_SOLAR_API_KEY", "NREL_API_KEY", "GOOGLE_CLOUD_PROJECT"),
    reason="needs Google + NREL keys + GCP project for Vertex",
)
def test_full_pipeline_integration() -> None:
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/score-lead",
            json={"address": "100 Long Beach Blvd, Long Beach, CA"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert 0.0 <= body["score"] <= 1.0
    assert 0.0 <= body["score_confidence"] <= 1.0
    assert body["weighting_mode"] in {
        "all_signals_available", "available_signals_only", "no_signals",
    }
    # Each dimension is the new {value, source, note} shape.
    for name in (
        "roof_potential", "income_qualification", "ownership", "bill_pain",
        "equity_proxy", "no_existing_solar", "intent_signal",
    ):
        dim = body["dimensions"][name]
        assert "value" in dim and "source" in dim
        if dim["value"] is not None:
            assert 0.0 <= dim["value"] <= 1.0
    assert len(body["narrative"]) > 50


# --- 8. Cache prevents duplicate calls -------------------------------------

@pytest.mark.asyncio
async def test_cache_prevents_duplicate_calls() -> None:
    cache.set("geocode:123 main st", {"lat": 1.5, "lng": 2.5, "formatted_address": "Seeded"})
    result, was_cached = await geocoding.geocode("123 Main St")
    assert was_cached is True and result.lat == 1.5


# --- 9. NO renormalization when dims are null (truth-first depression) ----

def test_score_does_NOT_renormalize_when_dims_null() -> None:
    """Headline score MUST visibly drop when dims are missing — no rescue-divide.

    A property where we only know roof_potential=0.5 (weight 0.25) and nothing
    else cannot exceed 0.125 on the headline. Confidence reports the gap.
    """
    roof = SolarRoofData(max_array_panels=10, max_kwh_year=7_500, has_existing_solar=None)
    cens = CensusData(median_household_income=None, block_group_geoid="x")
    pv = NRELData(ac_annual_kwh=None)
    parcel = AssessorData(owner_occupied=None)
    score, dims, mode, conf = scoring.compute_score(roof, cens, pv, parcel)
    # weighted_sum = 0.5 * 0.25 = 0.125 ; non-renormalized -> score = 0.125
    assert abs(score - 0.125) < 1e-9
    assert abs(conf - 0.25) < 1e-9
    assert mode == "available_signals_only"
    assert dims.income_qualification.value is None
    assert dims.ownership.value is None


# --- 10. Fabrication-resistance — narrative must NOT claim unknowns -------

@pytest.mark.asyncio
async def test_narrative_prompt_blocks_fabrication(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ownership is unavailable, the prompt must instruct Gemini not to claim it."""
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        narrative, "_call_gemini",
        lambda p: captured.setdefault("prompt", p) or "narrative text",
    )
    dims = _all_dims_unavailable()
    dims.roof_potential = DimensionValue(value=0.9, source="Google Solar API")
    await narrative.generate_narrative("Test Address", 0.9, dims, 0.25)
    prompt = captured["prompt"]
    # All four mocked-in-Phase-1 dimensions must be in the UNAVAILABLE section.
    for name in ("ownership", "equity_proxy", "no_existing_solar", "intent_signal"):
        assert f"{name:<22}  UNAVAILABLE" in prompt, f"{name} not flagged unavailable"
    # The explicit anti-fabrication rule must be present.
    assert "NEVER claim the resident is an owner" in prompt
