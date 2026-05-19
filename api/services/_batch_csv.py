"""CSV serialization for the batch-export endpoint.

Pure helper — no I/O, no async, no FastAPI. Takes a list of result rows
(the same shape stored in batch_processor._RESULTS) and returns the CSV
string a caller can stream back to the client.

CLAUDE.md Rule 3 (truth-first): `None` cells render as the empty string,
NEVER as 0 / 0.0 / "unknown" / "N/A". Downstream Excel users distinguish
"unscored" from "scored zero" by the blank cell; substituting a constant
silently breaks that.

CLAUDE.md Rule 1: one cohesive module — CSV row mapping + ordering.
"""
from __future__ import annotations

import csv
import io
from typing import Any

# Column order is the customer-facing contract. Frontend tests assert on
# this header row; reordering breaks Excel templates installers have built.
# Header label -> source key in the row dict (None == not yet persisted).
_COLUMNS: tuple[tuple[str, str | None], ...] = (
    ("address", "input_address"),
    ("apn", "resolved_ain"),
    ("lat", "geocoded_lat"),
    ("lng", "geocoded_lng"),
    ("score", "priority_score"),
    ("stream", "stream"),
    ("roof_potential", "roof_potential"),
    ("income_qualification", "income_qualified"),
    ("ownership", "ownership"),
    ("bill_pain", "bill_pain"),
    ("equity_proxy", "equity_strength"),
    ("utility", "bill_pain_utility"),
    ("year_built", "year_built"),
    ("sqft", "sqft_main"),
    # has_homeowners_exemption is the strongest owner-occupied signal we
    # persist today (LA Assessor flag — requires the address to be the
    # owner's primary residence). When the flag is None, the cell stays
    # blank — never substituted with False / 0.
    ("owner_occupied_signal", "has_homeowners_exemption"),
    ("narrative", "gemini_narrative"),
)


def _cell(value: Any) -> str:
    """Render one cell. None -> empty; bools -> 'true'/'false'; else str()."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_csv(results: list[dict[str, Any]]) -> str:
    """Serialize scored rows to CSV, sorted by priority_score desc.

    Only rows with scored_status == 'scored' AND a non-null priority_score
    appear — the same filter the frontend results table uses, so the CSV
    and the UI agree on what counts as a ranked lead. Skipped / failed
    rows surface in the status payload's reasons breakdown, not here.

    Ties on priority_score keep input order (Python sort is stable).
    """
    scored = [
        r for r in results
        if r.get("scored_status") == "scored" and r.get("priority_score") is not None
    ]
    scored.sort(key=lambda r: r["priority_score"], reverse=True)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([label for label, _ in _COLUMNS])
    for row in scored:
        writer.writerow([_cell(row.get(key)) if key else "" for _, key in _COLUMNS])
    return buf.getvalue()
