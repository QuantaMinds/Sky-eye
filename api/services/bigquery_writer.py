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
    now = dt.datetime.now(tz=dt.timezone.utc)
    expires = now + dt.timedelta(days=90)
    row = {
        "job_id": job_id,
        "installer_id": installer_id,
        "request_type": "address_list",
        "request_input": request_input[:500],
        "address_count": address_count,
        "status": "queued",
        "completed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }
    errors = _client().insert_rows_json(_JOBS_TABLE, [row])
    if errors:
        raise RuntimeError(f"insert batch_jobs failed: {errors}")


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
