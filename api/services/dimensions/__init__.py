"""Per-dimension scoring builders.

Each dimension lives in its own <100-LOC file under this package
(Rule 1 of CLAUDE.md). This __init__ re-exports every public symbol that
the previous monolithic api/services/_dimension_builders.py exposed, so
callers (api/services/scoring.py, tests/run_phase_15c_gate.py) keep
working through this import surface.

Adding a new dimension: create dimensions/<name>.py and add its public
builders to the re-export block below. Keep this __init__ a pure
re-export module — no business logic.
"""
from api.services.dimensions.bill_pain import bill_pain_dim
from api.services.dimensions.equity import equity_proxy_dim_from_parcel
from api.services.dimensions.income import _continuous_income_score, income_dim
from api.services.dimensions._ownership_classifier import (
    CORP_SHELL_PATTERN,
    determine_ownership_profile,
)
from api.services.dimensions.ownership import (
    ownership_dim,
    ownership_dim_from_parcel,
)
from api.services.dimensions.roof import roof_potential_dim

__all__ = [
    "bill_pain_dim",
    "equity_proxy_dim_from_parcel",
    "income_dim",
    "_continuous_income_score",
    "ownership_dim",
    "ownership_dim_from_parcel",
    "determine_ownership_profile",
    "CORP_SHELL_PATTERN",
    "roof_potential_dim",
]
