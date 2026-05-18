"""Region-specific calibration constants for the lead-scoring engine.

Single source of truth for every empirically-derived constant the dimension
builders read. Adding a new market (SF County, Orange County, Maricopa
County, etc.) is a one-file change: append a new `RegionCalibration`
instance to the `REGIONS` registry and run the calibration probes that
sourced each number.

Architecture rule (per feedback-no-national-defaults-for-constants):
every value below MUST trace back to a documented empirical probe on real
local data. No national rules-of-thumb, no "feels right" guesses. The
`notes` field captures provenance.

When adding a new region, the minimum probe set is:
  1. ROOF_KWH_FULL    — 15+ residential SFR Solar API calls; use the median
  2. INCOME_PEAK      — local financing/credit-utilization sweet spot
                        (not the Census median; the optimum band peak)
  3. INCOME_LOW_FLOOR — DAC-equivalent program eligibility floor for the
                        county, or the bottom 10th income percentile
  4. BILL_PAIN_FULL_USD — anchor representing "real bill pain" — usually
                          $3-4k/yr for a typical residential pre-solar bill
  5. LONG_TENURE_YEARS — usually 25 in CA Prop 13 jurisdictions; varies
                          elsewhere with local property-tax-reset rules
  6. EQUITY_DECAY     — tenure curve shape; 0.95 fits CA Prop 13 appreciation

Re-derive on data refresh: ACS releases (December), Solar API model
updates, utility rate restructuring. See project-phase15-backlog item
"Phase 1.5e follow-ups" for the annual recalibration cadence.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegionCalibration:
    """One region's calibration. All fields documented in module docstring."""

    name: str

    # Solar / roof normalization
    roof_kwh_full: float  # max_kwh_year value that maps to roof_potential = 1.0

    # Income curve (continuous: low-floor → quadratic rise → peak → linear decay → high-floor)
    income_low_floor: float    # below: flat 0.20 (DAC-SASH track)
    income_peak: float         # peaks at 1.00 here
    income_decay_range: float  # linear decay extends this many $ above peak
    income_high_floor: float   # asymptote for high-net-worth saturation

    # Bill-pain anchor
    bill_pain_full_usd: float  # annual bill that produces bill_pain = 1.0
    utility_rate_fallback: float  # $/kWh when utility resolution falls through

    # Ownership + equity (Prop 13 mechanics for CA; other states differ)
    long_tenure_years: int  # threshold for UNKNOWN_OR_TRUST bucket
    equity_decay: float     # tenure curve base: equity = 1 - decay^tenure

    # Provenance — for the YC narrative and re-derivation audit trail
    notes: str

    def income_score(self, income: float) -> tuple[float, str]:
        """Apply the continuous income curve for this region.

        Mirrors the canonical shape from `_dimension_builders` so future
        regions can override only the parameters without rewriting math.
        Returns (score, band_label).
        """
        if income < self.income_low_floor:
            return 0.20, "low-income / DAC-equivalent track"
        if income <= self.income_peak:
            ratio = (income - self.income_low_floor) / (self.income_peak - self.income_low_floor)
            score = 0.20 + (ratio ** 1.5) * 0.80
            return round(score, 2), "rising toward financing peak"
        distance = income - self.income_peak
        score = 1.00 - (distance / self.income_decay_range) * 0.35
        score = max(self.income_high_floor, score)
        return round(score, 2), "decaying toward saturation floor"


# ---------------------------------------------------------------------------
# REGION REGISTRY
# ---------------------------------------------------------------------------
# Add a new region by appending a RegionCalibration instance below. Every
# field requires a real empirical probe — do NOT copy LA values to a new
# region without re-running the calibration scripts on the new region's data.

LA_COUNTY = RegionCalibration(
    name="la_county",

    # Empirical: n=15 LB residential SFR Solar API probe 2026-05-17
    # min 8,739 / p25 20,190 / median 29,677 / p75 59,116 / max 445,473
    # 30,000 = LB median (anchored so roof_potential ~ 1.0 for typical
    # large unshaded SFR; ~0.3 for small/shaded; rare estates saturate).
    roof_kwh_full=30_000.0,

    # LA County FIPS 06037, ACS B19013_001E 5-year 2020-2024 = $90,112.
    # Financing peak at $130k (max federal solar credit utilization + clean
    # loan underwriting). Quadratic rise from $50k; linear decay to $300k+
    # saturation floor.
    income_low_floor=50_000.0,
    income_peak=130_000.0,
    income_decay_range=170_000.0,
    income_high_floor=0.65,

    # NREL PVWatts v8 typical 4 kW LA residential ~6,500 kWh/yr × $0.30/kWh
    # ≈ $1,950 annual bill. $3,000 = "high bill pain" anchor.
    bill_pain_full_usd=3_000.0,
    # Phase 1.5c flat fallback; tiered LADWP/SCE rates live in BQ
    # parcels_raw.utility_rates (Phase 1.5d). Used only when point falls
    # outside SCE/LADWP territories (small munis).
    utility_rate_fallback=0.30,

    # CA Prop 13: 25-year hold without exemption is the UNKNOWN_OR_TRUST
    # threshold (Belmont-Shore pattern: inherited/trust ownership).
    long_tenure_years=25,
    # 0.95^tenure: 1-0.95^50 ≈ 0.92 (50yr saturation); 1-0.95^20 ≈ 0.64;
    # 1-0.95^5 ≈ 0.23. Calibrated to CA Prop 13 compounding appreciation.
    equity_decay=0.95,

    notes=(
        "Calibrated 2026-05-17 against:\n"
        " - LA Assessor 2020-2024 rolls (~2.4M residential parcels)\n"
        " - Solar API probe (n=15 LB residential SFRs)\n"
        " - Census ACS 2020-2024 B19013_001E (LA County median $90,112)\n"
        " - LADWP R-1A + SCE TOU-D-PRIME tariff schedules\n"
        " - OEHHA SB-535 DAC tract definitions (Tribal update 2023/2024)\n"
        "See memory: feedback-no-national-defaults-for-constants and the\n"
        "Phase 1.5e commit message (5951f73) for full derivation trail."
    ),
)


# Registry — ordering doesn't matter; lookup by name.
REGIONS: dict[str, RegionCalibration] = {
    LA_COUNTY.name: LA_COUNTY,
    # 'sf_county':       <add when SF data has been probed>
    # 'orange_county':   <add when Orange County data has been probed>
    # 'maricopa_county': <add when AZ Phoenix-area data has been probed>
}

# Default for single-region operation. When multi-region runtime support is
# needed, plumb a `region` parameter through compute_score and the dimension
# builders; for now every consumer uses this constant.
DEFAULT_REGION = "la_county"


def get_calibration(region: str = DEFAULT_REGION) -> RegionCalibration:
    """Look up calibration constants for `region`. Raises KeyError if the
    region hasn't been added to the registry."""
    if region not in REGIONS:
        raise KeyError(
            f"Region {region!r} not in registry. Known: {sorted(REGIONS)}. "
            f"Add a new RegionCalibration to api/services/region_calibration.py "
            f"with real empirical probes per its module docstring."
        )
    return REGIONS[region]
