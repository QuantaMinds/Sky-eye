"""Tri-state permit match: True / False / None (unavailable).

The None case is the load-bearing one. If we haven't ingested LB permits
for the date window in question, EVERY parcel trivially has "no permit" —
and the confidence pipeline would treat every detected change as
unpermitted. That's the classic Edison-Theatre failure: a pipeline that
runs and returns confident-looking output built on a fake foundation
(CLAUDE.md Rule 3).

Coverage gate: before returning False, we verify the permits table has
at least one row matching (source_jurisdiction='LB', issued_date in
window). If it doesn't, has_permit returns None and the downstream
confidence pipeline drops + re-normalizes the permit gate instead of
penalizing the parcel for an absent dataset.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from google.cloud import bigquery

from api.config import get_settings

_TABLE = "sky-eye-496604.parcels_raw.permits"
_LOCATION = "us-west1"
_JURISDICTION = "LB"

# Coverage decision is per-process. Re-check by deleting the entry from
# the dict (testing) or restarting the worker (production roll-forward).
_coverage_cache: dict[tuple[str, str], bool] = {}


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or "sky-eye-496604"
    return bigquery.Client(project=project, location=_LOCATION)


def _coverage_key(start: dt.date, end: dt.date) -> tuple[str, str]:
    return (start.isoformat(), end.isoformat())


def has_coverage(window_start: dt.date, window_end: dt.date) -> bool:
    """Does the permits table have ANY LB rows in this window? Returns
    False when the dataset is empty for the period (so callers route to
    source='unavailable' rather than a fake 'no permit found')."""
    key = _coverage_key(window_start, window_end)
    if key in _coverage_cache:
        return _coverage_cache[key]
    sql = (
        f"SELECT COUNT(*) AS n FROM `{_TABLE}` "
        "WHERE source_jurisdiction = @j "
        "AND issued_date BETWEEN @s AND @e"
    )
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("j", "STRING", _JURISDICTION),
        bigquery.ScalarQueryParameter("s", "DATE", window_start),
        bigquery.ScalarQueryParameter("e", "DATE", window_end),
    ])
    row = next(iter(_client().query(sql, job_config=cfg).result()), None)
    covered = bool(row and int(row["n"]) > 0)
    _coverage_cache[key] = covered
    return covered


def has_permit(
    apn: str, window_start: dt.date, window_end: dt.date,
) -> Optional[bool]:
    """Tri-state: True (permit found), False (no permit found in a
    covered window), None (coverage is missing — answer unknown)."""
    if not apn:
        return None
    if not has_coverage(window_start, window_end):
        return None
    sql = (
        f"SELECT COUNT(*) AS n FROM `{_TABLE}` "
        "WHERE source_jurisdiction = @j "
        "AND ain = @apn "
        "AND issued_date BETWEEN @s AND @e"
    )
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("j", "STRING", _JURISDICTION),
        bigquery.ScalarQueryParameter("apn", "STRING", apn),
        bigquery.ScalarQueryParameter("s", "DATE", window_start),
        bigquery.ScalarQueryParameter("e", "DATE", window_end),
    ])
    row = next(iter(_client().query(sql, job_config=cfg).result()), None)
    return bool(row and int(row["n"]) > 0)


def _reset_coverage_cache_for_tests() -> None:
    _coverage_cache.clear()
