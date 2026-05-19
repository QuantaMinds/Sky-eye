"""Pydantic models for the batch scoring endpoint.

Max 500 addresses per request — enforced at the model layer so FastAPI
returns 422 with a clear field error before any handler code runs.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl

MAX_BATCH = 500


class BatchRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=MAX_BATCH)
    installer_id: str | None = Field(default=None, max_length=128)
    callback_url: HttpUrl | None = Field(default=None)


class BatchAcceptResponse(BaseModel):
    job_id: str
    status: str
    address_count: int


class BatchStatusResponse(BaseModel):
    """Job-level status payload returned by GET /batch-score/{job_id}.

    Counter invariant when status == 'complete':
      address_count == completed_count + skipped_count + failed_count

    - completed_count: rows that scored end-to-end (scored_status='scored').
      Semantics preserved from the pre-split contract — no rename.
    - skipped_count:   rows intentionally excluded by policy. Currently sourced
      1:1 from 'multi_unit_skipped'; expands automatically as new skip
      statuses land (e.g. a future explicit out-of-county filter).
    - failed_count:    true infrastructure exceptions (e.g. 'api_failure').
      The pre-split contract conflated skipped + failed into one bucket;
      the dashboard now renders them distinctly.

    skip_reasons / failure_reasons: dict[str, int] keyed by raw scored_status
    string. No hardcoded enum — buckets only appear when at least one row
    produced them. Tony's dashboard renders these as a cohort breakdown
    under the headline counters, e.g. "55 multi-unit excluded; 7 transient
    API errors."
    """

    job_id: str
    status: str  # 'queued' | 'processing' | 'complete' | 'unknown'
    address_count: int
    completed_count: int
    skipped_count: int = 0
    failed_count: int
    skip_reasons: dict[str, int] | None = None
    failure_reasons: dict[str, int] | None = None
    results: list[dict[str, Any]]
