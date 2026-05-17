"""SQLite-backed key-value cache with TTL.

Used by every external-API wrapper to honor caching limits (Solar API ToS:
30-day max) and avoid duplicate spend during testing. Synchronous SQLite is
fine — a local file lookup is sub-millisecond.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_PATH = Path(".cache.db")
_DEFAULT_TTL_DAYS = 30


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache "
        "(k TEXT PRIMARY KEY, v TEXT NOT NULL, exp INTEGER NOT NULL)"
    )
    return conn


def get(key: str) -> dict[str, Any] | None:
    """Return the cached value, or None if absent/expired."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT v, exp FROM cache WHERE k = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    value, expires_at = row
    if expires_at < int(time.time()):
        delete(key)
        return None
    return json.loads(value)


def set(key: str, value: dict[str, Any], ttl_days: int = _DEFAULT_TTL_DAYS) -> None:
    expires_at = int(time.time()) + ttl_days * 86400
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (k, v, exp) VALUES (?, ?, ?)",
            (key, json.dumps(value), expires_at),
        )


def delete(key: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM cache WHERE k = ?", (key,))


def clear() -> None:
    """Wipe the entire cache. For tests only."""
    with _conn() as conn:
        conn.execute("DELETE FROM cache")
