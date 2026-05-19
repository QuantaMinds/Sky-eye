"""Forensic audit of Phase 4 — what tests don't catch.

Goals (CLAUDE.md Rule 4):
  - Verify each spec rate-limit value is actually applied
  - Verify TTL policy matches spec
  - Drive a Redis-down + BQ-down scenario and confirm clean failure
  - Confirm matched-pair on rate limiter (fires + doesn't over-fire)
  - Check headroom math against actual call counts
  - Verify hit_rate distinguishes None (no traffic) from 0.0 (all misses)
  - Detect attribution drift: rate-limit list vs TTL list (both should
    list the spec's services)
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows default cp1252 chokes silently on em-dash in case titles — force UTF-8
# so the audit prints every detail line. Affects script stdout only.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from api.middleware import _cache_metrics, rate_limiter, ttl_cache  # noqa: E402
from api.middleware._limiter_primitives import (  # noqa: E402
    ConcurrencyLimiter,
    SlidingWindowLimiter,
    TokenCounter,
)


def hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _reset() -> None:
    from fakeredis import aioredis as fr
    ttl_cache._set_redis_client_for_tests(fr.FakeRedis(decode_responses=True))
    _cache_metrics._reset_for_tests()


async def audit_spec_config() -> list[str]:
    hr("CASE: spec config audit — rate limits + TTLs")
    findings: list[str] = []

    expected_rpm = {"solar": 100, "geocoding": 50, "gemini": 60, "census": 500}
    expected_concurrent = {"solar": 10}
    expected_ttl = {
        "solar": 30 * 86400, "geocoding": 30 * 86400,
        "census": 365 * 86400, "nrel": 90 * 86400, "gemini": None,
    }

    for svc, expected in expected_rpm.items():
        w = rate_limiter.registry.window(svc)
        if w is None:
            findings.append(f"FAIL: {svc} has no rpm limiter")
            continue
        if w.max_calls != expected:
            findings.append(f"FAIL: {svc} rpm={w.max_calls}, expected {expected}")
        print(f"  {svc}: rpm={w.max_calls} (spec {expected}) — {'OK' if w.max_calls == expected else 'FAIL'}")

    for svc, expected in expected_concurrent.items():
        c = rate_limiter.registry.concurrency(svc)
        if c is None:
            findings.append(f"FAIL: {svc} has no concurrency cap")
        elif c.max_concurrent != expected:
            findings.append(f"FAIL: {svc} concurrent={c.max_concurrent}, expected {expected}")
        else:
            print(f"  {svc}: concurrent={c.max_concurrent} (spec {expected}) — OK")

    for svc, expected in expected_ttl.items():
        actual = ttl_cache.TTL_SECONDS.get(svc, "MISSING")
        match = actual == expected
        print(f"  {svc}: ttl={actual} (spec {expected}) — {'OK' if match else 'FAIL'}")
        if not match:
            findings.append(f"FAIL: {svc} TTL={actual}, expected {expected}")

    if rate_limiter.registry.tokens("gemini") is None:
        findings.append("FAIL: gemini has no token counter — spec requires input/output tracking")
    else:
        print("  gemini: token counter present — OK")

    return findings


async def audit_matched_pair_rate_limiter() -> list[str]:
    hr("CASE: matched-pair limiter gate — fires + doesn't over-fire")
    findings: list[str] = []

    # Fires: 4th call inside the window must wait.
    lim = SlidingWindowLimiter(3, 0.2)
    for _ in range(3):
        await lim.acquire()
    t0 = time.monotonic()
    await lim.acquire()
    waited = time.monotonic() - t0
    print(f"  gate FIRES: 4th call waited {waited*1000:.0f} ms (expected >=150)")
    if waited < 0.15:
        findings.append(f"FAIL: 4th call did not wait — gate not firing ({waited:.3f}s)")

    # Doesn't over-fire: well under the limit, no wait.
    lim2 = SlidingWindowLimiter(100, 0.2)
    t0 = time.monotonic()
    for _ in range(5):
        await lim2.acquire()
    elapsed = time.monotonic() - t0
    print(f"  gate DOESN'T OVER-FIRE: 5/100 calls took {elapsed*1000:.1f} ms (expected <10)")
    if elapsed > 0.01:
        findings.append(f"FAIL: limiter blocked under-budget calls ({elapsed:.3f}s)")

    return findings


async def audit_redis_AND_bq_down() -> list[str]:
    hr("CASE: Redis AND BQ both down — must surface miss, not crash")
    _reset()
    findings: list[str] = []

    class _BoomRedis:
        async def get(self, *a, **kw): raise RuntimeError("redis down")
        async def set(self, *a, **kw): raise RuntimeError("redis down")
    ttl_cache._set_redis_client_for_tests(_BoomRedis())

    with patch("api.middleware._bq_cache.get",
               new=AsyncMock(side_effect=RuntimeError("bq down"))), \
         patch("api.middleware._bq_cache.set",
               new=AsyncMock(side_effect=RuntimeError("bq down"))):
        try:
            value = await ttl_cache.get("solar", "any-key")
            await ttl_cache.set("solar", "any-key", {"v": 1})
        except Exception as exc:
            findings.append(f"FAIL: ttl_cache crashed when both tiers down: {exc!r}")
            return findings

    print(f"  both-tiers-down read returned: {value!r}")
    if value is not None:
        findings.append(f"FAIL: ttl_cache.get returned non-None when both tiers down")
    rate = ttl_cache.bq_success_rate()
    print(f"  bq_success_rate after failed write: {rate}")
    if rate != 0.0:
        findings.append(f"FAIL: bq_success_rate {rate} should be 0.0 after a failed write")
    return findings


async def audit_hit_rate_none_vs_zero() -> list[str]:
    hr("CASE: hit_rate distinguishes None (no traffic) from 0.0 (all miss)")
    _reset()
    findings: list[str] = []

    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)):
        rates_before = ttl_cache.hit_rates()
        print(f"  hit_rate before any traffic: {rates_before}")
        if "geocoding" in rates_before:
            findings.append("FAIL: hit_rates() lists services with no traffic")

        await ttl_cache.get("geocoding", "miss-1")
        await ttl_cache.get("geocoding", "miss-2")
        rates_after_misses = ttl_cache.hit_rates()
        print(f"  hit_rate after 2 misses, 0 hits: {rates_after_misses}")
        if rates_after_misses.get("geocoding") != 0.0:
            findings.append(f"FAIL: all-miss hit_rate {rates_after_misses.get('geocoding')} should be 0.0")
        if "solar" in rates_after_misses:
            findings.append("FAIL: untouched 'solar' bucket appeared after geocoding traffic only")
    return findings


async def audit_concurrency_cap_real_traffic() -> list[str]:
    hr("CASE: concurrency cap holds under heavy contention")
    findings: list[str] = []
    sem = ConcurrencyLimiter(max_concurrent=10, name="audit")
    peak = [0]
    async def _one():
        async with sem:
            peak[0] = max(peak[0], sem.in_flight)
            await asyncio.sleep(0.02)
    await asyncio.gather(*[_one() for _ in range(60)])
    print(f"  60 tasks, max in-flight observed: {peak[0]} (cap 10)")
    if peak[0] > 10:
        findings.append(f"FAIL: in-flight {peak[0]} exceeded cap 10")
    return findings


async def audit_token_counter() -> list[str]:
    hr("CASE: token counter rolling-window math")
    findings: list[str] = []
    tc = TokenCounter(window_seconds=0.2)
    tc.record(input_tokens=100, output_tokens=50)
    tc.record(input_tokens=200, output_tokens=80)
    u = tc.usage()
    print(f"  immediate usage: {u}")
    if u["input_tokens_last_window"] != 300 or u["output_tokens_last_window"] != 130:
        findings.append(f"FAIL: token sums wrong: {u}")
    await asyncio.sleep(0.25)
    u2 = tc.usage()
    print(f"  usage after window expiry: {u2}")
    if u2["input_tokens_last_window"] != 0:
        findings.append(f"FAIL: tokens didn't evict: {u2}")
    return findings


async def main() -> None:
    hr("PHASE 4 FORENSIC AUDIT")
    all_findings: list[str] = []
    for fn in (
        audit_spec_config,
        audit_matched_pair_rate_limiter,
        audit_redis_AND_bq_down,
        audit_hit_rate_none_vs_zero,
        audit_concurrency_cap_real_traffic,
        audit_token_counter,
    ):
        all_findings.extend(await fn())

    hr("SUMMARY")
    if not all_findings:
        print("  OK   0 findings.")
    else:
        for f in all_findings:
            print(f"  {f}")
    print(f"\n  TOTAL FINDINGS: {len(all_findings)}")


if __name__ == "__main__":
    asyncio.run(main())
