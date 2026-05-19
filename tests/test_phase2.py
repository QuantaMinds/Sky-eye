"""Phase 2 — 8 tests covering batch endpoint, BigQuery persistence,
parallel processing, semaphore enforcement, partial failures, status, and
cache hits. External APIs and BigQuery are mocked at the seam.

CLAUDE.md Rule 1: this is one cohesive module (the Phase 2 gate).
CLAUDE.md Rule 3: tests must NOT exercise truthful data unless they assert
on it; mocks return explicit shapes so we don't accidentally validate
fabricated values.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import cache as local_cache
from api.main import app
from api.services import _batch_scorer, batch_processor, bigquery_writer


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Isolate per-test state: in-memory job tables + the SQLite cache file."""
    batch_processor._JOBS.clear()
    batch_processor._RESULTS.clear()
    monkeypatch.setattr(local_cache, "_DB_PATH", tmp_path / "phase2_cache.db")


@pytest.fixture
def stub_bq(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Replace the BigQuery writer with in-memory recorders."""
    calls: dict[str, list[Any]] = {"create": [], "update": [], "result": []}

    async def fake_create(job_id, installer_id, count, request_input):
        calls["create"].append((job_id, installer_id, count, request_input))

    async def fake_update(job_id, **fields):
        calls["update"].append((job_id, fields))

    async def fake_result(row):
        calls["result"].append(row)

    monkeypatch.setattr(bigquery_writer, "create_job", fake_create)
    monkeypatch.setattr(bigquery_writer, "update_job", fake_update)
    monkeypatch.setattr(bigquery_writer, "write_result", fake_result)
    return calls


def _ok_row(job_id: str, idx: int, address: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "result_index": idx,
        "input_address": address,
        "scored_status": "scored",
        "priority_score": 0.5,
        # Narrative is intentionally null in batch — lazy via
        # POST /api/v1/score-lead/{apn}/narrative. See
        # feedback-no-narrative-in-batch.
        "gemini_narrative": None,
    }


# --- 1. POST accepts up to 500 addresses --------------------------------

def test_batch_accepts_500_max(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    async def fake_score(job_id, idx, addr):
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", fake_score)

    addresses = [f"{i} Test St, Long Beach, CA" for i in range(500)]
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/batch-score",
            json={"addresses": addresses, "installer_id": "test-installer"},
        )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["address_count"] == 500
    assert body["status"] == "queued"
    assert len(body["job_id"]) >= 32  # uuid4


# --- 2. POST rejects 501 addresses (max length enforced by Pydantic) ----

def test_batch_rejects_501() -> None:
    addresses = [f"{i} Test St" for i in range(501)]
    with TestClient(app) as client:
        r = client.post("/api/v1/batch-score", json={"addresses": addresses})
    assert r.status_code == 422, r.text


# --- 3. Parallel processing — total time << serial time -----------------

def test_batch_processes_in_parallel(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """50 addresses × 100ms sleep. Serial = 5.0s; parallel(10) ≈ 0.5s.
    Allow generous headroom for Windows scheduler jitter — assert <2.0s."""
    async def slow_score(job_id, idx, addr):
        await asyncio.sleep(0.1)
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", slow_score)

    addresses = [f"{i} Test St" for i in range(50)]
    started = time.perf_counter()
    with TestClient(app) as client:
        r = client.post("/api/v1/batch-score", json={"addresses": addresses})
    elapsed = time.perf_counter() - started
    assert r.status_code == 202
    # FastAPI BackgroundTasks runs the work after sending the response but
    # before TestClient unblocks. So elapsed covers the full batch.
    assert elapsed < 2.0, f"batch took {elapsed:.2f}s — not parallel enough"


# --- 4. Each scored lead writes to BigQuery -----------------------------

def test_batch_writes_to_bigquery(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    async def fake_score(job_id, idx, addr):
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", fake_score)

    addresses = [f"{i} BQ Test" for i in range(7)]
    with TestClient(app) as client:
        r = client.post("/api/v1/batch-score", json={"addresses": addresses})
    assert r.status_code == 202

    assert len(stub_bq["create"]) == 1
    assert stub_bq["create"][0][2] == 7  # address_count arg
    assert len(stub_bq["result"]) == 7  # one row per address
    assert len(stub_bq["update"]) == 1
    _, fields = stub_bq["update"][0]
    assert fields["status"] == "complete"
    assert fields["completed_count"] == 7
    assert fields["failed_count"] == 0


# --- 5. GET status endpoint returns the job snapshot --------------------

def test_batch_status_endpoint(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    async def fake_score(job_id, idx, addr):
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", fake_score)

    with TestClient(app) as client:
        sub = client.post(
            "/api/v1/batch-score", json={"addresses": ["1 A St", "2 B St", "3 C St"]}
        )
        job_id = sub.json()["job_id"]
        r = client.get(f"/api/v1/batch-score/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "complete"
    assert body["address_count"] == 3
    assert body["completed_count"] == 3
    assert body["failed_count"] == 0
    assert len(body["results"]) == 3

    # 404 for unknown job
    with TestClient(app) as client:
        r404 = client.get("/api/v1/batch-score/does-not-exist")
    assert r404.status_code == 404


# --- 6. Partial failures don't break the batch --------------------------

def test_batch_handles_partial_failures(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    async def flaky(job_id, idx, addr):
        if idx % 3 == 0:
            raise RuntimeError(f"geocoding failed for {addr}")
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", flaky)

    addresses = [f"{i} Mixed St" for i in range(10)]
    with TestClient(app) as client:
        sub = client.post("/api/v1/batch-score", json={"addresses": addresses})
        job_id = sub.json()["job_id"]
        r = client.get(f"/api/v1/batch-score/{job_id}")
    body = r.json()
    assert body["status"] == "complete"
    assert body["completed_count"] == 6  # 10 - ceil(10/3)
    assert body["failed_count"] == 4
    # Counter-split contract: pure api_failure run has zero skipped.
    assert body["skipped_count"] == 0
    assert body["failure_reasons"] == {"api_failure": 4}
    # Every address produced a row, success or failure.
    assert len(stub_bq["result"]) == 10
    failures = [r for r in stub_bq["result"] if r["scored_status"] == "api_failure"]
    assert len(failures) == 4
    assert all("error_message" in f for f in failures)


# --- 7. Semaphore limits concurrency to SOLAR_CONCURRENCY (=10) ---------

def test_rate_limit_respected(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    state = {"active": 0, "peak": 0}

    async def tracking_score(job_id, idx, addr):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.05)
        state["active"] -= 1
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", tracking_score)
    assert batch_processor.SOLAR_CONCURRENCY == 10

    addresses = [f"{i} Sem St" for i in range(40)]
    with TestClient(app) as client:
        client.post("/api/v1/batch-score", json={"addresses": addresses})
    assert state["peak"] <= batch_processor.SOLAR_CONCURRENCY
    assert state["peak"] >= 5  # confirms parallelism is actually happening


# --- 8. Cache hits skip the upstream API call ---------------------------

def test_batch_does_not_call_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vertex AI narrative MUST NOT be invoked from the batch path.
    See feedback-no-narrative-in-batch."""
    from api.services import narrative as narrative_svc

    calls: list[Any] = []

    async def boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("narrative.generate_narrative must not be called from batch")

    monkeypatch.setattr(narrative_svc, "generate_narrative", boom)

    # Stub all upstream services so we exercise the real _batch_scorer
    # without hitting external APIs. The point is to confirm that the
    # narrative module is unreferenced from the batch code path.
    from api.models.lead import (
        CensusData, DacInfo, GeocodingResult, NRELData, SolarRoofData, UtilityInfo,
    )
    from api.services import (
        bigquery_writer as bw,
        census, dac, geocoding, nrel, parcel_lookup, solar_api, utility,
    )

    async def fake_geo(addr): return GeocodingResult(lat=33.77, lng=-118.19, formatted_address=addr), False
    async def fake_solar(lat, lng, a): return SolarRoofData(max_array_panels=10, max_kwh_year=12000), False
    async def fake_census(lat, lng): return CensusData(median_household_income=85000, block_group_geoid="060371234001"), False
    async def fake_nrel(lat, lng, **kw): return NRELData(ac_annual_kwh=8000), False
    async def fake_parcel(lat, lng): return None, False
    async def fake_util(lat, lng): return UtilityInfo(), False
    async def fake_dac(lat, lng): return DacInfo(), False
    async def noop_create(*a, **kw): return None
    async def noop_update(*a, **kw): return None
    async def noop_write(*a, **kw): return None

    monkeypatch.setattr(geocoding, "geocode", fake_geo)
    monkeypatch.setattr(solar_api, "get_roof_data", fake_solar)
    monkeypatch.setattr(census, "get_block_group_data", fake_census)
    monkeypatch.setattr(nrel, "get_production", fake_nrel)
    monkeypatch.setattr(parcel_lookup, "lookup_by_point", fake_parcel)
    monkeypatch.setattr(utility, "lookup_by_point", fake_util)
    monkeypatch.setattr(dac, "lookup_by_point", fake_dac)
    monkeypatch.setattr(bw, "create_job", noop_create)
    monkeypatch.setattr(bw, "update_job", noop_update)
    monkeypatch.setattr(bw, "write_result", noop_write)

    with TestClient(app) as client:
        sub = client.post(
            "/api/v1/batch-score", json={"addresses": ["1 Real St", "2 Real St"]}
        )
        job_id = sub.json()["job_id"]
        r = client.get(f"/api/v1/batch-score/{job_id}")
    assert r.status_code == 200
    rows = r.json()["results"]
    assert len(rows) == 2
    assert all(row["gemini_narrative"] is None for row in rows)
    assert calls == []  # Gemini never invoked


def test_job_status_falls_back_to_bigquery(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """Simulate worker restart: in-memory _JOBS is cleared. GET must still
    return the job state by reading BigQuery."""
    async def fake_score(job_id, idx, addr):
        return _ok_row(job_id, idx, addr)
    monkeypatch.setattr(_batch_scorer, "score_one_address", fake_score)

    bq_jobs: dict[str, dict[str, Any]] = {}
    bq_rows: dict[str, list[dict[str, Any]]] = {}

    async def fake_read_job(job_id):
        return bq_jobs.get(job_id)

    async def fake_read_results(job_id):
        return bq_rows.get(job_id, [])

    # Mirror what process_batch / write_result would write to BQ.
    real_create = stub_bq  # already records, but we also need to mirror to bq_jobs
    async def capture_create(job_id, installer_id, count, request_input):
        bq_jobs[job_id] = {
            "job_id": job_id, "installer_id": installer_id, "address_count": count,
            "status": "processing", "completed_count": 0, "failed_count": 0,
        }

    async def capture_update(job_id, **fields):
        bq_jobs[job_id].update(fields)

    async def capture_result(row):
        bq_rows.setdefault(row["job_id"], []).append(row)

    from api.services import bigquery_writer as bw
    monkeypatch.setattr(bw, "create_job", capture_create)
    monkeypatch.setattr(bw, "update_job", capture_update)
    monkeypatch.setattr(bw, "write_result", capture_result)
    monkeypatch.setattr(bw, "read_job", fake_read_job)
    monkeypatch.setattr(bw, "read_results", fake_read_results)

    with TestClient(app) as client:
        sub = client.post(
            "/api/v1/batch-score", json={"addresses": ["1 Restart Way", "2 Restart Way"]}
        )
        job_id = sub.json()["job_id"]
        # Simulate worker restart — wipe in-memory mirror.
        batch_processor._JOBS.clear()
        batch_processor._RESULTS.clear()
        r = client.get(f"/api/v1/batch-score/{job_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "complete"
    assert body["completed_count"] == 2
    assert len(body["results"]) == 2
    # Cache should be repopulated for next poll on this worker.
    assert job_id in batch_processor._JOBS


def test_batch_skips_multi_unit_collision(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """When parcel_lookup returns resolution_confidence='building' (multiple
    AINs share the polygon — condo siblings), the row MUST be emitted with
    scored_status='multi_unit_skipped' and a row-level error_message, NOT
    ranked with a fabricated identical-twin priority_score. This is the gate
    the Phase 2 smoke test exposed via the deliberately-included `525 E
    SEASIDE WAY PH1` edge case."""
    from api.models.lead import (
        CensusData, DacInfo, GeocodingResult, NRELData, ParcelData,
        SolarRoofData, UtilityInfo,
    )
    from api.services import (
        census, dac, geocoding, nrel, parcel_lookup, solar_api, utility,
    )

    async def fake_geo(addr):
        return GeocodingResult(lat=33.77, lng=-118.19, formatted_address=addr), False
    async def fake_solar(lat, lng, a):
        return SolarRoofData(max_array_panels=10, max_kwh_year=12000), False
    async def fake_census(lat, lng):
        return CensusData(median_household_income=85000, block_group_geoid="060371234001"), False
    async def fake_nrel(lat, lng, **kw):
        return NRELData(ac_annual_kwh=8000), False
    async def fake_util(lat, lng):
        return UtilityInfo(), False
    async def fake_dac(lat, lng):
        return DacInfo(), False

    async def fake_parcel_building(lat, lng):
        return ParcelData(
            apn="7280001001", address_situs="525 E SEASIDE WAY PH1",
            city="LONG BEACH CA", zip="90802",
            use_category="Residential", use_subcategory="Condominium",
            is_residential=True, is_taxable=True, stream="private",
            resolution_confidence="building", ains_at_point=3,
        ), False

    monkeypatch.setattr(geocoding, "geocode", fake_geo)
    monkeypatch.setattr(solar_api, "get_roof_data", fake_solar)
    monkeypatch.setattr(census, "get_block_group_data", fake_census)
    monkeypatch.setattr(nrel, "get_production", fake_nrel)
    monkeypatch.setattr(parcel_lookup, "lookup_by_point", fake_parcel_building)
    monkeypatch.setattr(utility, "lookup_by_point", fake_util)
    monkeypatch.setattr(dac, "lookup_by_point", fake_dac)

    with TestClient(app) as client:
        sub = client.post(
            "/api/v1/batch-score",
            json={"addresses": ["525 E SEASIDE WAY PH1, Long Beach, CA 90802"]},
        )
        job_id = sub.json()["job_id"]
        r = client.get(f"/api/v1/batch-score/{job_id}")
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    assert len(rows) == 1
    row = rows[0]
    assert row["scored_status"] == "multi_unit_skipped"
    assert row["resolved_ain"] == "7280001001"
    assert row["resolution_confidence"] == "building"
    # No priority_score on skipped rows — truth-first: never invent a number
    # we won't rank on.
    assert row.get("priority_score") is None
    # error_message must name the collision and the C-46 scope reason.
    msg = row["error_message"]
    assert "Multi-unit" in msg
    assert "3 AINs" in msg
    assert "C-46" in msg


def test_batch_skipped_count_is_distinct_from_failed(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """Counter-split contract: multi_unit_skipped rows MUST land in
    skipped_count, NOT failed_count. Verifies the regression that prompted
    the split — pre-split, "62 failed" silently merged 55 condo skips with
    7 real timeouts.

    Mix: 2 scored + 3 multi_unit_skipped + 1 api_failure = 6 total.
    """
    async def mixed_score(job_id, idx, addr):
        base = {"job_id": job_id, "result_index": idx, "input_address": addr}
        if idx < 2:
            return {**base, "scored_status": "scored", "priority_score": 0.5}
        if idx < 5:
            return {**base, "scored_status": "multi_unit_skipped",
                    "error_message": "Multi-unit building detected"}
        return {**base, "scored_status": "api_failure",
                "error_message": "ConnectTimeout"}
    monkeypatch.setattr(_batch_scorer, "score_one_address", mixed_score)

    addresses = [f"{i} Mix St" for i in range(6)]
    with TestClient(app) as client:
        sub = client.post("/api/v1/batch-score", json={"addresses": addresses})
        job_id = sub.json()["job_id"]
        body = client.get(f"/api/v1/batch-score/{job_id}").json()

    assert body["completed_count"] == 2
    assert body["skipped_count"] == 3
    assert body["failed_count"] == 1
    # Invariant: address_count == completed + skipped + failed
    assert body["address_count"] == (
        body["completed_count"] + body["skipped_count"] + body["failed_count"]
    )


def test_skip_reasons_dict_populated_correctly(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """skip_reasons is keyed by raw scored_status — no hardcoded enum. With
    3 multi_unit_skipped rows the dict must read {'multi_unit_skipped': 3}.
    failure_reasons must NOT contain a zero-bucket for api_failure (truth-
    first: no fake entries)."""
    async def all_skipped(job_id, idx, addr):
        return {
            "job_id": job_id, "result_index": idx, "input_address": addr,
            "scored_status": "multi_unit_skipped",
            "error_message": "Multi-unit building detected (45 AINs)",
        }
    monkeypatch.setattr(_batch_scorer, "score_one_address", all_skipped)

    with TestClient(app) as client:
        sub = client.post(
            "/api/v1/batch-score",
            json={"addresses": ["1 Tower Way", "2 Tower Way", "3 Tower Way"]},
        )
        job_id = sub.json()["job_id"]
        body = client.get(f"/api/v1/batch-score/{job_id}").json()

    assert body["skip_reasons"] == {"multi_unit_skipped": 3}
    # No zero-bucket entries for statuses that never appeared.
    assert body.get("failure_reasons") in (None, {})


def test_unknown_status_does_not_inflate_completed(
    monkeypatch: pytest.MonkeyPatch, stub_bq: dict[str, list[Any]]
) -> None:
    """Defensive: a future scored_status value not in any known set MUST
    roll into failed_count (visible), never into completed_count (silent).
    Catches the next conflation bug before it ships."""
    async def unknown_status(job_id, idx, addr):
        return {
            "job_id": job_id, "result_index": idx, "input_address": addr,
            "scored_status": "rate_limited_pending_retry",  # not in any set
            "error_message": "future status",
        }
    monkeypatch.setattr(_batch_scorer, "score_one_address", unknown_status)

    with TestClient(app) as client:
        sub = client.post("/api/v1/batch-score", json={"addresses": ["1 Future Ln"]})
        job_id = sub.json()["job_id"]
        body = client.get(f"/api/v1/batch-score/{job_id}").json()

    assert body["completed_count"] == 0  # the contract — silent inflation forbidden
    assert body["skipped_count"] == 0
    assert body["failed_count"] == 1
    # And the unknown status surfaces by its real name in failure_reasons.
    assert body["failure_reasons"] == {"rate_limited_pending_retry": 1}


def test_create_job_uses_dml_insert_not_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock the streaming-buffer fix: _create_job_sync MUST go through
    client.query() (DML INSERT), NOT insert_rows_json (streaming insert).

    Why this test matters: pre-fix, all 5 batch_jobs rows ever written
    read 'status=queued, counts=0' because streaming-buffered rows can't
    be UPDATEd, and the update exception was swallowed. If anyone reverts
    to insert_rows_json for this path, this test fails immediately.
    """
    from api.services import bigquery_writer as bw

    calls: dict[str, list[object]] = {"query": [], "insert_rows_json": []}

    class _FakeJob:
        def result(self):
            return None

    class _FakeClient:
        def query(self, sql: str, **kwargs):
            calls["query"].append({"sql": sql, "kwargs": kwargs})
            return _FakeJob()

        def insert_rows_json(self, table: str, rows: list[dict]):
            calls["insert_rows_json"].append({"table": table, "rows": rows})
            return []  # signal "no errors" if anyone calls this

    monkeypatch.setattr(bw, "_client", lambda: _FakeClient())

    bw._create_job_sync(
        job_id="job-dml-test",
        installer_id="t",
        address_count=3,
        request_input="1 A St; 2 B St; 3 C St",
    )

    assert len(calls["insert_rows_json"]) == 0, (
        "regression: _create_job_sync fell back to streaming insert — "
        "rows in the buffer can't be UPDATEd and job counts go silently stale"
    )
    assert len(calls["query"]) == 1
    sql = calls["query"][0]["sql"]
    assert "INSERT INTO" in sql.upper()
    assert "batch_jobs" in sql


def test_cache_hits_skip_api_calls() -> None:
    """Hit the real geocoding service via the SQLite cache. Seeded entries
    must return without invoking the HTTP transport at all."""
    from api.services import geocoding as geo_service

    local_cache.set(
        "geocode:cached address",
        {"lat": 33.77, "lng": -118.19, "formatted_address": "Cached Address"},
    )

    async def fail_if_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("HTTP must not be called when cache is warm")

    import httpx

    class _ExplodingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            await fail_if_called()

    original = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **kw: _ExplodingClient()  # type: ignore[assignment]
    try:
        result, was_cached = asyncio.run(geo_service.geocode("Cached Address"))
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]
    assert was_cached is True
    assert result.lat == 33.77
