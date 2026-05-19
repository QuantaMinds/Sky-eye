"""Roof-potential dimension: max_kwh_year normalized to the region's
ROOF_KWH_FULL anchor. Built on the Google Solar API's max-array output.
"""
from __future__ import annotations

from api.models.lead import DimensionValue, SolarRoofData
from api.services.dimensions._common import CAL, clip


def roof_potential_dim(roof: SolarRoofData) -> DimensionValue:
    if not roof.max_kwh_year:
        return DimensionValue(
            value=None, source="Google Solar API",
            note="No roof data returned for this building",
        )
    return DimensionValue(
        value=clip(roof.max_kwh_year / CAL.roof_kwh_full),
        source=f"Google Solar API (anchor: {int(CAL.roof_kwh_full)} kWh/yr = 1.0)",
    )
