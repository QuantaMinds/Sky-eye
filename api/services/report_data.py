"""Assemble the view dict that pdf_generator consumes.

Inputs: one batch_results row + live (cache-backed) roof/nrel/utility
fetches. The mapper is pure — the only I/O is in fetch_for_apn().

Truth-first (CLAUDE.md Rule 3): missing inputs propagate as None into
the view, NOT as 0 / "" / midpoint constants. The template renders
None as the literal word "Unavailable".
"""
from __future__ import annotations

from typing import Any

from api.data_sources import DATA_SOURCES
from api.services import bigquery_writer, nrel, solar_api, utility

_DIMS = (
    ("roof_potential",       "Roof potential",       "roof_potential"),
    ("income_qualification", "Income qualification", "income_qualified"),
    ("ownership",            "Ownership",            "ownership"),
    ("bill_pain",            "Bill pain",            "bill_pain"),
    ("equity_proxy",         "Equity proxy",         "equity_strength"),
    ("no_existing_solar",    "No existing solar",    "no_existing_solar"),
    ("intent_signal",        "Intent signal",        "intent_signal"),
)


def _estimated_savings(kwh_year: float | None, rate: float | None) -> float | None:
    if kwh_year is None or rate is None:
        return None
    return float(kwh_year) * float(rate)


def _truthful_rate(utility_data) -> float | None:
    """Return the utility rate ONLY if it was measured, else None.

    utility.lookup_by_point falls back to the 'unknown' row with
    representative_rate=0.30 and confidence_level='fallback' for any
    point outside SCE/LADWP territory. Propagating that 0.30 into
    savings = kWh × rate produces a fabricated dollar figure for every
    out-of-territory lead (Phase 3 forensic finding 2.5). Truth-first:
    if it's a fallback, we don't know the rate.
    """
    if utility_data is None:
        return None
    if getattr(utility_data, "confidence_level", None) == "fallback":
        return None
    rate = getattr(utility_data, "representative_rate", None)
    return float(rate) if rate is not None else None


def _opt_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_bool(v) -> bool | None:
    """Three-valued: True / False / None. NEVER coerce missing to False."""
    if v is None:
        return None
    return bool(v)


def build_view(
    row: dict[str, Any],
    roof_data,
    nrel_data,
    utility_data,
) -> dict[str, Any]:
    """Pure mapper — no I/O. roof_data may be None (Solar API miss).

    Rule 3: every nullable field propagates None into the view. Callers
    (the template) MUST render None as 'Unavailable', never as a
    substitute constant. See [[feedback-forensic-pass-on-green-tests]].
    """
    dims = []
    for key, label, col in _DIMS:
        dims.append({
            "key": key,
            "label": label,
            "value": row.get(col),
            "source": (row.get(f"{col}_source") or row.get(f"{col}_status") or "unavailable"),
        })
    rate = _truthful_rate(utility_data)
    kwh = roof_data.max_kwh_year if roof_data is not None else None
    return {
        "apn": row.get("resolved_ain"),
        "address": row.get("input_address"),  # None propagates
        "lat": row.get("geocoded_lat"),
        "lng": row.get("geocoded_lng"),
        "priority_score": _opt_float(row.get("priority_score")),  # None propagates
        # batch_results does NOT store score_confidence yet; the value
        # is genuinely unavailable until the schema persists it.
        "score_confidence": _opt_float(row.get("score_confidence")),
        "stream": row.get("stream"),
        "year_built": row.get("year_built"),
        "sqft_main": row.get("sqft_main"),
        "total_value": row.get("total_value"),
        "has_homeowners_exemption": _opt_bool(row.get("has_homeowners_exemption")),
        "dimensions": dims,
        "roof": {
            "max_array_panels": getattr(roof_data, "max_array_panels", None),
            "max_kwh_year": kwh,
            "max_sunshine_hours": getattr(roof_data, "max_sunshine_hours", None),
        },
        "nrel": {
            "ac_annual_kwh": getattr(nrel_data, "ac_annual_kwh", None),
            "capacity_factor": getattr(nrel_data, "capacity_factor", None),
        },
        "financial": {
            "estimated_annual_savings_usd": _estimated_savings(kwh, rate),
            "rate_per_kwh_usd": rate,
            "simple_payback_years": None,  # no cost model in Phase 3
        },
        "narrative": row.get("gemini_narrative"),
        "data_sources": list(DATA_SOURCES),
        "map_data_uri": None,
    }


async def fetch_for_apn(apn: str) -> dict[str, Any] | None:
    """Build a view by looking up the row in BQ and refreshing roof/utility.

    Returns None if the APN has never been scored.
    """
    row = await bigquery_writer.lookup_latest_by_apn(apn)
    if row is None:
        return None
    lat = row.get("geocoded_lat")
    lng = row.get("geocoded_lng")
    # Empty string here is for the Solar API key only — not a fabrication
    # of the user-visible address (that one preserves None into the view).
    address = row.get("input_address") or ""
    if lat is None or lng is None:
        return build_view(row, None, None, None)
    (roof_data, _), (nrel_data, _), (util_data, _) = (
        await solar_api.get_roof_data(lat, lng, address),
        await nrel.get_production(lat, lng),
        await utility.lookup_by_point(lat, lng),
    )
    return build_view(row, roof_data, nrel_data, util_data)
