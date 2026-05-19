"""Unified cache: Redis (hot) -> BigQuery (cold), per-service TTL policy.

Public API:
  - get(service, key)            -> dict | None
  - set(service, key, value)     -> None  (writes to both tiers)
  - hit_rates() / bq_success_rate / headroom -> /health metrics

TTL policy is source of truth here — every caller passes `service` and
the TTL is looked up centrally. Phase 1 callers that hand-rolled their
own `ttl_days=N` are migrated to this module.

Redis: fakeredis in dev/tests, real Memorystore in prod via REDIS_URL.
If Redis is unreachable, reads fall through to BigQuery and writes
still target BigQuery (so the cold tier stays warm even when Redis is
down). See [[feedback-gcs-deferred-until-real-consumer]] — the
two-tier choice traded SQLite for BQ persistence per ship review.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from api.middleware import _bq_cache, _cache_metrics

# Per-service TTL (seconds). None = never expires (we own the artifact).
# Source of truth — Phase 4 spec.
TTL_SECONDS: dict[str, int | None] = {
    "solar":     30 * 86400,
    "geocoding": 30 * 86400,
    "census":    365 * 86400,
    "nrel":      90 * 86400,
    "gemini":    None,
}

# Module-level Redis client. None means "not initialized yet" — we lazy-
# init on first use so importing this module doesn't require Redis to be
# reachable (cleaner test ergonomics).
_redis_client: Any | None = None


def _build_redis_client():
    """Construct the Redis client. REDIS_URL set => real Redis;
    else fakeredis. Failure to import/instantiate falls back to fakeredis
    so tests + dev never see a hard import error."""
    url = os.environ.get("REDIS_URL")
    if url:
        from redis import asyncio as aioredis
        return aioredis.from_url(url, decode_responses=True)
    from fakeredis import aioredis as fr
    return fr.FakeRedis(decode_responses=True)


def _redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = _build_redis_client()
    return _redis_client


# Test-only hook — never call from production code. Swap in a mock that
# raises to exercise the Redis-down branch.
def _set_redis_client_for_tests(client: Any) -> None:
    global _redis_client
    _redis_client = client


def _now() -> float:
    return time.time()


def _envelope(value: dict[str, Any], ttl_seconds: int | None) -> dict[str, Any]:
    exp = None if ttl_seconds is None else int(_now()) + int(ttl_seconds)
    return {"v": value, "exp": exp}


def _unwrap_if_fresh(raw: str | bytes | None) -> dict[str, Any] | None:
    """Decode + freshness-check a cached envelope. Returns None for:
      - missing/absent value
      - corrupt JSON (Redis returned garbage)
      - envelope missing the expected 'v' key
      - envelope past its 'exp' timestamp

    This catches its own decode/key errors by design — promoted from
    accident-of-placement defense (the outer try/except in get() used
    to swallow JSONDecodeError implicitly). Keeping the defense local
    means it survives refactors that narrow the outer scope. See
    [[feedback-explicit-defense-not-accident]].
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        env = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(env, dict):
        return None
    exp = env.get("exp")
    try:
        if exp is not None and float(exp) < _now():
            return None
    except (TypeError, ValueError):
        return None
    return env.get("v")


async def get(service: str, key: str) -> dict[str, Any] | None:
    """Read-through: Redis first, BQ on miss / Redis-down.

    NOTE: No in-flight deduplication. N concurrent reads of the SAME
    cold key will issue N upstream calls (the first finish-er writes
    the cache, but the others are already mid-flight). Acceptable
    today because address collisions within a single batch are rare.
    Activate per-key asyncio.Lock dedup when ANY of the following:
      - batch size routinely exceeds 5,000
      - Solar API cost per batch becomes a budget concern
      - a customer's batch shows >10% duplicate keys
    See [[feedback-explicit-trigger-for-deferred-work]].
    """
    full_key = f"{service}:{key}"

    # Tier 1: Redis hot path
    try:
        raw = await _redis().get(full_key)
        value = _unwrap_if_fresh(raw)
        if value is not None:
            _cache_metrics.cache_hit(service)
            return value
    except Exception:
        # Fall through to BQ — Redis failure must not block reads.
        pass

    # Tier 2: BQ cold path
    try:
        value = await _bq_cache.get(full_key)
    except Exception:
        value = None
    if value is not None:
        _cache_metrics.cache_hit(service)
        # Best-effort backfill of Redis so the next read is hot.
        try:
            ttl = TTL_SECONDS.get(service)
            await _redis().set(
                full_key, json.dumps(_envelope(value, ttl)),
                ex=ttl if ttl else None,
            )
        except Exception:
            pass
        return value

    _cache_metrics.cache_miss(service)
    return None


async def set(
    service: str, key: str, value: dict[str, Any], *, ttl_override: int | None = None
) -> None:
    """Dual-write to Redis + BQ. ttl_override lets a caller use a TTL
    different from the service default (e.g. Solar 7d for 404s)."""
    full_key = f"{service}:{key}"
    ttl = ttl_override if ttl_override is not None else TTL_SECONDS.get(service)
    envelope = _envelope(value, ttl)

    try:
        await _redis().set(full_key, json.dumps(envelope), ex=ttl if ttl else None)
    except Exception:
        pass

    import datetime as dt
    expires_at = (
        None if ttl is None
        else dt.datetime.fromtimestamp(envelope["exp"], tz=dt.timezone.utc)
    )
    try:
        await _bq_cache.set(full_key, service, value, expires_at)
        _cache_metrics.bq_writes.ok()
    except Exception:
        _cache_metrics.bq_writes.fail()


def hit_rates() -> dict[str, float | None]:
    return _cache_metrics.hit_rates()


def bq_success_rate() -> float | None:
    return _cache_metrics.bq_success_rate()
