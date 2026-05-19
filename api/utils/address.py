"""Address string normalization for situs-vs-mailing equality checks.

Standardizes casing, strips structural punctuation, collapses internal
whitespace, and normalizes common street-suffix variants (AVENUE/AVE -> AV,
STREET -> ST, BOULEVARD/BLD -> BLVD, etc.) so the ownership classifier can
test strict equality between the situs address (from LA County parcel data)
and the mailing address (from the future scraped/PRA/commercial source).

Conservative by design — covers only the suffix variants that produce
false-mismatches on real LA County parcel + mailing pairs. Does NOT
handle: leading zeros in house numbers, directional spell-outs
(NORTH -> N), half-house fractions (1/2), unit-marker variants
(APT vs UNIT vs #). Extend incrementally as production mismatches surface.
"""
from __future__ import annotations

import re

_STRIP_PUNCT = re.compile(r"[.,_#\-–]")  # period, comma, underscore, #, ASCII-hyphen, en-dash
_COLLAPSE_WS = re.compile(r"\s+")

# Word-boundary suffix normalizations. Order matters when a longer form
# could be rewritten by a shorter substring rule — apply long-form first.
_SUFFIX_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAVENUE\b"), "AV"),
    (re.compile(r"\bAVE\b"), "AV"),
    (re.compile(r"\bSTREET\b"), "ST"),
    (re.compile(r"\bBOULEVARD\b"), "BLVD"),
    (re.compile(r"\bBLD\b"), "BLVD"),
    (re.compile(r"\bROAD\b"), "RD"),
    (re.compile(r"\bDRIVE\b"), "DR"),
    (re.compile(r"\bCOURT\b"), "CT"),
    (re.compile(r"\bLANE\b"), "LN"),
    (re.compile(r"\bPLACE\b"), "PL"),
    (re.compile(r"\bHIGHWAY\b"), "HWY"),
)


def normalize_address(address_str: str | None) -> str:
    """Returns an upper-case, punctuation-stripped, suffix-canonicalized form.

    Designed for strict-equality matching between two address strings
    that may differ only in casing, punctuation, or street-suffix variants.
    Empty / None input returns an empty string (not an error — callers
    decide whether absent input is signal or noise).
    """
    if not address_str:
        return ""
    s = address_str.upper().strip()
    s = _STRIP_PUNCT.sub(" ", s)
    s = _COLLAPSE_WS.sub(" ", s)
    for pattern, repl in _SUFFIX_RULES:
        s = pattern.sub(repl, s)
    return s.strip()
