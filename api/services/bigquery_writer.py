"""BigQuery writer for batch scoring jobs and results.

Two write paths, both async wrappers over the sync BigQuery SDK:
  - jobs   -> leadlens.batch_jobs   (one row per batch request)
  - results -> leadlens.batch_results (one row per scored address)

Truth-first: every dimension value/source/confidence is preserved as-is.
None stays None (no substitute constants — see CLAUDE.md Rule 3).
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

from google.cloud import bigquery

from api.config import get_settings

_PROJECT = "sky-eye-496604"
_LOCATION = "us-west1"
_JOBS_TABLE = f"{_PROJECT}.leadlens.batch_jobs"
_RESULTS_TABLE = f"{_PROJECT}.leadlens.batch_results"


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or _PROJECT
    return bigquery.Client(project=project, location=_LOCATION)


def _now_iso() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat()


def _create_job_sync(
    job_id: str, installer_id: str | None, address_count: int, request_input: str
) -> None:
    """Insert the job header row via DML INSERT, NOT streaming insert.

    Why: BigQuery refuses DML UPDATE/DELETE against rows still in the
    streaming buffer (~30 min residency). Earlier versions used
    `insert_rows_json`, which sent the row through the streaming buffer
    and made the subsequent UPDATE in process_batch silently fail (caught
    by the swallowing `except` and ignored). Pre-fix, all 5 batch_jobs
    rows ever written read `status='queued', counts=0` regardless of
    actual job state — cross-worker / direct-BQ readers saw wrong data.

    DML INSERT goes through the query path: no streaming buffer, row is
    immediately UPDATE-able. Cost is identical at this volume (~hundreds
    of jobs/day; one tiny INSERT each).
    """
    now = dt.datetime.now(tz=dt.timezone.utc)
    expires = now + dt.timedelta(days=90)
    sql = f"""
    INSERT INTO `{_JOBS_TABLE}` (
        job_id, installer_id, request_type, request_input, address_count,
        status, completed_count, skipped_count, failed_count,
        created_at, expires_at
    ) VALUES (
        @job_id, @installer_id, @request_type, @request_input, @address_count,
        @status, @completed_count, @skipped_count, @failed_count,
        @created_at, @expires_at
    )
    """
    params = [
        bigquery.ScalarQueryParameter("job_id", "STRING", job_id),
        bigquery.ScalarQueryParameter("installer_id", "STRING", installer_id),
        bigquery.ScalarQueryParameter("request_type", "STRING", "address_list"),
        bigquery.ScalarQueryParameter("request_input", "STRING", request_input[:500]),
        bigquery.ScalarQueryParameter("address_count", "INT64", address_count),
        bigquery.ScalarQueryParameter("status", "STRING", "queued"),
        bigquery.ScalarQueryParameter("completed_count", "INT64", 0),
        bigquery.ScalarQueryParameter("skipped_count", "INT64", 0),
        bigquery.ScalarQueryParameter("failed_count", "INT64", 0),
        bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", now),
        bigquery.ScalarQueryParameter("expires_at", "TIMESTAMP", expires),
    ]
    _client().query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    ).result()


def _update_job_sync(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    client = _client()
    sets = ", ".join(f"{k} = @{k}" for k in fields)
    params = [
        bigquery.ScalarQueryParameter("jid", "STRING", job_id),
        *(bigquery.ScalarQueryParameter(k, _bq_type(v), v) for k, v in fields.items()),
    ]
    client.query(
        f"UPDATE `{_JOBS_TABLE}` SET {sets} WHERE job_id = @jid",
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    ).result()


def _bq_type(v: Any) -> str:
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, int):
        return "INT64"
    if isinstance(v, float):
        return "FLOAT64"
    if isinstance(v, dt.datetime):
        return "TIMESTAMP"
    return "STRING"


def _sanitize_for_bq(row: dict[str, Any]) -> dict[str, Any]:
    """Round floats to 9 decimals — BigQuery NUMERIC scale limit.

    Python floats serialize to JSON with ~17 sig figs, which the streaming
    insert path rejects for NUMERIC columns with no fallback retry. Found
    via Phase 2 smoke run: bill_pain=0.69364390164266965 silently dropped
    every scored row in the first live batch.
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        out[k] = round(v, 9) if isinstance(v, float) else v
    return out


def _write_result_sync(row: dict[str, Any]) -> None:
    errors = _client().insert_rows_json(_RESULTS_TABLE, [_sanitize_for_bq(row)])
    if errors:
        raise RuntimeError(f"insert batch_results failed: {errors}")


def _read_job_sync(job_id: str) -> dict[str, Any] | None:
    q = (
        "SELECT job_id, installer_id, address_count, status, "
        "completed_count, skipped_count, failed_count, "
        "created_at, started_at, completed_at "
        f"FROM `{_JOBS_TABLE}` WHERE job_id = @jid LIMIT 1"
    )
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("jid", "STRING", job_id)]
    )
    row = next(iter(_client().query(q, job_config=cfg).result()), None)
    return dict(row.items()) if row else None


def _read_results_sync(job_id: str) -> list[dict[str, Any]]:
    q = f"SELECT * FROM `{_RESULTS_TABLE}` WHERE job_id = @jid ORDER BY result_index"
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("jid", "STRING", job_id)]
    )
    return [dict(r.items()) for r in _client().query(q, job_config=cfg).result()]


async def create_job(
    job_id: str, installer_id: str | None, address_count: int, request_input: str
) -> None:
    await asyncio.to_thread(
        _create_job_sync, job_id, installer_id, address_count, request_input
    )


async def update_job(job_id: str, **fields: Any) -> None:
    await asyncio.to_thread(_update_job_sync, job_id, **fields)


async def write_result(row: dict[str, Any]) -> None:
    row.setdefault("scored_at", _now_iso())
    await asyncio.to_thread(_write_result_sync, row)


async def read_job(job_id: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_read_job_sync, job_id)


async def read_results(job_id: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_read_results_sync, job_id)


def _lookup_latest_by_apn_sync(apn: str) -> dict[str, Any] | None:
    q = (
        f"SELECT * FROM `{_RESULTS_TABLE}` "
        "WHERE resolved_ain = @apn AND scored_status = 'scored' "
        "ORDER BY scored_at DESC LIMIT 1"
    )
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("apn", "STRING", apn)]
    )
    row = next(iter(_client().query(q, job_config=cfg).result()), None)
    return dict(row.items()) if row else None


def _write_narrative_back_sync(apn: str, text: str) -> None:
    q = (
        f"UPDATE `{_RESULTS_TABLE}` "
        "SET gemini_narrative = @txt "
        "WHERE resolved_ain = @apn AND scored_status = 'scored'"
    )
    cfg = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("apn", "STRING", apn),
            bigquery.ScalarQueryParameter("txt", "STRING", text),
        ]
    )
    _client().query(q, job_config=cfg).result()


async def lookup_latest_by_apn(apn: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_lookup_latest_by_apn_sync, apn)


async def write_narrative_back(apn: str, text: str) -> None:
    await asyncio.to_thread(_write_narrative_back_sync, apn, text)
