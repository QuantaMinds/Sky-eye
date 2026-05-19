"""Equity-proxy dimension: CA Prop 13 tenure curve (1 - 0.95^tenure).

Continuous asymptotic shape — replaces stepped bands. Real market equity is
decoupled from assessed value under Prop 13; tenure is the cleanest free
proxy. See feedback-california-prop13-tenure.
"""
from __future__ import annotations

from datetime import datetime

from api.models.lead import DimensionValue, ParcelData
from api.services.dimensions._common import CAL, clip, resolve_arms_length_year


def equity_proxy_dim_from_parcel(parcel: ParcelData) -> DimensionValue:
    year, source_tag = resolve_arms_length_year(parcel)
    if year is None:
        return DimensionValue(
            value=None, source="unavailable",
            note="No base year, arms_length_year, or recording date in parcel record",
        )
    tenure = max(0, datetime.now().year - year)
    value = round(1.0 - (CAL.equity_decay ** tenure), 2)
    return DimensionValue(
        value=clip(value),
        source=f"LA County Assessor — {source_tag}, tenure={tenure}yr",
        note=(
            "Continuous asymptotic curve: 1 - 0.95^tenure. Replaces stepped bands "
            "for smoother gradient. CA Prop 13 reality: real market equity is "
            "decoupled from assessed value; tenure is the cleanest free proxy."
        ),
    )
