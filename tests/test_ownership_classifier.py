"""Tests for the prioritized 4-tier ownership classifier.

Includes the two structural profiles the user explicitly called out
(true corporate shell with out-of-state PO Box; California living trust
on a situs-match property) plus coverage for every tier of the hierarchy
so a future regression can be located precisely.
"""
from __future__ import annotations

import pytest

from api.models.lead import ParcelData
from api.services.dimensions._ownership_classifier import (
    ABSENTEE_INVESTOR,
    ABSENTEE_INVESTOR_POBOX,
    CORPORATE_INSTITUTIONAL,
    FAMILY_TRUST_POTENTIAL_OCCUPANT,
    LOCAL_ABSENTEE_INVESTOR,
    OUT_OF_STATE_LANDLORD,
    OWNER_OCCUPIED,
    OWNER_OCCUPIED_UNCLAIMED_EXEMPTION,
    UNKNOWN_OR_TRUST,
    determine_ownership_profile,
)


def _parcel(
    apn: str = "1234567890",
    situs: str = "1122 BIXBY RD",
    city: str = "LONG BEACH",
    zip_: str = "90807",
    exempt: bool = False,
    arms_year: int | None = None,
) -> ParcelData:
    return ParcelData(
        apn=apn,
        address_situs=situs,
        city=city,
        zip=zip_,
        use_category="Residential",
        is_residential=True,
        is_taxable=True,
        has_homeowners_exemption=exempt,
        arms_length_year=arms_year,
    )


# --- Tier 1: sworn exemption wins regardless of mailing data ---

def test_tier1_exemption_no_scraped_data() -> None:
    p = _parcel(exempt=True)
    label, score = determine_ownership_profile(p, scraped_mail_data=None)
    assert (label, score) == (OWNER_OCCUPIED, 0.95)


def test_tier1_exemption_beats_corporate_mailing() -> None:
    """Even if scraped mailing shows LLC, sworn exemption is canonical."""
    p = _parcel(exempt=True)
    scraped = {"owner_full_name": "ACME PROPERTIES LLC", "mail_state": "DE"}
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (OWNER_OCCUPIED, 0.95)


# --- Phase 1.5c.2a fallback (scraped_mail_data is None) ---

def test_fallback_long_tenure_no_exemption() -> None:
    p = _parcel(exempt=False, arms_year=1980)
    label, score = determine_ownership_profile(p, scraped_mail_data=None)
    assert (label, score) == (UNKNOWN_OR_TRUST, 0.40)


def test_fallback_short_tenure_no_exemption() -> None:
    p = _parcel(exempt=False, arms_year=2020)
    label, score = determine_ownership_profile(p, scraped_mail_data=None)
    assert (label, score) == (ABSENTEE_INVESTOR, 0.15)


def test_fallback_no_tenure_data() -> None:
    p = _parcel(exempt=False, arms_year=None)
    label, score = determine_ownership_profile(p, scraped_mail_data=None)
    assert (label, score) == (ABSENTEE_INVESTOR, 0.15)


# --- Tier 2: corporate-shell purge (user fixture #1) ---

def test_tier2_corporate_llc_out_of_state_po_box() -> None:
    """USER FIXTURE: 4242 LIME AV, LONG BEACH — true corporate shell
    (out-of-state PO Box with LLC keyword). Must hard-purge to 0.00."""
    p = _parcel(situs="4242 LIME AV", city="LONG BEACH", zip_="90807")
    scraped = {
        "owner_full_name": "INVESCO EQUITY PARTNERS LLC",
        "full_mailing_address": "PO BOX 4690, DEEDVILLE, DE 19801",
        "mail_state": "DE",
    }
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (CORPORATE_INSTITUTIONAL, 0.00)


def test_tier2_corporate_in_mailing_address() -> None:
    """Corp keyword in mailing address (not owner name) also purges."""
    p = _parcel()
    scraped = {
        "owner_full_name": "JOHN SMITH",
        "full_mailing_address": "C/O ACME REALTY HOLDINGS 500 MAIN ST",
        "mail_state": "CA",
    }
    label, _ = determine_ownership_profile(p, scraped)
    assert label == CORPORATE_INSTITUTIONAL


# --- Tier 3: family living trust protection (user fixture #2) ---

def test_tier3_family_living_trust_situs_match() -> None:
    """USER FIXTURE: 1122 BIXBY RD — CA Living Trust + situs match.
    The trust protection rule must bypass corporate purge AND beat the
    situs-match tier (TRUST is the more specific signal). Result: 0.40."""
    p = _parcel(situs="1122 BIXBY RD", city="LONG BEACH", zip_="90807")
    scraped = {
        "owner_full_name": "THE HAROLD AND MAUDE LIVING TRUST",
        "full_mailing_address": "1122 BIXBY RD, LONG BEACH, CA 90807",
        "mail_state": "CA",
    }
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (FAMILY_TRUST_POTENTIAL_OCCUPANT, 0.40)


def test_tier3_trust_word_boundary_not_substring() -> None:
    """TRUSTEE / TRUSTMARK in owner name must NOT fire family-trust tier."""
    p = _parcel()
    for non_trust in ["JANE TRUSTEE OF SMITH ESTATE", "TRUSTMARK INSURANCE CORP"]:
        scraped = {"owner_full_name": non_trust, "full_mailing_address": "X", "mail_state": "CA"}
        label, _ = determine_ownership_profile(p, scraped)
        # TRUSTMARK has CORP -> corporate. JANE TRUSTEE has no other markers -> LOCAL_ABSENTEE.
        assert label != FAMILY_TRUST_POTENTIAL_OCCUPANT


# --- Tier 4: PO BOX / PMB ---

def test_tier4_po_box() -> None:
    p = _parcel()
    scraped = {"owner_full_name": "JANE DOE", "full_mailing_address": "PO BOX 1234 ANYTOWN CA 90000", "mail_state": "CA"}
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (ABSENTEE_INVESTOR_POBOX, 0.05)


def test_tier4_pmb() -> None:
    p = _parcel()
    scraped = {"owner_full_name": "JOHN DOE", "full_mailing_address": "100 MAIN ST PMB 47 LOS ANGELES CA 90001", "mail_state": "CA"}
    label, _ = determine_ownership_profile(p, scraped)
    assert label == ABSENTEE_INVESTOR_POBOX


def test_tier4_pobox_punctuation_variants() -> None:
    p = _parcel()
    for variant in ["P.O. BOX 100", "P.O.BOX 100", "P O BOX 100"]:
        scraped = {"owner_full_name": "JOHN DOE", "full_mailing_address": variant, "mail_state": "CA"}
        label, _ = determine_ownership_profile(p, scraped)
        assert label == ABSENTEE_INVESTOR_POBOX, f"{variant!r} should match"


# --- Tier 5: situs == mailing strong-confirm ---

def test_tier5_situs_equals_mailing_owner_unfiled_exemption() -> None:
    p = _parcel(situs="4242 LIME AV", city="LONG BEACH", zip_="90807")
    scraped = {
        "owner_full_name": "JANE DOE",
        "full_mailing_address": "4242 LIME AVE Long Beach, CA 90807",
        "mail_state": "CA",
    }
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (OWNER_OCCUPIED_UNCLAIMED_EXEMPTION, 0.85)


# --- Tier 6: out-of-state landlord ---

def test_tier6_out_of_state_landlord() -> None:
    p = _parcel()
    scraped = {"owner_full_name": "JOHN DOE", "full_mailing_address": "500 PARK AV NEW YORK NY 10022", "mail_state": "NY"}
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (OUT_OF_STATE_LANDLORD, 0.00)


def test_tier6_unknown_state_does_not_purge() -> None:
    """Truth-first: missing mail_state must NOT fire the out-of-state purge."""
    p = _parcel(situs="100 X ST", city="LA", zip_="90001")
    scraped = {"owner_full_name": "JOHN DOE", "full_mailing_address": "500 OTHER ST 90002", "mail_state": ""}
    label, _ = determine_ownership_profile(p, scraped)
    assert label != OUT_OF_STATE_LANDLORD  # falls through to LOCAL_ABSENTEE_INVESTOR


# --- Tier 7: local in-state mismatch fallback ---

def test_tier7_local_in_state_mismatch() -> None:
    p = _parcel(situs="100 SUBJECT ST", city="LOS ANGELES", zip_="90001")
    scraped = {"owner_full_name": "JOHN DOE", "full_mailing_address": "200 OTHER ST SAN FRANCISCO CA 94105", "mail_state": "CA"}
    label, score = determine_ownership_profile(p, scraped)
    assert (label, score) == (LOCAL_ABSENTEE_INVESTOR, 0.15)
