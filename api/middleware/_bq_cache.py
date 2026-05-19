"""BigQuery cold-tier cache backing api.middleware.ttl_cache.

Table: leadlens.api_cache. Reads serve when Redis is down or missing;
writes are dual-targeted from ttl_cache so the persistent record always
catches up. MERGE-based upsert so duplicate keys don't trip the
streaming-buffer DML quirk (same lesson as bigquery_writer's batch_jobs
INSERT-instead-of-streaming fix).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from typing import Any

from google.cloud import bigquery

from api.config import get_settings

_PROJECT = "sky-eye-496604"
_LOCATION = "us-west1"
_TABLE = f"{_PROJECT}.leadlens.api_cache"


def _client() -> bigquery.Client:
    project = get_settings().google_cloud_project or _PROJECT
    return bigquery.Client(project=project, location=_LOCATION)


def _ensure_table_sync() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{_TABLE}` (
      cache_key STRING NOT NULL,
      service   STRING NOT NULL,
      value_json STRING NOT NULL,
      expires_at TIMESTAMP,
      created_at TIMESTAMP NOT NULL
    )
    """
    _client().query(sql).result()


def _get_sync(cache_key: str) -> dict[str, Any] | None:
    sql = (
        f"SELECT value_json, expires_at FROM `{_TABLE}` "
        "WHERE cache_key = @k "
        "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP()) "
        "LIMIT 1"
    )
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("k", "STRING", cache_key)]
    )
    row = next(iter(_client().query(sql, job_config=cfg).result()), None)
    if row is None:
        return None
    return json.loads(row["value_json"])


def _set_sync(
    cache_key: str, service: str, value: dict[str, Any], expires_at: dt.datetime | None
) -> None:
    sql = f"""
    MERGE `{_TABLE}` T
    USING (SELECT @k AS cache_key) S
    ON T.cache_key = S.cache_key
    WHEN MATCHED THEN
      UPDATE SET value_json = @v, expires_at = @exp, service = @svc
    WHEN NOT MATCHED THEN
      INSERT (cache_key, service, value_json, expires_at, created_at)
      VALUES (@k, @svc, @v, @exp, CURRENT_TIMESTAMP())
    """
    cfg = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("k", "STRING", cache_key),
            bigquery.ScalarQueryParameter("svc", "STRING", service),
            bigquery.ScalarQueryParameter("v", "STRING", json.dumps(value)),
            bigquery.ScalarQueryParameter("exp", "TIMESTAMP", expires_at),
        ]
    )
    _client().query(sql, job_config=cfg).result()


async def ensure_table() -> None:
    await asyncio.to_thread(_ensure_table_sync)


async def get(cache_key: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_get_sync, cache_key)


async def set(
    cache_key: str, service: str, value: dict[str, Any], expires_at: dt.datetime | None
) -> None:
    await asyncio.to_thread(_set_sync, cache_key, service, value, expires_at)
