"""Forensic audit of Phase 3 PDF report generation.

Not for production. Builds five test views (the fixture + four edge
cases), drives the full render pipeline, extracts the PDF text, and
audits every claim made on each PDF against the source data.

Audit goals (CLAUDE.md Rule 4 — data quality is separate from tests):
  - Verify every field that lands in the PDF traces back to source data.
  - Flag fabrication: any value the PDF asserts that wasn't in the input.
  - Verify None propagation: a None input MUST render as "Unavailable",
    never as 0 / "" / midpoint constant.
  - Exercise the GCS upload path against a fake client to confirm
    bytes flow correctly into upload_from_string + signed URL builder.
  - Time the render; verify size; verify it's a real PDF.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pypdf import PdfReader  # noqa: E402

from api.services import pdf_generator, report_data, report_storage  # noqa: E402

FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "sample_lead_data.json").read_text(encoding="utf-8")
)
FIXTURE.pop("_doc", None)


def hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def extract(pdf_bytes: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def audit_view(label: str, view: dict, expected_unavailable: list[str]) -> dict:
    """Render the view, dump bytes, extract text, check claims."""
    hr(f"CASE: {label}")
    t0 = time.perf_counter()
    pdf = pdf_generator.render_pdf(view)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    text = extract(pdf)
    text_l = text.lower()

    out = {
        "label": label,
        "bytes": len(pdf),
        "elapsed_ms": round(elapsed_ms, 1),
        "is_pdf": pdf[:5] == b"%PDF-",
        "findings": [],
    }
    print(f"  bytes={out['bytes']:,}  elapsed={out['elapsed_ms']} ms  is_pdf={out['is_pdf']}")
    print(f"  page_count={len(PdfReader(io.BytesIO(pdf)).pages)}")

    # Check Unavailable rendering for fields the case says should be missing.
    for field in expected_unavailable:
        if "unavailable" not in text_l:
            out["findings"].append(
                f"FAIL: {field!r} should surface as 'Unavailable' but text has none"
            )

    # Whatever the view says, does it match the PDF?
    addr = (view.get("address") or "").lower()
    if addr and addr[:18] not in text_l:
        out["findings"].append(f"FAIL: address {addr!r} not in PDF text")
    score = view.get("priority_score")
    if score is not None and f"{score:.2f}" not in text:
        out["findings"].append(f"FAIL: score {score:.2f} not in PDF text")
    if view.get("apn") and view["apn"] not in text:
        out["findings"].append(f"FAIL: apn {view['apn']!r} not in PDF text")

    # Attribution + date always required.
    today = dt.date.today().isoformat()
    if today not in text:
        out["findings"].append("FAIL: generation date missing from attribution")
    if "data sources:" not in text_l:
        out["findings"].append("FAIL: 'Data sources:' missing from attribution")

    print("  --- extracted text (truncated) ---")
    print("\n".join("    " + ln for ln in text.splitlines()[:25]))
    if len(text.splitlines()) > 25:
        print(f"    ...({len(text.splitlines()) - 25} more lines)")
    print(f"  --- findings: {len(out['findings'])} ---")
    for f in out["findings"]:
        print(f"    {f}")
    return out


def audit_storage_path() -> dict:
    """Drive report_storage with a fake client; confirm bytes hand off correctly."""
    hr("CASE: GCS storage path (mocked client)")
    captured = {}

    fake_blob = MagicMock()
    def _signed(**kwargs):
        captured["signed_kwargs"] = kwargs
        return "https://storage.googleapis.com/leadlens-reports/test.pdf?X-Goog-Signature=fakebigsig&exp=86400"
    fake_blob.generate_signed_url.side_effect = _signed
    def _upload(data, content_type):
        captured["upload_bytes_len"] = len(data)
        captured["upload_content_type"] = content_type
        captured["upload_starts_with"] = data[:5]
    fake_blob.upload_from_string.side_effect = _upload

    fake_bucket = MagicMock()
    def _blob(name):
        captured["blob_name"] = name
        return fake_blob
    fake_bucket.blob.side_effect = _blob

    fake_client = MagicMock()
    def _bucket(name):
        captured["bucket_name"] = name
        return fake_bucket
    fake_client.bucket.side_effect = _bucket

    import asyncio
    from unittest.mock import patch
    pdf = pdf_generator.render_pdf(FIXTURE)
    with patch("api.services.report_storage.storage.Client", return_value=fake_client):
        url = asyncio.run(report_storage.upload_and_sign(
            pdf, "2026-05-18/forensic-test.pdf", ttl_hours=24,
        ))

    print(json.dumps({k: (str(v) if not isinstance(v, (int, str, bytes)) else (v.decode("latin1") if isinstance(v, bytes) else v)) for k, v in captured.items()}, indent=2, default=str))
    print(f"  returned_url={url}")

    findings = []
    if captured.get("bucket_name") != "leadlens-reports":
        findings.append(f"FAIL: bucket name {captured.get('bucket_name')!r} != 'leadlens-reports'")
    if captured.get("upload_content_type") != "application/pdf":
        findings.append(f"FAIL: content_type {captured.get('upload_content_type')!r}")
    if captured.get("upload_bytes_len") != len(pdf):
        findings.append(f"FAIL: upload bytes len {captured.get('upload_bytes_len')} != pdf len {len(pdf)}")
    if captured.get("upload_starts_with") != b"%PDF-":
        findings.append(f"FAIL: upload bytes don't start with %PDF-: {captured.get('upload_starts_with')!r}")
    skw = captured.get("signed_kwargs") or {}
    if skw.get("expiration") != dt.timedelta(hours=24):
        findings.append(f"FAIL: signed-url expiration {skw.get('expiration')!r} != 24h")
    if skw.get("version") != "v4":
        findings.append(f"FAIL: signed-url version {skw.get('version')!r} != v4")
    if not url.startswith("https://"):
        findings.append(f"FAIL: returned URL not https: {url!r}")
    print(f"  --- findings: {len(findings)} ---")
    for f in findings:
        print(f"    {f}")
    return {"label": "storage", "findings": findings}


def audit_fabrication() -> dict:
    """Walk build_view() with edge inputs to surface Rule-3 violations."""
    hr("CASE: Rule-3 fabrication audit (build_view edge cases)")
    findings = []

    # 1. priority_score missing → check the value the PDF asserts
    row = {"input_address": "X", "priority_score": None, "geocoded_lat": 1.0, "geocoded_lng": 2.0}
    v = report_data.build_view(row, None, None, None)
    print(f"  empty row priority_score in view = {v['priority_score']!r}  (input was None)")
    if v["priority_score"] == 0.0:
        findings.append(
            "FAIL Rule-3: priority_score=None coerced to 0.0 in build_view "
            "(line: `float(row.get('priority_score') or 0.0)`). PDF will "
            "claim 0.00 with confidence 100% for unscored leads."
        )

    # 2. score_confidence hard-coded
    print(f"  empty row score_confidence  = {v['score_confidence']!r}  (NOT in batch_results schema)")
    if v["score_confidence"] == 1.0:
        findings.append(
            "FAIL Rule-3: score_confidence hard-coded to 1.0 in build_view. "
            "batch_results does NOT store confidence; this fabricates "
            "'100% confidence' for every PDF."
        )

    # 3. address missing
    row2 = {"priority_score": 0.5}
    v2 = report_data.build_view(row2, None, None, None)
    print(f"  no-address view address = {v2['address']!r}")
    if v2["address"] == "":
        findings.append(
            "FAIL Rule-3: missing input_address coerced to '' in build_view. "
            "Hero address block renders empty rather than 'Unknown address'."
        )

    # 4. has_homeowners_exemption None → False
    print(f"  no-row exemption = {v2['has_homeowners_exemption']!r}  (input None)")
    if v2["has_homeowners_exemption"] is False:
        findings.append(
            "FAIL Rule-3: has_homeowners_exemption=None coerced to False. "
            "An unfiled/unknown exemption silently reads as 'no exemption'."
        )

    # 5. utility fallback rate fabricates savings
    from api.models.lead import SolarRoofData, UtilityInfo
    fake_roof = SolarRoofData(max_array_panels=20, max_kwh_year=10000.0, max_sunshine_hours=1700.0)
    fallback_util = UtilityInfo()  # rate defaults to 0.30, confidence_level='fallback'
    v3 = report_data.build_view({"input_address": "X"}, fake_roof, None, fallback_util)
    print(f"  fallback-util financial = {v3['financial']!r}")
    if v3["financial"]["estimated_annual_savings_usd"] == 3000.0:
        findings.append(
            "FAIL Rule-3: utility confidence='fallback' silently produces "
            "a fabricated savings figure (rate=$0.30 default × kWh). "
            "build_view does NOT check utility_data.confidence_level."
        )

    print(f"  --- findings: {len(findings)} ---")
    for f in findings:
        print(f"    {f}")
    return {"label": "fabrication", "findings": findings}


def run_edge_cases() -> list[dict]:
    """Drive the render with deliberately incomplete views."""
    results = []

    # all-null dims
    v = deepcopy(FIXTURE)
    for d in v["dimensions"]:
        d["value"] = None
        d["source"] = "unavailable"
    results.append(audit_view("all-7-dims-null", v, expected_unavailable=["all dims"]))

    # missing roof/nrel/financial
    v = deepcopy(FIXTURE)
    v["roof"] = {"max_array_panels": None, "max_kwh_year": None, "max_sunshine_hours": None}
    v["nrel"] = {"ac_annual_kwh": None, "capacity_factor": None}
    v["financial"] = {"estimated_annual_savings_usd": None, "rate_per_kwh_usd": None, "simple_payback_years": None}
    results.append(audit_view("no-roof-no-financial", v, expected_unavailable=["roof", "financial"]))

    # no narrative
    v = deepcopy(FIXTURE)
    v["narrative"] = None
    results.append(audit_view("no-narrative", v, expected_unavailable=["narrative"]))

    # apn missing
    v = deepcopy(FIXTURE)
    v["apn"] = None
    results.append(audit_view("no-apn", v, expected_unavailable=[]))

    return results


def main() -> None:
    hr("PHASE 3 FORENSIC AUDIT")
    print(f"  ROOT={ROOT}")
    print(f"  fixture keys: {sorted(FIXTURE.keys())}")
    print(f"  dim count: {len(FIXTURE['dimensions'])}")

    all_findings: list[dict] = []
    all_findings.append(audit_view("happy-path-fixture", FIXTURE, expected_unavailable=[]))
    all_findings.extend(run_edge_cases())
    all_findings.append(audit_storage_path())
    all_findings.append(audit_fabrication())

    hr("SUMMARY")
    total_fail = 0
    for r in all_findings:
        n = len(r["findings"])
        total_fail += n
        flag = "OK " if n == 0 else f"FAIL({n})"
        print(f"  {flag}  {r['label']}")
    print()
    print(f"  TOTAL FINDINGS: {total_fail}")


if __name__ == "__main__":
    main()
