"""POST /api/v1/batch-score + GET /api/v1/batch-score/{job_id}.

POST accepts up to 500 addresses, kicks off a background asyncio task, and
returns a job_id immediately. The task scores each address concurrently
(capped by batch_processor.SOLAR_CONCURRENCY) and streams rows to
leadlens.batch_results in BigQuery.

GET returns the in-memory job snapshot (low latency, kept in the same
worker process). 404 when the worker doesn't know the job — clients should
treat that as "ask BigQuery directly" for cross-worker durability.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response

from api.models.batch import BatchAcceptResponse, BatchRequest, BatchStatusResponse
from api.services import _batch_csv, batch_processor

router = APIRouter(prefix="/api/v1", tags=["batch-score"])


@router.post(
    "/batch-score",
    response_model=BatchAcceptResponse,
    status_code=202,
)
async def submit_batch(
    req: BatchRequest, background: BackgroundTasks
) -> BatchAcceptResponse:
    job_id = str(uuid.uuid4())
    background.add_task(
        _run_batch, job_id, list(req.addresses), req.installer_id
    )
    return BatchAcceptResponse(
        job_id=job_id, status="queued", address_count=len(req.addresses)
    )


async def _run_batch(
    job_id: str, addresses: list[str], installer_id: str | None
) -> None:
    """Background entry point — wraps process_batch so exceptions don't
    bubble into FastAPI's BackgroundTasks logger as unhandled errors."""
    try:
        await batch_processor.process_batch(job_id, addresses, installer_id)
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover — defensive
        # process_batch already records bq_errors on the job; nothing to do here.
        pass


@router.get("/batch-score/{job_id}", response_model=BatchStatusResponse)
async def get_batch_status(job_id: str) -> BatchStatusResponse:
    snap = await batch_processor.get_job(job_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not known")
    return BatchStatusResponse(
        job_id=snap["job_id"],
        status=snap.get("status", "unknown"),
        address_count=snap.get("address_count", 0),
        completed_count=snap.get("completed_count", 0),
        skipped_count=snap.get("skipped_count") or 0,  # legacy rows may have NULL
        failed_count=snap.get("failed_count", 0),
        skip_reasons=snap.get("skip_reasons") or None,
        failure_reasons=snap.get("failure_reasons") or None,
        results=snap.get("results", []),
    )


@router.get("/batch-score/{job_id}/export")
async def export_batch_csv(job_id: str, format: str = "csv") -> Response:
    """Download scored rows as a sorted CSV. Only 'csv' is supported today.

    Reads from the same job snapshot as the status endpoint so the CSV
    matches what the UI is showing exactly — no second pipeline, no risk
    of the export disagreeing with the dashboard.
    """
    if format != "csv":
        raise HTTPException(status_code=400, detail=f"unsupported format: {format}")
    snap = await batch_processor.get_job(job_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not known")
    body = _batch_csv.build_csv(snap.get("results", []))
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="leadlens-batch-{job_id[:8]}.csv"'
            ),
        },
    )
