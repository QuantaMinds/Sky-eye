"""Pydantic models for /api/v1/score-lead.

Truth-first contract: every dimension is a ``DimensionValue`` carrying its
own source. ``value is None`` means "we don't know" — never a substitute
constant (see CLAUDE.md Rule 3).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    address: str = Field(min_length=5, max_length=500)


class GeocodingResult(BaseModel):
    lat: float
    lng: float
    formatted_address: str


class SolarRoofData(BaseModel):
    max_array_panels: int | None = None
    max_kwh_year: float | None = None
    max_sunshine_hours: float | None = None
    # Public Solar API does not expose detected-arrays — always unknown in Phase 1.
    has_existing_solar: bool | None = None
    building_name: str = ""


class CensusData(BaseModel):
    median_household_income: float | None = None
    block_group_geoid: str = ""


class NRELData(BaseModel):
    ac_annual_kwh: float | None = None
    capacity_factor: float | None = None
    solar_radiation: float | None = None


class AssessorData(BaseModel):
    # Phase 1: always None (real LA Assessor integration deferred to Phase 1.5c).
    owner_occupied: bool | None = None
    year_built: int | None = None


class DimensionValue(BaseModel):
    """One dimension's contribution. value=None means data is unavailable."""

    value: float | None = Field(default=None, ge=0, le=1)
    source: str
    note: str | None = None


class ScoreDimensions(BaseModel):
    roof_potential: DimensionValue
    income_qualification: DimensionValue
    ownership: DimensionValue
    bill_pain: DimensionValue
    equity_proxy: DimensionValue
    no_existing_solar: DimensionValue
    intent_signal: DimensionValue


class ScoreResponse(BaseModel):
    address: str
    lat: float
    lng: float
    score: float = Field(ge=0, le=1)
    # Fraction of weights backed by real data — 1.0 only if every dim is available.
    score_confidence: float = Field(ge=0, le=1)
    weighting_mode: str  # "all_signals_available" | "available_signals_only" | "no_signals"
    dimensions: ScoreDimensions
    narrative: str
    data_sources: list[str]
    cached: dict[str, bool]
    latency_ms: int
