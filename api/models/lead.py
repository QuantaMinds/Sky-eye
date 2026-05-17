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
    """DEPRECATED — superseded by ParcelData in Phase 1.5c.

    Kept temporarily so existing scoring code that imports AssessorData
    keeps compiling. New code should use ParcelData.
    """

    owner_occupied: bool | None = None
    year_built: int | None = None


class ParcelData(BaseModel):
    """LA County Assessor parcel record resolved by ST_CONTAINS spatial lookup."""

    apn: str
    address_situs: str = ""
    city: str = ""
    zip: str = ""
    use_category: str = ""           # 'Residential' | 'Commercial' | ...
    use_subcategory: str = ""        # 'Single Family Residence' | etc.
    use_code: str = ""               # 4-digit LA County code
    is_residential: bool = False
    is_taxable: bool = False
    stream: str = "not_residential"  # 'private' | 'dac_sash' | 'not_residential'
    has_homeowners_exemption: bool = False
    homeowners_exemption_amount: float | None = None
    # Prop 13 tenure-start year (older of land/improvement base years).
    # In BigQuery this is 9999 when both base years are missing; the
    # parcel_lookup service maps 9999 -> None for truth-first behavior.
    arms_length_year: int | None = None
    recording_year: int | None = None
    year_built: int | None = None
    sqft_main: int | None = None
    total_value: float | None = None
    land_value: float | None = None
    improvement_value: float | None = None
    area_m2: float | None = None
    # "parcel" -> ST_CONTAINS resolved to exactly one AIN at this point.
    # "building" -> point falls inside a polygon shared by multiple AINs
    #   (condos, apartment-owned units, etc.). Returned AIN is one of the
    #   sibling units in the building, NOT necessarily the specific unit
    #   the caller's address pointed at. See
    #   feedback-multi-unit-ain-polygon-ambiguity for the consequences.
    resolution_confidence: str = "parcel"
    ains_at_point: int = 1


class UtilityInfo(BaseModel):
    """Electric utility serving a lat/lng — resolved via ST_CONTAINS against
    parcels_raw.utility_territories + joined to parcels_raw.utility_rates.
    See feedback-narrative-precision-must-match-data for confidence_level usage.
    """

    utility_name: str = "unknown"   # 'LADWP' | 'SCE' | 'unknown'
    representative_rate: float = 0.30      # $/kWh blended residential
    tariff_variant: str | None = None      # 'R-1A' | 'TOU-D-PRIME' | None
    nem_regime: str | None = None          # '1:1 retained' | 'NEM 3.0 (ACC export)' | None
    confidence_level: str = "fallback"     # 'precise' | 'approximate' | 'fallback'
    rate_source_note: str = ""


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
