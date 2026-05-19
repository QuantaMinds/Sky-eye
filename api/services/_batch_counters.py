"""Status-counting helper for batch_processor.

Pure function — extracted so batch_processor stays under the 100-LOC budget
(CLAUDE.md Rule 1) and so the bucketing rule lives in one auditable place.

scored_status taxonomy for job-level counters:
  - "scored" is the implicit completed_count bucket.
  - SKIPPED_STATUSES: intentional policy exclusions. Tony's dashboard
    renders these as "excluded (different product category)", NOT failures.
  - FAILED_STATUSES: true infrastructure exceptions. Retryable.
  - Anything else falls through to failed_count — never to completed_count.
    This is the test_unknown_status_does_not_inflate_completed contract.
"""
from __future__ import annotations

from typing import Any

SKIPPED_STATUSES: frozenset[str] = frozenset({"multi_unit_skipped"})
FAILED_STATUSES: frozenset[str] = frozenset({"api_failure"})


def bucket_results(
    rows: list[dict[str, Any]],
) -> tuple[int, int, int, dict[str, int], dict[str, int]]:
    """Tally rows into (completed, skipped, failed, skip_reasons, failure_reasons).

    Reasons dicts are keyed by the raw scored_status string — no hardcoded
    enums. When new skip/failure statuses land, they appear automatically
    without code changes here.
    """
    completed = skipped = failed = 0
    skip_reasons: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    for r in rows:
        status = r.get("scored_status")
        if status == "scored":
            completed += 1
        elif status in SKIPPED_STATUSES:
            skipped += 1
            skip_reasons[status] = skip_reasons.get(status, 0) + 1
        else:
            failed += 1
            key = status if status else "unknown"
            failure_reasons[key] = failure_reasons.get(key, 0) + 1
    return completed, skipped, failed, skip_reasons, failure_reasons
