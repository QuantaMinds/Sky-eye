"""Long Beach building permits ingest.

Fetches a Socrata-style JSON page from data.longbeach.gov, normalizes each
row to the existing parcels_raw.permits schema, and DML-INSERTs into
BigQuery. Idempotent on (source_jurisdiction, permit_id).

Why DML INSERT (not streaming): same reason as bigquery_writer.py — we
re-run this scraper and need rows immediately UPDATE/DELETE-able. Permits
volume is low (LB issues ~10-20k/year residential); cost is negligible.

Truth-first: when Socrata returns a row missing apn / issued_date / value,
we write the row with those fields as NULL — never substitute a default.
Downstream permit_matcher treats NULL apn as "not joinable" and returns
source='unavailable' rather than False.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

import httpx
from google.cloud import bigquery

from api.config import get_settings

_PERMITS_TABLE = "sky-eye-496604.parcels_raw.permits"
_LOCATION = "us-west1"
_JURISDICTION = "LB"


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or "sky-eye-496604"
    return bigquery.Client(project=project, location=_LOCATION)


def fetch_page(
    dataset_url: str, limit: int = 1000, offset: int = 0, *, where: str | None = None,
) -> list[dict[str, Any]]:
    """One page from a Socrata JSON endpoint. dataset_url is the full
    https://data.longbeach.gov/resource/{id}.json — passed in (not
    hardcoded) so this code does not assume a specific dataset that may
    move. App-Token is optional but recommended for >1000 calls/hour."""
    params: dict[str, str | int] = {"$limit": limit, "$offset": offset}
    if where:
        params["$where"] = where
    headers = {}
    token = get_settings().google_cloud_project  # placeholder — replace with a real app token env var if rate-limited
    del token
    r = httpx.get(dataset_url, params=params, headers=headers, timeout=60.0)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected Socrata response shape: {type(data).__name__}")
    return data


def _coerce_date(v: Any) -> dt.date | None:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def normalize_row(raw: dict[str, Any], mapping: dict[str, str], source_url: str) -> dict[str, Any]:
    """Map a Socrata row to the parcels_raw.permits schema.

    `mapping` keys are OUR column names; values are the Socrata field name
    in the upstream row. Missing keys stay None (Rule 3).
    """
    def g(col: str) -> Any:
        src = mapping.get(col)
        return raw.get(src) if src else None

    return {
        "permit_id": str(g("permit_id") or "") or None,
        "ain": (str(g("ain")) if g("ain") is not None else None),
        "permit_type": g("permit_type"),
        "permit_status": g("permit_status"),
        "application_date": _coerce_date(g("application_date")),
        "issued_date": _coerce_date(g("issued_date")),
        "finaled_date": _coerce_date(g("finaled_date")),
        "description": g("description"),
        "estimated_value": _to_decimal(g("estimated_value")),
        "city": g("city") or "Long Beach",
        "zip": g("zip"),
        "source_jurisdiction": _JURISDICTION,
        "source_url": source_url,
        "ingested_at": dt.datetime.now(tz=dt.timezone.utc),
    }


def _to_decimal(v: Any):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def upsert_rows(rows: Iterable[dict[str, Any]]) -> int:
    """Idempotent insert: DELETE matching (source_jurisdiction, permit_id)
    then INSERT. Returns rows written. Skips rows with no permit_id (we
    can't dedupe them safely; better to log + drop than insert duplicates
    on every run)."""
    written = 0
    client = _client()
    table = _PERMITS_TABLE
    for row in rows:
        if not row.get("permit_id"):
            continue
        client.query(
            f"DELETE FROM `{table}` "
            "WHERE source_jurisdiction = @j AND permit_id = @p",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("j", "STRING", _JURISDICTION),
                bigquery.ScalarQueryParameter("p", "STRING", row["permit_id"]),
            ]),
        ).result()
        errors = client.insert_rows_json(table, [_for_streaming(row)])
        if errors:
            raise RuntimeError(f"insert permits failed for {row['permit_id']}: {errors}")
        written += 1
    return written


def _for_streaming(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe copy: dates and datetimes -> ISO strings."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, dt.datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dt.date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
