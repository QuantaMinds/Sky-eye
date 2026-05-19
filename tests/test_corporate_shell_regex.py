"""Sanity test for CORP_SHELL_PATTERN — the corporate-shell purge regex.

Catches the substring-match bug we flagged before the user accepted the
prioritized hierarchy: tokens like "CO" or "INC" inside an unbounded `in`
operator would false-purge legitimate streets ("BACON ST", "LINCOLN BLVD",
"MOROCCO CT") and surnames ("VINCENT", "PRINCESS", "WINCHESTER"). The
\b word-boundary pattern fixes this — but only if the test suite proves it.

This test runs in two passes:
  1. Every corporate-pattern string MUST match the regex
  2. Every non-corporate string (person names, streets, family trusts)
     MUST NOT match

A single mis-classified non-corporate is a regression and fails the test.
"""
from __future__ import annotations

import pytest

from api.services.dimensions.ownership import CORP_SHELL_PATTERN

# True corporate / institutional patterns — MUST match
CORPORATE_NAMES = [
    "ACME PROPERTIES LLC",
    "WEST COAST INVESTMENTS L.L.C.",
    "PACIFIC HOLDINGS CORP",
    "GOLDEN STATE CORPORATION",
    "WIDGET INC",
    "ACME INCORPORATED",
    "SUNSET COMPANY",
    "SMITH & JONES PARTNERS",
    "MARINA PARTNERSHIP",
    "ACME LP",
    "GLOBAL L.P.",
    "WELLS FARGO BANK NA",
    "FIRST AMERICAN TRUST CO",
    "PACIFIC HOLDINGS",
    "OCEAN VIEW PROPERTIES",
    "BLUE WAVE REALTY",
    "WEST SIDE ASSOCIATES",
    "STARLIGHT VENTURES",
    "BLACKSTONE CAPITAL",
    "OPPORTUNITY FUND IV",
    "SUNSET GROUP",
    "GOLDEN ENTERPRISES",
    "URBAN MANAGEMENT",
    "MORTGAGE REMIC POOL 47",
    "AMERICAN REIT TRUST",
]

# Legitimate person names + situs strings containing risky substrings.
# Each entry is at least one substring-match landmine — the regex MUST NOT
# fire on any of these. If one does, the corporate-purge would silently
# eat a legitimate owner-occupant lead in production.
NON_CORPORATE_STRINGS = [
    "JOHN SMITH",
    "MARIA GARCIA",
    "VINCENT JIMENEZ",          # substring INC
    "PRINCESS DAVIS",           # substring INC
    "LINCOLN PARK FAMILY",      # substring INC, CO
    "WINCHESTER LN",            # substring INC
    "MOROCCO COURT",            # substring CO
    "BACON STREET",             # substring CO
    "EL CAMINO REAL DRIVE",     # substring CO
    "JOSEPH FALCO",             # substring CO inside FALCO
    "BIANCO DAVIS",             # substring CO inside BIANCO
    "RICHARD MARTINEZ",         # substring INC inside no-word-boundary
    "ELIZABETH WINSTON",        # substring INC
    "SMITH FAMILY TRUST",       # TRUST deliberately allowed (CA living trust)
    "JOHN DOE TRUST",           # TRUST allowed
    "MILLER FAMILY TRUST",      # CA Prop 13 owner-occupant pattern
    "DAVID HOLD",               # substring HOLD but no \bHOLDINGS\b
    "MARY BANKHEAD",            # substring BANK no word boundary
    "ROBERTS DEVELOPMENT DR",   # DEVELOPMENT removed from token list -> must NOT match
    "100 LINCOLN BLVD",
    "5191014012 BACON ST",      # AIN + situs combo
    "CAPITOL HEIGHTS",          # CAPITOL (with O) not CAPITAL — must not match
    "FUNDA SHARMA",             # substring FUND inside FUNDA
    "GROUPER LANE",             # substring GROUP inside GROUPER
    "PROPERTYS LANE",           # substring PROPERTY no word boundary at end
]


@pytest.mark.parametrize("name", CORPORATE_NAMES)
def test_corporate_patterns_match(name: str) -> None:
    """Every corporate name must trigger the purge."""
    m = CORP_SHELL_PATTERN.search(name)
    assert m is not None, f"corporate name slipped through: {name!r}"


@pytest.mark.parametrize("name", NON_CORPORATE_STRINGS)
def test_non_corporate_strings_do_not_match(name: str) -> None:
    """Every legitimate person/street name must NOT trigger the purge."""
    m = CORP_SHELL_PATTERN.search(name)
    assert m is None, (
        f"FALSE POSITIVE — substring bug: {name!r} matched token "
        f"{m.group(0)!r} at position {m.start()}. This would silently "
        f"purge a legitimate lead in production."
    )


def test_trust_not_in_corporate_list() -> None:
    """California family living trusts MUST NOT be purged — they are
    standard owner-occupant pattern under Prop 13, not corporate shells."""
    assert CORP_SHELL_PATTERN.search("SMITH FAMILY TRUST") is None
    assert CORP_SHELL_PATTERN.search("THE MILLER LIVING TRUST") is None
    # BUT "TRUST CO" / "TRUST COMPANY" remain corporate — verified by
    # the corporate test set (FIRST AMERICAN TRUST CO).


def test_case_insensitive() -> None:
    """Regex is IGNORECASE — lowercase corporate variants must match."""
    assert CORP_SHELL_PATTERN.search("acme llc") is not None
    assert CORP_SHELL_PATTERN.search("Acme Holdings") is not None
