"""Internal: prioritized 4-tier ownership classifier (no DimensionValue here).

Returns (profile_label, score) tuples. Profile labels are stable string
constants suitable for narrative / UI surfacing. Public DimensionValue
wrappers live in api/services/dimensions/ownership.py.

Tier order (highest priority first):
  Tier 1  has_homeowners_exemption == True              -> OWNER_OCCUPIED                       0.95
  Tier 2  CORP_SHELL_PATTERN hit (owner name or mail)    -> CORPORATE_INSTITUTIONAL              0.00
  Tier 3  TRUST in owner name (word-boundary)           -> FAMILY_TRUST_POTENTIAL_OCCUPANT      0.40
  Tier 4  PO BOX / PMB in mailing                       -> ABSENTEE_INVESTOR_POBOX              0.05
  Tier 5  normalized situs == normalized mailing        -> OWNER_OCCUPIED_UNCLAIMED_EXEMPTION   0.85
  Tier 6  mail_state != "CA"                            -> OUT_OF_STATE_LANDLORD                0.00
  Tier 7  in-state mismatch (default scraped fallback)  -> LOCAL_ABSENTEE_INVESTOR              0.15

scraped_mail_data=None (1.5c.2a default) skips Tiers 2-7 and emits one of
the three pre-scrape labels: OWNER_OCCUPIED, UNKNOWN_OR_TRUST, ABSENTEE_INVESTOR.
"""
from __future__ import annotations

import re
from datetime import datetime

from api.models.lead import ParcelData
from api.services.dimensions._common import CAL, resolve_arms_length_year
from api.utils.address import normalize_address

OWNER_OCCUPIED = "OWNER_OCCUPIED"
UNKNOWN_OR_TRUST = "UNKNOWN_OR_TRUST"
ABSENTEE_INVESTOR = "ABSENTEE_INVESTOR"
CORPORATE_INSTITUTIONAL = "CORPORATE_INSTITUTIONAL"
FAMILY_TRUST_POTENTIAL_OCCUPANT = "FAMILY_TRUST_POTENTIAL_OCCUPANT"
ABSENTEE_INVESTOR_POBOX = "ABSENTEE_INVESTOR_POBOX"
OWNER_OCCUPIED_UNCLAIMED_EXEMPTION = "OWNER_OCCUPIED_UNCLAIMED_EXEMPTION"
OUT_OF_STATE_LANDLORD = "OUT_OF_STATE_LANDLORD"
LOCAL_ABSENTEE_INVESTOR = "LOCAL_ABSENTEE_INVESTOR"

# (?<!\w)(?!\w) lookarounds — \b fails on L.L.C. / L.P. end-of-string
# (see feedback-regex-lookarounds-for-punctuation).
CORP_SHELL_PATTERN = re.compile(
    r"(?<!\w)("
    r"LLC|L\.L\.C\.|"
    r"CORP(?:ORATION)?|"
    r"INC(?:ORPORATED)?|"
    r"COMPANY|"
    r"PARTNERS|PARTNERSHIP|LP|L\.P\.|"
    r"BANK|TRUST CO|"
    r"HOLDINGS|PROPERTIES|REALTY|"
    r"ASSOCIATES|VENTURES|CAPITAL|FUND|GROUP|"
    r"ENTERPRISES|MANAGEMENT|REMIC|REIT"
    r")(?!\w)",
    re.IGNORECASE,
)

_POBOX_PATTERN = re.compile(r"(?<!\w)(P\.?\s*O\.?\s*BOX|PMB)(?!\w)", re.IGNORECASE)
_TRUST_PATTERN = re.compile(r"\bTRUST\b", re.IGNORECASE)

# Strips a 2-letter uppercase state code that sits immediately before a
# 5-digit ZIP — the canonical US "..., STATE 12345" tail. Used ONLY for the
# situs-vs-mail equality comparison: ParcelData has no state column (LA
# County's CSV doesn't expose one), while scraped mailing strings include
# it. Symmetric application avoids state-asymmetry false-negatives without
# coupling the classifier to any specific state literal.
_STATE_BEFORE_ZIP = re.compile(r"\s+[A-Z]{2}(?=\s+\d{5}(?:$|\s|-))")


def _situs_full_address(parcel: ParcelData) -> str:
    return " ".join(p for p in (parcel.address_situs, parcel.city, parcel.zip) if p)


def _normalized_for_address_compare(s: str) -> str:
    """Strips the state code that appears immediately before a ZIP, on top
    of normalize_address. Region-agnostic — works for CA, NY, TX, etc."""
    return _STATE_BEFORE_ZIP.sub("", s)


def determine_ownership_profile(
    parcel: ParcelData,
    scraped_mail_data: dict | None = None,
) -> tuple[str, float]:
    """Return (profile_label, score). See module docstring for tier order.

    Expected scraped_mail_data keys (all optional): owner_full_name,
    full_mailing_address, mail_state. Missing keys default to empty strings;
    unknown mail_state does NOT fire the out-of-state purge (truth-first:
    don't penalize on absent signal).
    """
    if parcel.has_homeowners_exemption:
        return OWNER_OCCUPIED, 0.95

    if scraped_mail_data is None:
        year, _ = resolve_arms_length_year(parcel)
        if year is not None and (datetime.now().year - year) >= CAL.long_tenure_years:
            return UNKNOWN_OR_TRUST, 0.40
        return ABSENTEE_INVESTOR, 0.15

    owner_name = (scraped_mail_data.get("owner_full_name") or "").upper()
    mail_full = (scraped_mail_data.get("full_mailing_address") or "").upper()
    mail_state = (scraped_mail_data.get("mail_state") or "").upper()

    if CORP_SHELL_PATTERN.search(owner_name) or CORP_SHELL_PATTERN.search(mail_full):
        return CORPORATE_INSTITUTIONAL, 0.00
    if _TRUST_PATTERN.search(owner_name):
        return FAMILY_TRUST_POTENTIAL_OCCUPANT, 0.40
    if _POBOX_PATTERN.search(mail_full):
        return ABSENTEE_INVESTOR_POBOX, 0.05

    situs_norm = _normalized_for_address_compare(normalize_address(_situs_full_address(parcel)))
    mail_norm = _normalized_for_address_compare(normalize_address(mail_full))
    if situs_norm and situs_norm == mail_norm:
        return OWNER_OCCUPIED_UNCLAIMED_EXEMPTION, 0.85

    if mail_state and mail_state != "CA":
        return OUT_OF_STATE_LANDLORD, 0.00
    return LOCAL_ABSENTEE_INVESTOR, 0.15


LABEL_TO_TIER: dict[str, str] = {
    OWNER_OCCUPIED:                     "1a",
    UNKNOWN_OR_TRUST:                   "1b",
    ABSENTEE_INVESTOR:                  "1c",
    CORPORATE_INSTITUTIONAL:            "2",
    FAMILY_TRUST_POTENTIAL_OCCUPANT:    "3",
    ABSENTEE_INVESTOR_POBOX:            "4",
    OWNER_OCCUPIED_UNCLAIMED_EXEMPTION: "5",
    OUT_OF_STATE_LANDLORD:              "6",
    LOCAL_ABSENTEE_INVESTOR:            "7",
}


PROFILE_NOTES: dict[str, str] = {
    OWNER_OCCUPIED:                     "Homeowner's Exemption claimed — sworn legal owner-occupant attestation.",
    UNKNOWN_OR_TRUST:                   "Long tenure, no exemption. Likely inherited / family trust / unfiled owner-occupant.",
    ABSENTEE_INVESTOR:                  "Short tenure, no exemption — likely investor / rental.",
    CORPORATE_INSTITUTIONAL:            "Corporate-shell pattern detected in owner name or mailing address.",
    FAMILY_TRUST_POTENTIAL_OCCUPANT:    "Family / living trust in owner name — CA Prop 13 owner-occupant pattern.",
    ABSENTEE_INVESTOR_POBOX:            "Mail routed to PO BOX / PMB — institutional handling.",
    OWNER_OCCUPIED_UNCLAIMED_EXEMPTION: "Situs == mailing match — owner-occupant who hasn't filed exemption.",
    OUT_OF_STATE_LANDLORD:              "Mailing address outside California — out-of-area landlord.",
    LOCAL_ABSENTEE_INVESTOR:            "In-state mailing mismatch — local investor / second property.",
}
