"""Parallel batch scoring with a Solar-API concurrency cap.

Design:
  - One asyncio.Semaphore(10) gates concurrent calls to the Solar API,
    keeping us well under the documented 600/min quota even at full burst.
  - Per-address failures are isolated: one bad address writes an error row
    and the rest of the batch continues (Rule 3 — surface unknowns, don't
    crash the pipeline).
  - Job status is mirrored in-memory so GET /batch-score/{job_id} can
    answer immediately without hitting BigQuery's streaming buffer.
  - BigQuery is the persistent store (leadlens.batch_jobs + batch_results).

CLAUDE.md Rule 1: this is one cohesive module — the batch fan-out. The
single-address scoring helper is colocated because it is only used here.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

from api.services import _batch_counters, _batch_scorer, bigquery_writer

SOLAR_CONCURRENCY = 10

# In-memory job state — survives the lifetime of one uvicorn worker.
# Authoritative store is BigQuery; this is a low-latency mirror so the
# GET status endpoint doesn't pay a BQ round-trip on every poll.
_JOBS: dict[str, dict[str, Any]] = {}
_RESULTS: dict[str, list[dict[str, Any]]] = {}


async def get_job(job_id: str) -> dict[str, Any] | None:
    """Return the job snapshot.

    In-memory first (sub-millisecond on a warm worker), then BigQuery
    fallback so polling still works after worker restart or on a peer
    pod that didn't see the original POST. Re-populates the in-memory
    mirror so subsequent polls on this worker hit memory.

    skip_reasons / failure_reasons are derived from the row list on every
    read (not stored separately) so the BigQuery-fallback path produces
    identical telemetry to the warm-worker path.
    """
    job = _JOBS.get(job_id)
    if job is None:
        bq_job = await bigquery_writer.read_job(job_id)
        if bq_job is None:
            return None
        _JOBS[job_id] = bq_job
        _RESULTS[job_id] = await bigquery_writer.read_results(job_id)
        job = bq_job
    results = _RESULTS.get(job_id, [])
    _, _, _, skip_reasons, failure_reasons = _batch_counters.bucket_results(results)
    return {
        **job,
        "results": results,
        "skip_reasons": skip_reasons,
        "failure_reasons": failure_reasons,
    }


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


async def _score_with_semaphore(
    sem: asyncio.Semaphore, job_id: str, index: int, address: str
) -> dict[str, Any]:
    async with sem:
        try:
            row = await _batch_scorer.score_one_address(job_id, index, address)
        except Exception as exc:  # pragma: no cover — defensive
            row = {
                "job_id": job_id,
                "result_index": index,
                "input_address": address,
                "scored_status": "api_failure",
                "error_message": (str(exc) or repr(exc))[:500],
            }
    _RESULTS.setdefault(job_id, []).append(row)
    try:
        await bigquery_writer.write_result(row)
    except Exception as exc:  # pragma: no cover
        # BQ write failure must not poison the batch — log via the in-memory
        # job and continue. Operator alerting goes through Cloud Monitoring.
        _JOBS[job_id].setdefault("bq_errors", []).append(str(exc)[:300])
    return row


async def process_batch(
    job_id: str, addresses: list[str], installer_id: str | None = None
) -> None:
    """Run the whole batch concurrently. Updates _JOBS as it progresses."""
    started = _now()
    _JOBS[job_id] = {
        "job_id": job_id,
        "installer_id": installer_id,
        "address_count": len(addresses),
        "status": "processing",
        "completed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "created_at": started.isoformat(),
        "started_at": started.isoformat(),
    }
    try:
        await bigquery_writer.create_job(
            job_id, installer_id, len(addresses), addresses[0] if addresses else ""
        )
    except Exception as exc:  # pragma: no cover — BQ outage is non-fatal here
        _JOBS[job_id].setdefault("bq_errors", []).append(str(exc)[:300])

    sem = asyncio.Semaphore(SOLAR_CONCURRENCY)
    tasks = [_score_with_semaphore(sem, job_id, i, a) for i, a in enumerate(addresses)]
    rows = await asyncio.gather(*tasks, return_exceptions=False)

    completed, skipped, failed, _, _ = _batch_counters.bucket_results(rows)
    finished = _now()
    _JOBS[job_id].update(
        status="complete",
        completed_count=completed,
        skipped_count=skipped,
        failed_count=failed,
        completed_at=finished.isoformat(),
    )
    try:
        await bigquery_writer.update_job(
            job_id,
            status="complete",
            completed_count=completed,
            skipped_count=skipped,
            failed_count=failed,
            started_at=started,
            completed_at=finished,
        )
    except Exception as exc:  # pragma: no cover
        _JOBS[job_id].setdefault("bq_errors", []).append(str(exc)[:300])
