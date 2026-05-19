"""Canonical list of external data sources cited in API responses + PDF footers.

Single source of truth: when a new external service is added to the
pipeline (or an existing one moves vintage), update this list and both
the /score-lead JSON response and the PDF attribution footer pick it up.

Prior state (Phase 3): two separate hard-coded lists in
api/routers/lead_score.py and api/services/report_data.py. The PDF
footer omitted Geocoding API, utility territories, DAC tracts, and
Vertex AI — non-obvious data-attribution drift. Found via Phase 3
forensic audit §3.4.
"""
from __future__ import annotations

# Order: each line is one external system; the trailing parenthesis
# carries vintage / table identifier where it materially affects audits.
DATA_SOURCES: tuple[str, ...] = (
    "Google Maps Platform Geocoding API",
    "Google Maps Platform Solar API",
    "US Census ACS 5-year (2024 vintage)",
    "NREL PVWatts V8",
    "LA County Assessor (Rolls 2021-2024, BigQuery)",
    "CPUC Electric IOU Territory + LA County DRP city boundaries (utility)",
    "OEHHA SB-535 Disadvantaged Communities (Tribal update 2023/2024)",
    "Google Vertex AI (Gemini 2.5 Flash)",
)
