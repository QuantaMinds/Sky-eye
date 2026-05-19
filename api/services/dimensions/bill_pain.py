"""Bill-pain dimension: annual production (kWh) × utility rate ($/kWh)
normalized to the region's BILL_PAIN_FULL_USD anchor. Pulls real LADWP/SCE
tariffs when utility resolution succeeds; falls back to a flat default rate
when the point falls outside known utility territories.
"""
from __future__ import annotations

from api.models.lead import DimensionValue, NRELData, UtilityInfo
from api.services.dimensions._common import CAL, clip


def bill_pain_dim(nrel: NRELData, utility: UtilityInfo | None = None) -> DimensionValue:
    if not nrel.ac_annual_kwh:
        return DimensionValue(
            value=None, source="NREL PVWatts v8",
            note="No production estimate returned",
        )
    if utility is None:
        utility = UtilityInfo()  # all defaults; rate=0.30, confidence=fallback
    annual_bill = nrel.ac_annual_kwh * utility.representative_rate
    return DimensionValue(
        value=clip(annual_bill / CAL.bill_pain_full_usd),
        source=(
            f"NREL PVWatts v8 (4 kW system) x {utility.utility_name} "
            f"~${utility.representative_rate:.2f}/kWh"
            + (f" ({utility.tariff_variant})" if utility.tariff_variant else "")
            + f" = approximately ${annual_bill:,.0f}/yr proxy"
        ),
        note=(
            f"confidence={utility.confidence_level}; "
            + (f"NEM regime: {utility.nem_regime}. " if utility.nem_regime else "")
            + (utility.rate_source_note[:160] if utility.rate_source_note else "")
        ),
    )
