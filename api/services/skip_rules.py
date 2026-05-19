"""Shared skip-rules for parcel scoring paths.

The multi-unit skip lives here so every scoring path (single-call router,
batch scorer, future paths) imports the same rule. Duplicated business
logic across paths is how Tony's pilot CSV got contaminated on 2026-05-19:
the rule was fixed in _batch_scorer but the single-call router and the
pilot script kept letting apartments through. See
[[audit-all-code-paths-for-rule-fixes]].

Callers build their own response shape — single-call raises HTTPException,
batch returns a dict. This module returns only the cause description.

NULL units is treated as 1 here (no skip). The NULL-units-with-non-SFR-
use_code case (Defect 3 from the 2026-05-19 investigation) is a separate
followup with its own behavior change and test coverage — intentionally
not handled in this refactor.
"""
from __future__ import annotations

from api.models.lead import ParcelData


def multi_unit_cause(parcel: ParcelData) -> str | None:
    """Return a description of the multi-unit signal if skip should fire, else None.

    Two distinct signals, either fires:
      (a) resolution_confidence == "building" — point falls inside a polygon
          shared by multiple AINs (condo siblings).
      (b) units > 1 — a single AIN represents a multi-unit building
          (apartment / multiplex / triplex).
    """
    if parcel.resolution_confidence == "building":
        return f"{parcel.ains_at_point} AINs share this polygon (condo siblings)"
    units = parcel.units if parcel.units is not None else 1
    if units > 1:
        return f"{units} units on a single AIN (apartment / multiplex)"
    return None
