"""Phase 5 — TaxLens change detection. One cohesive module (Rule 1 exception).

External calls (EE, Gemini Pro, BigQuery permits) are mocked at the seam
so pytest never burns EECU credits or Vertex tokens. Live-credential
tests are gated on env vars and skip when absent — same pattern as
test_phase1.py.

Matched-pair gate tests (per feedback_matched_pair_rule3_gates): for
every gate in confidence_pipeline we test fires-True, fires-False, AND
input-None-drops-from-score. Single-direction tests would pass while
over- or under-suppressing real signal.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from api.middleware import _bq_cache, ttl_cache  # noqa: E402
from api.services import (  # noqa: E402
    change_detector,
    confidence_pipeline,
    ee_alphaearth,
    multimodal_classifier,
    permit_matcher,
)


@pytest.fixture(autouse=True)
def _isolate_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same shape as test_phase1 — never touch production cache state."""
    from fakeredis import aioredis as _fr
    ttl_cache._set_redis_client_for_tests(_fr.FakeRedis(decode_responses=True))

    async def _noop_get(*a, **kw): return None
    async def _noop_set(*a, **kw): return None
    monkeypatch.setattr(_bq_cache, "get", _noop_get)
    monkeypatch.setattr(_bq_cache, "set", _noop_set)
    permit_matcher._reset_coverage_cache_for_tests()


# --- 1. AlphaEarth embedding loader returns 64-D vector or None -----------

def test_alphaearth_embeddings_load_64_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked EE: reduceRegion returns a full 64-band stats dict ->
    EmbeddingResult.vector is a 64-float list, source='alphaearth'."""
    class FakeStats:
        def getInfo(self):
            return {f"A{i:02d}": float(i) / 64.0 for i in range(64)}

    class FakeImage:
        def select(self, _bands): return self
        def reduceRegion(self, **kw): return FakeStats()

    class FakeColl:
        def filterBounds(self, _g): return self
        def filterDate(self, _s, _e): return self
        def size(self):
            class S:
                def getInfo(self_inner): return 1
            return S()
        def mosaic(self): return FakeImage()

    class FakeReducer:
        @staticmethod
        def mean(): return object()

    class FakeEE:
        def Geometry(self, geo): return object()
        def ImageCollection(self, _name): return FakeColl()
        Reducer = FakeReducer

    monkeypatch.setattr(ee_alphaearth, "ee_module", lambda: FakeEE())
    result = ee_alphaearth.get_alphaearth_embeddings({"type": "Point", "coordinates": [0, 0]}, 2024)
    assert result.source == "alphaearth"
    assert result.vector is not None and len(result.vector) == 64


def test_alphaearth_returns_unavailable_when_no_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """size=0 -> source='unavailable', vector=None (Rule 3, no zero-vector substitute)."""
    class FakeColl:
        def filterBounds(self, _g): return self
        def filterDate(self, _s, _e): return self
        def size(self):
            class S:
                def getInfo(self_inner): return 0
            return S()

    class FakeEE:
        def Geometry(self, geo): return object()
        def ImageCollection(self, _name): return FakeColl()

    monkeypatch.setattr(ee_alphaearth, "ee_module", lambda: FakeEE())
    result = ee_alphaearth.get_alphaearth_embeddings({"type": "Point", "coordinates": [0, 0]}, 2024)
    assert result.source == "unavailable"
    assert result.vector is None


# --- 2. cosine_distance is the math we expect -----------------------------

def test_cosine_distance_identity_is_zero() -> None:
    v = [1.0, 2.0, 3.0]
    assert abs(change_detector.cosine_distance(v, v)) < 1e-9


def test_cosine_distance_orthogonal_is_one() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(change_detector.cosine_distance(a, b) - 1.0) < 1e-9


def test_cosine_distance_nan_on_zero_vector() -> None:
    """A zero vector signals a masked-everywhere reduction we should have
    surfaced as 'unavailable' upstream. If we got here, return NaN so
    change_detector drops the row instead of ranking it 1.0."""
    import math
    assert math.isnan(change_detector.cosine_distance([0.0, 0.0], [1.0, 1.0]))


# --- 3. permit_matcher tri-state ------------------------------------------

def test_permit_matcher_returns_none_when_apn_empty() -> None:
    assert permit_matcher.has_permit("", dt.date(2022, 1, 1), dt.date(2024, 12, 31)) is None


def test_permit_matcher_returns_none_when_coverage_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coverage check returns False (zero LB rows in window) ->
    has_permit returns None for every APN, NOT False. Otherwise an
    unpopulated permits table would inflate every detection as
    'unpermitted' (Rule 3, the load-bearing case)."""
    monkeypatch.setattr(permit_matcher, "has_coverage", lambda s, e: False)
    out = permit_matcher.has_permit("1234001001", dt.date(2022, 1, 1), dt.date(2024, 12, 31))
    assert out is None  # NOT False — that would fabricate "no permit found"


def test_permit_matcher_returns_true_when_match_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coverage exists AND apn has a permit row -> True."""
    monkeypatch.setattr(permit_matcher, "has_coverage", lambda s, e: True)
    monkeypatch.setattr(permit_matcher, "_client",
                        lambda: _FakeBQ(count_rows=[{"n": 2}]))
    out = permit_matcher.has_permit("1234001001", dt.date(2022, 1, 1), dt.date(2024, 12, 31))
    assert out is True


def test_permit_matcher_returns_false_when_match_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coverage exists AND apn has zero permit rows -> False (legitimately
    unpermitted in a covered window — gate 2 should fire)."""
    monkeypatch.setattr(permit_matcher, "has_coverage", lambda s, e: True)
    monkeypatch.setattr(permit_matcher, "_client",
                        lambda: _FakeBQ(count_rows=[{"n": 0}]))
    out = permit_matcher.has_permit("1234001001", dt.date(2022, 1, 1), dt.date(2024, 12, 31))
    assert out is False


class _FakeBQ:
    def __init__(self, count_rows): self._rows = count_rows
    def query(self, _sql, job_config=None):
        rows = self._rows
        class _Job:
            def result(self_inner): return iter(rows)
        return _Job()


# --- 4. Multimodal classifier truth-first surface -------------------------

@pytest.mark.asyncio
async def test_classifier_returns_unavailable_when_chip_missing() -> None:
    """Either chip None -> Gemini NEVER called, source='unavailable'."""
    result, hit = await multimodal_classifier.classify(
        apn="1234", sqft=2000, use_subcategory="SFR",
        png_a=None, png_b=b"\x89PNG",
        naip_a_date="", naip_b_date="2024-06-01",
    )
    assert result.source == "unavailable"
    assert result.change_type is None and result.confidence_0_1 is None
    assert hit is False


@pytest.mark.asyncio
async def test_classifier_parses_pool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked Pro returns valid JSON -> source='gemini_pro', fields parsed."""
    def fake_call(prompt, png_a, png_b):
        return (
            '{"change_type":"new_pool","confidence_0_1":0.84,'
            '"estimated_added_sqft":null,"evidence":"rectangular blue pool in backyard"}',
            500, 80,
        )
    monkeypatch.setattr(multimodal_classifier, "_call_gemini_pro", fake_call)

    result, _ = await multimodal_classifier.classify(
        apn="1234", sqft=2000, use_subcategory="SFR",
        png_a=b"\x89PNGfake", png_b=b"\x89PNGfake",
        naip_a_date="2022-06-01", naip_b_date="2024-06-01",
    )
    assert result.source == "gemini_pro"
    assert result.change_type == "new_pool"
    assert abs(result.confidence_0_1 - 0.84) < 1e-6
    assert result.estimated_added_sqft is None  # null from JSON stays null
    assert "blue pool" in (result.evidence or "")


@pytest.mark.asyncio
async def test_classifier_unavailable_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed JSON -> source='unavailable', no salvage attempt (Rule 3)."""
    monkeypatch.setattr(
        multimodal_classifier, "_call_gemini_pro",
        lambda p, a, b: ("not even close to json", 100, 50),
    )
    result, _ = await multimodal_classifier.classify(
        apn="1234", sqft=2000, use_subcategory="SFR",
        png_a=b"\x89PNG", png_b=b"\x89PNG",
        naip_a_date="2022-06-01", naip_b_date="2024-06-01",
    )
    assert result.source == "unavailable"
    assert "JSON parse failed" in (result.note or "")


@pytest.mark.asyncio
async def test_classifier_unavailable_on_invalid_change_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """change_type not in the closed enum -> 'unavailable', NOT
    coerced to 'no_significant_change' (that would hide bugs)."""
    monkeypatch.setattr(
        multimodal_classifier, "_call_gemini_pro",
        lambda p, a, b: ('{"change_type":"alien_landing","confidence_0_1":0.9}', 100, 50),
    )
    result, _ = await multimodal_classifier.classify(
        apn="1234", sqft=2000, use_subcategory="SFR",
        png_a=b"\x89PNG", png_b=b"\x89PNG",
        naip_a_date="2022-06-01", naip_b_date="2024-06-01",
    )
    assert result.source == "unavailable"
    assert "alien_landing" in (result.note or "")


# --- 5. 5-gate confidence pipeline (matched-pair tests per gate) ----------

def test_confidence_pipeline_all_gates_fire() -> None:
    """High-distance, no-permit, real change, high conf, big sqft uplift."""
    r = confidence_pipeline.evaluate(
        alphaearth_distance=0.7,           # > 0.4
        has_permit_result=False,           # no permit
        gemini_change_type="new_pool",     # not no_change
        gemini_confidence=0.85,            # > 0.7
        gemini_added_sqft=400.0,           # > 100
    )
    assert r.available_gates == 5
    assert r.fired_gates == 5
    assert r.final_score == 1.0


def test_confidence_pipeline_no_gates_fire() -> None:
    """Counter-evidence on every gate -> score 0.0, not None."""
    r = confidence_pipeline.evaluate(
        alphaearth_distance=0.1,                       # < 0.4
        has_permit_result=True,                        # permit found
        gemini_change_type="no_significant_change",
        gemini_confidence=0.3,                         # < 0.7
        gemini_added_sqft=10.0,                        # < 100
    )
    assert r.available_gates == 5
    assert r.fired_gates == 0
    assert r.final_score == 0.0


def test_confidence_pipeline_drops_unavailable_gates() -> None:
    """Permits unavailable + classifier unavailable -> only 1 gate
    (embedding) is available. Score = 1/1 = 1.0 if it fires.
    The point: a None gate is NEITHER 0 nor 0.5 — it disappears."""
    r = confidence_pipeline.evaluate(
        alphaearth_distance=0.7,
        has_permit_result=None,        # permits dataset absent
        gemini_change_type=None,       # classifier didn't run
        gemini_confidence=None,
        gemini_added_sqft=None,
    )
    assert r.available_gates == 1
    assert r.fired_gates == 1
    assert r.final_score == 1.0


def test_confidence_pipeline_all_none_score_is_none() -> None:
    """Every input None -> final_score=None. NEVER substitute 0.0 — that
    would tell a customer 'definitely no change' from zero evidence."""
    r = confidence_pipeline.evaluate(
        alphaearth_distance=None, has_permit_result=None,
        gemini_change_type=None, gemini_confidence=None,
        gemini_added_sqft=None,
    )
    assert r.available_gates == 0
    assert r.final_score is None


def test_permit_gate_inverts_correctly() -> None:
    """has_permit=True -> gate FAILS (counter-evidence). has_permit=False
    -> gate FIRES. Matched-pair test for the inversion that's easy to
    get backwards in code review."""
    r_true = confidence_pipeline.evaluate(
        alphaearth_distance=0.7, has_permit_result=True,
        gemini_change_type="new_pool", gemini_confidence=0.9, gemini_added_sqft=400.0,
    )
    r_false = confidence_pipeline.evaluate(
        alphaearth_distance=0.7, has_permit_result=False,
        gemini_change_type="new_pool", gemini_confidence=0.9, gemini_added_sqft=400.0,
    )
    assert r_true.gates["no_permit"].fired is False  # permit found -> gate fails
    assert r_false.gates["no_permit"].fired is True  # no permit -> gate fires


def test_embedding_gate_nan_distance_is_unavailable() -> None:
    """NaN distance (zero-norm vector upstream) -> gate fired=None,
    NOT False. `float('nan') > 0.4` is False in Python, which would
    silently vote 'counter-evidence' for an unknown signal — exactly
    the Rule 3 violation pattern. Matched against the numeric-distance
    tests above."""
    r = confidence_pipeline.evaluate(
        alphaearth_distance=float("nan"),
        has_permit_result=False, gemini_change_type="new_pool",
        gemini_confidence=0.9, gemini_added_sqft=400.0,
    )
    assert r.gates["embedding_distance"].fired is None
    # Available gates drops to 4, score reflects 4 fires of 4.
    assert r.available_gates == 4 and r.fired_gates == 4
    assert r.final_score == 1.0


def test_value_uplift_gate_exact_threshold() -> None:
    """Threshold is STRICT > 100. 100 sqft -> False, 101 -> True. Catches
    off-by-one regressions on the boundary."""
    base = dict(
        alphaearth_distance=0.7, has_permit_result=False,
        gemini_change_type="new_pool", gemini_confidence=0.9,
    )
    r_at = confidence_pipeline.evaluate(gemini_added_sqft=100.0, **base)
    r_above = confidence_pipeline.evaluate(gemini_added_sqft=100.1, **base)
    assert r_at.gates["value_uplift"].fired is False
    assert r_above.gates["value_uplift"].fired is True


# --- 6. End-to-end pipeline (mocked external calls, exercises endpoint) ----

def test_full_pipeline_e2e_with_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/v1/detect-changes against a single-parcel bbox. All
    external services mocked; we're testing the orchestration, not the
    real precision number (that's the benchmark)."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.services import (
        change_detector as cd, change_events_writer as ew, chip_extractor as ce,
        lb_parcels, multimodal_classifier as mc, permit_matcher as pm,
    )

    monkeypatch.setattr(
        cd, "detect_changes_in_bbox",
        lambda *a, **kw: [cd.ChangeCandidate(
            apn="1234001001", distance=0.62,
            year_a=kw.get("year_a") or a[4], year_b=kw.get("year_b") or a[5],
            embedding_a_date="2022-annual", embedding_b_date="2024-annual",
        )],
    )
    monkeypatch.setattr(
        lb_parcels, "get_parcel_geometry",
        lambda apn: {"apn": apn, "geojson": {"type": "Point", "coordinates": [0, 0]},
                     "sqft_main": 2000, "use_subcategory": "SFR", "address_situs": "1 X"},
    )
    monkeypatch.setattr(
        ce, "fetch_pair",
        lambda apn, ya, yb: ce.ParcelChipSet(
            apn=apn,
            parcel={"apn": apn, "sqft_main": 2000, "use_subcategory": "SFR"},
            naip_a=ce.ChipResult(png=b"\x89PNG_a", source="naip", image_date=f"{ya}-06-01"),
            naip_b=ce.ChipResult(png=b"\x89PNG_b", source="naip", image_date=f"{yb}-06-01"),
            s2_a=ce.ChipResult(png=None, source="unavailable", image_date=None),
            s2_b=ce.ChipResult(png=None, source="unavailable", image_date=None),
        ),
    )

    async def fake_classify(**kw):
        return mc.ClassificationResult(
            change_type="new_pool", confidence_0_1=0.84,
            estimated_added_sqft=300.0, evidence="rect blue pool",
            source="gemini_pro",
        ), False
    monkeypatch.setattr(mc, "classify", fake_classify)
    monkeypatch.setattr(pm, "has_permit", lambda apn, s, e: False)

    # Stub the BQ writer — tests must not touch the real change_events table.
    persisted_rows: list[dict] = []

    async def fake_persist(detections, year_a, year_b):
        persisted_rows.extend(
            ew._row_for(d, year_a, year_b) for d in detections
        )
        non_null = [r for r in persisted_rows if r is not None]
        return len(non_null), len(persisted_rows) - len(non_null)

    monkeypatch.setattr(ew, "persist_detections", fake_persist)

    with TestClient(app) as client:
        r = client.post(
            "/api/v1/detect-changes",
            json={"bbox": [-118.20, 33.75, -118.10, 33.82],
                  "year_a": 2022, "year_b": 2024, "min_confidence": 0.6},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidates_considered"] == 1
    assert body["detections_above_threshold"] == 1
    d = body["detections"][0]
    assert d["apn"] == "1234001001"
    assert d["final_score"] == 1.0
    assert d["available_gates"] == 5 and d["fired_gates"] == 5
    assert d["classifier_source"] == "gemini_pro"
    assert d["change_type"] == "new_pool"
    # Truth-first surface: every gate breakdown carries the raw input.
    assert d["gates"]["embedding_distance"]["raw_input"] == 0.62
    assert d["gates"]["no_permit"]["raw_input"] is False  # has_permit_result=False -> fires
    # Persistence contract: this detection has final_score!=None so it was persisted.
    assert body["persisted_rows"] == 1
    assert body["persistence_skipped"] == 0
    assert persisted_rows[0]["confidence_score"] == 1.0
    assert persisted_rows[0]["permit_check_status"] == "no_permit_in_window"


# --- 7. Benchmark gate (smoke set vs customer-facing benchmark) ----------

LABELS_CSV = Path("fixtures/known_changes/labels.csv")


@pytest.mark.skipif(not LABELS_CSV.exists(), reason="ground-truth labels not yet built")
def test_benchmark_runs_against_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """When labels.csv exists, the benchmark must read and report against
    it. We DO NOT assert the precision number here — that's the
    benchmark script's job, and the published-claim threshold (>=100
    labels, non-author labeled) is enforced there. See
    feedback_precision_claim_validation_minimum."""
    import csv
    rows = list(csv.DictReader(LABELS_CSV.open()))
    assert len(rows) > 0
    # Header contract — if this breaks, the benchmark stops working silently.
    for required in ("apn", "year_a", "year_b", "has_change", "change_type"):
        assert required in rows[0], f"labels.csv missing column: {required}"
