"""Phase 5 foundation tests — the pieces needed BEFORE labeling can begin.

Scope: imports + idempotency + truth-first surface (None/source='unavailable'
when chips are missing). Live EE / BQ calls are gated on credentials, same
as test_phase1.py.

The actual precision benchmark lives in tests/test_phase5.py (next turn),
once the labeling tool has produced fixtures/known_changes/labels.csv.
"""
from __future__ import annotations

import importlib
import os

import pytest


def _have(*keys: str) -> bool:
    return all(bool(os.environ.get(k)) for k in keys)


# --- 1. Module imports cleanly --------------------------------------------

def test_earth_engine_module_imports() -> None:
    import api.services.earth_engine as ee_mod
    assert hasattr(ee_mod, "init")
    assert hasattr(ee_mod, "ee_module")


def test_chip_extractor_module_imports() -> None:
    import api.services.chip_extractor as ce
    assert hasattr(ce, "fetch_pair")
    assert hasattr(ce, "montage")


def test_lb_parcels_module_imports() -> None:
    import api.services.lb_parcels as lb
    assert hasattr(lb, "get_parcel_geometry")
    assert hasattr(lb, "list_apns_in_bbox")


def test_permit_ingest_module_imports() -> None:
    import api.services.permit_ingest as pi
    assert hasattr(pi, "fetch_page")
    assert hasattr(pi, "normalize_row")
    assert hasattr(pi, "upsert_rows")


# --- 2. EE init is idempotent ---------------------------------------------

@pytest.mark.skipif(
    not _have("GOOGLE_CLOUD_PROJECT") and not _have("EARTH_ENGINE_PROJECT"),
    reason="needs GCP / EE project set",
)
def test_earth_engine_init_idempotent() -> None:
    import api.services.earth_engine as ee_mod
    ee_mod._reset_for_tests()
    ee_mod.init()
    ee_mod.init()  # second call must be a no-op, not double-init


# --- 3. Chip ChipResult truth-first contract ------------------------------

def test_chip_result_unavailable_has_no_png() -> None:
    from api.services.ee_naip import ChipResult
    r = ChipResult(png=None, source="unavailable", image_date=None, note="x")
    assert r.png is None
    assert r.source == "unavailable"


def test_chip_save_skips_when_no_png(tmp_path) -> None:
    from api.services.ee_naip import ChipResult, save_chip
    chip = ChipResult(png=None, source="unavailable", image_date=None, note=None)
    out = tmp_path / "x.png"
    assert save_chip(chip, out) is False
    assert not out.exists()


# --- 4. permit_ingest normalize_row preserves NULLs (Rule 3) -------------

def test_normalize_row_missing_apn_stays_none() -> None:
    from api.services.permit_ingest import normalize_row
    mapping = {"permit_id": "pn", "issued_date": "id"}  # no 'ain' in mapping
    row = normalize_row({"pn": "P-001", "id": "2024-03-15"}, mapping, "https://x/y.json")
    assert row["permit_id"] == "P-001"
    assert row["ain"] is None  # never substituted
    assert row["estimated_value"] is None
    assert str(row["issued_date"]) == "2024-03-15"


def test_normalize_row_bad_date_returns_none() -> None:
    from api.services.permit_ingest import normalize_row
    mapping = {"permit_id": "pn", "issued_date": "id"}
    row = normalize_row({"pn": "P-002", "id": "not-a-date"}, mapping, "u")
    assert row["issued_date"] is None  # truth-first; do not fabricate


# --- 5. Labeling CLI imports + arg parser shape ---------------------------

def test_labeling_cli_imports() -> None:
    """The CLI must be importable as a module so the docstring renders in
    `python -m scripts.label_parcels --help`. It also imports its deps at
    module import time, so an ImportError here means the foundation is
    broken before the user can even start labeling."""
    spec = importlib.util.spec_from_file_location(
        "label_parcels",
        os.path.join(os.path.dirname(__file__), "..", "scripts", "label_parcels.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "CHIPS_DIR")
    assert hasattr(mod, "LABELS_CSV")
