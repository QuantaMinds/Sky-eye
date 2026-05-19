"""Eyeball test for Phase 3 — generates ./tmp/sample_report.pdf from the
JSON fixture so the developer can physically open the PDF and check quality.

Usage:
    python scripts/generate_sample_report.py
    start tmp\\sample_report.pdf       # Windows
    open tmp/sample_report.pdf         # macOS

Per Phase 3 gate: don't ship until you've eyeballed at least 3 real PDFs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.services import pdf_generator  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_lead_data.json"
OUT_DIR = ROOT / "tmp"
OUT_PATH = OUT_DIR / "sample_report.pdf"


def main() -> None:
    view = json.loads(FIXTURE.read_text(encoding="utf-8"))
    view.pop("_doc", None)
    pdf_bytes = pdf_generator.render_pdf(view)
    OUT_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_bytes(pdf_bytes)
    kb = len(pdf_bytes) / 1024
    print(f"wrote {OUT_PATH} ({kb:.1f} KB)")
    if kb > 500:
        print("WARNING: PDF exceeds 500 KB target")


if __name__ == "__main__":
    main()
