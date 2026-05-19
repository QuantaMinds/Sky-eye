"""Phase 3 tests — PDF report generation.

All 6 tests must pass before Phase 3 ships (CLAUDE.md Rule 2).

Tests cover the full render path with the JSON fixture, plus the GCS
storage layer with mocks (suite stays hermetic — no live network).
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pypdf import PdfReader

from api.models.lead import UtilityInfo
from api.services import pdf_generator, report_data, report_storage

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_lead_data.json"
FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
FIXTURE.pop("_doc", None)


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def test_pdf_renders_without_errors():
    pdf = pdf_generator.render_pdf(FIXTURE)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:5] == b"%PDF-", "output is not a PDF"
    assert len(pdf) > 1000, "PDF suspiciously small"


def test_pdf_has_all_sections():
    pdf = pdf_generator.render_pdf(FIXTURE)
    text = _extract_text(pdf).lower()
    for needle in ("address", "lead score", "score breakdown",
                   "roof", "financial", "analyst summary"):
        assert needle in text, f"missing section: {needle!r}"
    # Concrete data from fixture
    assert "1234 sunset" in text
    assert "0.74" in text  # priority_score


def test_pdf_includes_attribution():
    pdf = pdf_generator.render_pdf(FIXTURE)
    text = _extract_text(pdf).lower()
    assert "data sources:" in text
    assert "google maps platform solar api" in text
    assert "nrel pvwatts" in text
    today = dt.date.today().isoformat()
    assert today in text, "generation date missing from attribution"


async def test_signed_url_expires_24h(mocker):
    fake_blob = MagicMock()
    fake_blob.generate_signed_url.return_value = "https://signed.example/pdf"
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket
    mocker.patch("api.services.report_storage.storage.Client", return_value=fake_client)

    url = await report_storage.upload_and_sign(
        b"%PDF-fake", "2026-05-18/test.pdf", ttl_hours=24
    )
    assert url == "https://signed.example/pdf"
    fake_blob.upload_from_string.assert_called_once()
    args, kwargs = fake_blob.generate_signed_url.call_args
    assert kwargs["expiration"] == dt.timedelta(hours=24)
    assert kwargs["version"] == "v4"
    assert kwargs["method"] == "GET"


def test_white_label_logo_swaps():
    logo_a = "data:image/png;base64," + base64.b64encode(b"AAA-marker").decode()
    logo_b = "data:image/png;base64," + base64.b64encode(b"BBB-marker").decode()
    html_a = pdf_generator.render_html(
        FIXTURE, installer={"name": "Installer-A", "logo_data_uri": logo_a}
    )
    html_b = pdf_generator.render_html(
        FIXTURE, installer={"name": "Installer-B", "logo_data_uri": logo_b}
    )
    assert "Installer-A" in html_a
    assert "Installer-B" in html_b
    assert logo_a in html_a
    assert logo_b in html_b
    # Logo swap must visibly change the output (not a no-op pass-through)
    assert html_a != html_b


def test_pdf_under_500kb_size():
    pdf = pdf_generator.render_pdf(FIXTURE)
    assert len(pdf) < 500_000, f"PDF too large: {len(pdf):,} bytes (>500 KB)"


def test_build_view_propagates_none_not_fabrications():
    """Rule-3 guard: every nullable BQ field must propagate None into
    the view dict — NEVER coerce to 0.0 / '' / False / 1.0.

    This test catches the class of bug found in the Phase 3 forensic
    audit (2026-05-18): silent coercion across 5 fields produced a PDF
    that asserted score=0.00 + confidence=100% for unscored leads, and
    a fabricated savings dollar figure for any lead outside SCE/LADWP.
    See [[feedback-forensic-pass-on-green-tests]].
    """
    empty_row: dict = {}
    view = report_data.build_view(empty_row, None, None, None)

    # Scalar fields the mapper must NOT fabricate.
    assert view["priority_score"] is None, "priority_score must not coerce to 0.0"
    assert view["score_confidence"] is None, "score_confidence must not be hard-coded"
    assert view["address"] is None, "address must not coerce to ''"
    assert view["has_homeowners_exemption"] is None, \
        "has_homeowners_exemption must be three-valued, not bool(None)"

    # Roof / NREL / financial sub-objects must all carry None when source missing.
    assert view["roof"]["max_array_panels"] is None
    assert view["roof"]["max_kwh_year"] is None
    assert view["roof"]["max_sunshine_hours"] is None
    assert view["nrel"]["ac_annual_kwh"] is None
    assert view["financial"]["estimated_annual_savings_usd"] is None
    assert view["financial"]["rate_per_kwh_usd"] is None
    assert view["financial"]["simple_payback_years"] is None


def test_build_view_drops_utility_fallback_rate():
    """When utility lookup falls back to the 'unknown' territory row,
    rate + savings MUST surface as None — not as the 0.30 default that
    UtilityInfo carries for fallback rows. Direct test of the §2.5
    forensic finding.
    """
    fallback_util = UtilityInfo()  # default: rate=0.30, confidence_level='fallback'

    # Even with a real roof kWh number, the savings calc must abstain.
    class _Roof:
        max_kwh_year = 10_000.0
        max_array_panels = 20
        max_sunshine_hours = 1700.0

    view = report_data.build_view({}, _Roof(), None, fallback_util)
    assert view["financial"]["rate_per_kwh_usd"] is None, \
        "fallback rate must not propagate to the view"
    assert view["financial"]["estimated_annual_savings_usd"] is None, \
        "savings must not be computed against a fallback rate"


def test_build_view_uses_measured_utility_rate():
    """Counterpart to the fallback test: when utility lookup is real
    ('precise' or 'approximate' confidence), the rate DOES flow through
    and savings are computed. This proves the gate is on confidence_level,
    not blanket suppression."""
    real_util = UtilityInfo(
        utility_name="LADWP",
        representative_rate=0.32,
        confidence_level="precise",
    )

    class _Roof:
        max_kwh_year = 10_000.0
        max_array_panels = 20
        max_sunshine_hours = 1700.0

    view = report_data.build_view({}, _Roof(), None, real_util)
    assert view["financial"]["rate_per_kwh_usd"] == 0.32
    assert view["financial"]["estimated_annual_savings_usd"] == 3200.0


async def test_generate_report_inline_default(mocker, monkeypatch):
    """Default mode: USE_GCS_STORAGE unset → endpoint returns PDF bytes
    inline with the right Content-Disposition. No GCS calls.

    Mirrors the webhook-deferred decision: ship the upload path dark
    until a real consumer needs persistence. See
    [[feedback-gcs-deferred-until-real-consumer]].
    """
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.delenv("USE_GCS_STORAGE", raising=False)
    view = report_data.build_view(FIXTURE.get("__notarow__", {}), None, None, None)
    view.update({
        "apn": "7156012038",
        "address": "1234 Sunset Blvd",
        "priority_score": 0.74,
        "score_confidence": 0.86,
        "narrative": "short",
        "data_sources": ["X"],
    })
    mocker.patch("api.routers.reports.report_data.fetch_for_apn", return_value=view)
    upload_spy = mocker.patch("api.routers.reports.report_storage.upload_and_sign")

    with TestClient(app) as client:
        r = client.post("/api/v1/generate-report", json={"apn": "7156012038"})

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="lead_7156012038_' in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"
    upload_spy.assert_not_called(), "default mode must not touch GCS"


def test_pdf_renders_with_all_nulls_no_crash():
    """The template must render without TypeError when every nullable
    field is None — catches Jinja format-on-None and similar crashes
    that would surface only in production for unscored leads.
    """
    empty_view = report_data.build_view({}, None, None, None)
    pdf = pdf_generator.render_pdf(empty_view)
    assert pdf[:5] == b"%PDF-"
    text = _extract_text(pdf).lower()
    assert "unavailable" in text or "unknown" in text, \
        "missing-data PDF should surface 'Unavailable' or 'unknown' somewhere"
