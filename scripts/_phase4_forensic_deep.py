"""Deep forensic audit of Phase 4 — what really hits storage, what's silent.

Goes beyond _phase4_forensic.py (which audits spec config) by exercising
the full pipeline end-to-end and inspecting actual side effects:

  - Drive solar_api/geocoding/census/nrel/narrative through the cache
    and inspect the Redis keys + BQ write payloads that resulted.
  - Verify the envelope shape (v, exp) is correct, including the
    forever-TTL case for Gemini.
  - Confirm rate-limiter and concurrency cap are actually used by the
    migrated services (not bypassed by some import-path mistake).
  - Confirm token counter is invoked from the narrative pipeline with
    the actual usage_metadata values.
  - Drive Redis-write-failure-after-BQ-hit (silent swallow) and detect
    whether errors are lost.
  - Live-probe BigQuery for the leadlens.api_cache table existence and
    schema. The forensic uploads if absent (mirrors the Phase 3 GCS
    bucket probe).
  - Detect serialization fragility (does model_dump produce
    JSON-serializable values for every cached service?).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass


def hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ----------------------- Test scaffolding --------------------------------

class _Fake200:
    status_code = 200
    is_redirect = False
    def __init__(self, body: dict) -> None: self._body = body
    def raise_for_status(self): pass
    def json(self): return self._body


_SOLAR_BODY = {
    "name": "buildings/forensic-001",
    "solarPotential": {
        "maxArrayPanelsCount": 22,
        "maxSunshineHoursPerYear": 1735.0,
        "solarPanelConfigs": [{"yearlyEnergyDcKwh": 10250.0}],
    },
}
_CENSUS_GEO_BODY = {
    "result": {"geographies": {"2020 Census Blocks": [
        {"STATE": "06", "COUNTY": "037", "TRACT": "207400", "BLKGRP": "1"}
    ]}}
}
_CENSUS_ACS_BODY = [["B19013_001E", "NAME"], ["72500", "Block Group 1"]]
_NREL_BODY = {"errors": [], "outputs": {"ac_annual": 11250.0, "capacity_factor": 0.18, "solrad_annual": 5.3}}
_GEOCODE_BODY = {
    "status": "OK",
    "results": [{
        "geometry": {"location": {"lat": 34.06, "lng": -118.27}},
        "formatted_address": "Forensic, Los Angeles, CA",
    }],
}


class _FakeAsyncClient:
    def __init__(self, *a, **kw): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *e): pass
    async def get(self, url, params=None, **kw):
        if "solar.googleapis.com" in url: return _Fake200(_SOLAR_BODY)
        if "geocoding.geo.census.gov" in url: return _Fake200(_CENSUS_GEO_BODY)
        if "api.census.gov" in url: return _Fake200(_CENSUS_ACS_BODY)
        if "developer.nrel.gov" in url: return _Fake200(_NREL_BODY)
        if "maps.googleapis.com" in url: return _Fake200(_GEOCODE_BODY)
        return _Fake200({})


def _settings_mock():
    m = MagicMock()
    m.google_solar_api_key = "fake-key"
    m.google_cloud_project = "sky-eye-496604"
    m.nrel_api_key = "fake-key"
    m.census_api_key = "fake-key"
    m.vertex_ai_location = "us-central1"
    return m


# ----------------------- Helper: fresh state ------------------------------

def _fresh() -> None:
    """Each case starts with empty fakeredis + reset metrics."""
    from fakeredis import aioredis as fr
    from api.middleware import _cache_metrics, ttl_cache
    ttl_cache._set_redis_client_for_tests(fr.FakeRedis(decode_responses=True))
    _cache_metrics._reset_for_tests()


# ----------------------- CASE 1: end-to-end storage ----------------------

async def case_storage_e2e() -> list[str]:
    hr("CASE 1: end-to-end storage — does a real fetch actually hit Redis + BQ?")
    findings: list[str] = []
    _fresh()
    from api.middleware import ttl_cache
    from api.services import solar_api

    bq_writes: list[tuple] = []
    async def _capture_set(cache_key, service, value, expires_at):
        bq_writes.append((cache_key, service, value, expires_at))
    async def _capture_get(_k): return None

    with patch("api.middleware._bq_cache.set", new=_capture_set), \
         patch("api.middleware._bq_cache.get", new=_capture_get), \
         patch("api.services.solar_api.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.config.get_settings", return_value=_settings_mock()):
        result, cache_hit = await solar_api.get_roof_data(34.05, -118.25, "100 Forensic St")
        print(f"  first call:   panels={result.max_array_panels} kwh={result.max_kwh_year} hit={cache_hit}")
        result2, cache_hit2 = await solar_api.get_roof_data(34.05, -118.25, "100 Forensic St")
        print(f"  second call:  panels={result2.max_array_panels} kwh={result2.max_kwh_year} hit={cache_hit2}")

    redis_client = ttl_cache._redis_client
    keys = await redis_client.keys("*")
    print(f"  redis keys after run: {keys}")

    if not keys:
        findings.append("FAIL: nothing in Redis after a fetch — hot tier not being written")
    elif b"solar:" not in (k if isinstance(k, bytes) else k.encode() for k in keys) and not any(k.startswith("solar:") if isinstance(k, str) else k.startswith(b"solar:") for k in keys):
        findings.append(f"FAIL: no key with 'solar:' prefix; got {keys!r}")

    # Inspect the stored envelope.
    if keys:
        raw = await redis_client.get(keys[0])
        envelope = json.loads(raw)
        print(f"  stored envelope: {envelope}")
        if "v" not in envelope or "exp" not in envelope:
            findings.append(f"FAIL: envelope missing v/exp keys: {envelope}")
        elif envelope["exp"] is None:
            findings.append("FAIL: Solar envelope exp is None (should be 30d from now)")
        else:
            expected_exp = int(time.time()) + 30 * 86400
            drift = abs(envelope["exp"] - expected_exp)
            print(f"  exp drift from expected 30d: {drift}s")
            if drift > 60:
                findings.append(f"FAIL: exp drift {drift}s > 60s tolerance")

    print(f"  BQ writes captured: {len(bq_writes)}")
    for cache_key, service, value, expires_at in bq_writes:
        print(f"    key={cache_key} service={service} expires_at={expires_at}")
        if not cache_key.startswith("solar:"):
            findings.append(f"FAIL: BQ cache_key {cache_key!r} missing 'solar:' prefix")
        if service != "solar":
            findings.append(f"FAIL: BQ service field {service!r} != 'solar'")
        if expires_at is None:
            findings.append("FAIL: BQ expires_at is None for solar (should be ~30d ahead)")

    if cache_hit2 is not True:
        findings.append("FAIL: second call did not register as cache hit")

    return findings


# ----------------------- CASE 2: forever-TTL semantics --------------------

async def case_forever_ttl() -> list[str]:
    hr("CASE 2: Gemini forever-TTL — no exp, no Redis EX, no expires_at")
    findings: list[str] = []
    _fresh()
    from api.middleware import ttl_cache

    bq_writes: list[tuple] = []
    async def _capture_set(*args): bq_writes.append(args)

    with patch("api.middleware._bq_cache.set", new=_capture_set), \
         patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)):
        await ttl_cache.set("gemini", "prompt-hash-abc", {"text": "Test narrative."})

    redis_client = ttl_cache._redis_client
    keys = await redis_client.keys("*")
    print(f"  redis keys: {keys}")
    raw = await redis_client.get(keys[0])
    envelope = json.loads(raw)
    print(f"  envelope: {envelope}")
    if envelope["exp"] is not None:
        findings.append(f"FAIL: gemini envelope exp={envelope['exp']!r}, expected None")

    ttl_remaining = await redis_client.ttl(keys[0])
    print(f"  redis TTL: {ttl_remaining}  (-1 = no expiry; -2 = missing)")
    if ttl_remaining != -1:
        findings.append(f"FAIL: redis TTL for gemini key={ttl_remaining}, expected -1 (no expiry)")

    # BQ side
    _, service, _, expires_at = bq_writes[0]
    print(f"  bq write expires_at={expires_at}")
    if expires_at is not None:
        findings.append(f"FAIL: bq expires_at={expires_at!r} for gemini, expected None")
    return findings


# ----------------------- CASE 3: 7d override TTL --------------------------

async def case_solar_404_override() -> list[str]:
    hr("CASE 3: Solar 404 — 7d override propagates to Redis AND BQ")
    findings: list[str] = []
    _fresh()
    from api.middleware import ttl_cache

    bq_writes: list[tuple] = []
    async def _capture_set(*args): bq_writes.append(args)

    with patch("api.middleware._bq_cache.set", new=_capture_set), \
         patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)):
        await ttl_cache.set("solar", "no-imagery-here", {"empty": True}, ttl_override=7 * 86400)

    redis_client = ttl_cache._redis_client
    keys = await redis_client.keys("*")
    raw = await redis_client.get(keys[0])
    envelope = json.loads(raw)
    print(f"  envelope: {envelope}")
    expected_7d = int(time.time()) + 7 * 86400
    drift = abs(envelope["exp"] - expected_7d)
    print(f"  drift from expected 7d: {drift}s")
    if drift > 60:
        findings.append(f"FAIL: 7d override drift {drift}s > 60s")

    ttl = await redis_client.ttl(keys[0])
    print(f"  redis TTL: {ttl}s (expected ~604800)")
    if abs(ttl - 7 * 86400) > 60:
        findings.append(f"FAIL: redis TTL {ttl} not ~7d")

    _, _, _, expires_at = bq_writes[0]
    print(f"  bq expires_at: {expires_at}")
    if expires_at is None:
        findings.append("FAIL: BQ expires_at is None for 7d override")
    else:
        expected = dt.datetime.fromtimestamp(expected_7d, tz=dt.timezone.utc)
        delta = abs((expires_at - expected).total_seconds())
        if delta > 60:
            findings.append(f"FAIL: BQ expires_at off by {delta}s")
    return findings


# ----------------------- CASE 4: narrative pipeline + token counter ------

async def case_narrative_token_counter() -> list[str]:
    hr("CASE 4: narrative pipeline — token counter invoked with real usage values?")
    findings: list[str] = []
    _fresh()
    from api.middleware import rate_limiter, ttl_cache
    from api.models.lead import DimensionValue, ScoreDimensions
    from api.services import narrative

    fake_call = MagicMock(return_value=("Narrative text response.", 412, 87))
    dims = ScoreDimensions(
        roof_potential=DimensionValue(value=0.8, source="solar_api"),
        income_qualification=DimensionValue(value=0.6, source="acs"),
        ownership=DimensionValue(value=0.9, source="assessor"),
        bill_pain=DimensionValue(value=0.7, source="utility"),
        equity_proxy=DimensionValue(value=0.5, source="assessor"),
        no_existing_solar=DimensionValue(value=None, source="unavailable"),
        intent_signal=DimensionValue(value=None, source="unavailable"),
    )

    tokens_before = rate_limiter.registry.tokens("gemini").usage()
    print(f"  tokens before:    {tokens_before}")

    with patch("api.services.narrative._call_gemini", new=fake_call), \
         patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)):
        text, cached = await narrative.generate_narrative("Test address", 0.74, dims, 0.86)
        print(f"  returned text:    {text!r}  cached={cached}")

    tokens_after = rate_limiter.registry.tokens("gemini").usage()
    print(f"  tokens after:     {tokens_after}")

    if tokens_after["input_tokens_last_window"] != 412:
        findings.append(f"FAIL: input tokens {tokens_after['input_tokens_last_window']} != 412")
    if tokens_after["output_tokens_last_window"] != 87:
        findings.append(f"FAIL: output tokens {tokens_after['output_tokens_last_window']} != 87")

    # Cached on a second call (no Gemini call).
    fake_call.reset_mock()
    with patch("api.services.narrative._call_gemini", new=fake_call), \
         patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)):
        text2, cached2 = await narrative.generate_narrative("Test address", 0.74, dims, 0.86)
        print(f"  second call:      text={text2!r}  cached={cached2}  call_count={fake_call.call_count}")
    if not cached2:
        findings.append("FAIL: second narrative call did not cache-hit")
    if fake_call.called:
        findings.append("FAIL: Gemini was called again despite a cache hit")

    return findings


# ----------------------- CASE 5: serialization fragility -----------------

async def case_serialization_fragility() -> list[str]:
    hr("CASE 5: serialization — does every cached service model JSON-encode cleanly?")
    findings: list[str] = []
    from api.models.lead import (
        CensusData, GeocodingResult, NRELData, SolarRoofData,
    )

    cases = (
        ("solar", SolarRoofData(max_array_panels=20, max_kwh_year=10000.0,
                                max_sunshine_hours=1700.0, building_name="x")),
        ("geocoding", GeocodingResult(lat=34.0, lng=-118.0, formatted_address="X")),
        ("census", CensusData(median_household_income=72500.0, block_group_geoid="0001")),
        ("nrel", NRELData(ac_annual_kwh=11000.0, capacity_factor=0.18, solar_radiation=5.3)),
    )
    for name, model in cases:
        payload = model.model_dump()
        try:
            blob = json.dumps(payload)
            print(f"  {name}: model_dump -> json {len(blob)} bytes  OK")
        except (TypeError, ValueError) as exc:
            findings.append(f"FAIL: {name} model_dump not JSON-serializable: {exc}")
    return findings


# ----------------------- CASE 6: silent-swallow detection ----------------

async def case_silent_swallows() -> list[str]:
    hr("CASE 6: silent swallows — Redis fails mid-write, BQ-only path still records correctly")
    findings: list[str] = []
    _fresh()
    from api.middleware import _cache_metrics, ttl_cache

    class _RedisGetOkSetFails:
        async def get(self, *a, **kw):
            return None  # forces fall-through to BQ path
        async def set(self, *a, **kw):
            raise RuntimeError("redis write outage")
    ttl_cache._set_redis_client_for_tests(_RedisGetOkSetFails())

    bq_set_calls: list[tuple] = []
    async def _capture(*args):
        bq_set_calls.append(args)

    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=_capture):
        await ttl_cache.set("solar", "k-redis-write-fails", {"v": 99})

    print(f"  bq_set_calls captured: {len(bq_set_calls)}")
    if not bq_set_calls:
        findings.append("FAIL: BQ write skipped when Redis raised on set (silent loss)")
    rate = ttl_cache.bq_success_rate()
    print(f"  bq_success_rate: {rate}")
    if rate != 1.0:
        findings.append(f"FAIL: bq_success_rate {rate} != 1.0 — BQ succeeded but counter says otherwise")

    # Now: BQ hit backfills Redis — Redis backfill SET fails. Does the read still succeed?
    bq_value = {"panels": 24}
    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=bq_value)):
        value = await ttl_cache.get("solar", "k-bq-only-hit")
    print(f"  bq-only read (with broken Redis backfill): {value}")
    if value != bq_value:
        findings.append(f"FAIL: BQ-served value lost when Redis backfill SET fails: got {value!r}")
    rates = _cache_metrics.hit_rates()
    print(f"  hit_rates: {rates}")
    if rates.get("solar") is None or rates["solar"] < 0.5:
        findings.append(f"FAIL: BQ-served read not registered as hit: rate={rates.get('solar')}")
    return findings


# ----------------------- CASE 7: envelope corruption ---------------------

async def case_envelope_corruption() -> list[str]:
    hr("CASE 7: envelope corruption — Redis returns non-JSON / malformed envelope")
    findings: list[str] = []
    _fresh()
    from api.middleware import ttl_cache

    class _CorruptRedis:
        async def get(self, *a, **kw): return "this is not json{"
        async def set(self, *a, **kw): pass
    ttl_cache._set_redis_client_for_tests(_CorruptRedis())

    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)):
        try:
            value = await ttl_cache.get("solar", "k-corrupt")
            print(f"  corrupt-envelope read returned: {value!r}")
            if value is not None:
                findings.append(f"FAIL: corrupt envelope returned non-None value: {value!r}")
        except json.JSONDecodeError as exc:
            findings.append(f"FAIL: ttl_cache.get raised JSONDecodeError on corrupt envelope: {exc}")

    # Malformed envelope (valid JSON, missing 'v')
    class _MalformedRedis:
        async def get(self, *a, **kw): return '{"missing":"keys"}'
        async def set(self, *a, **kw): pass
    ttl_cache._set_redis_client_for_tests(_MalformedRedis())
    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)):
        value2 = await ttl_cache.get("solar", "k-malformed")
        print(f"  malformed-envelope read returned: {value2!r}")
    return findings


# ----------------------- CASE 8: live BQ table probe ---------------------

async def case_live_bq_table_probe() -> list[str]:
    hr("CASE 8: live BQ — ensure_table() bootstraps + table reachable after")
    findings: list[str] = []
    import os
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "sky-eye-496604")

    # Step 1: invoke the same code path the FastAPI startup hook runs.
    # CREATE TABLE IF NOT EXISTS is idempotent — re-running is harmless.
    from api.middleware import _bq_cache
    try:
        await _bq_cache.ensure_table()
        print("  ensure_table() returned cleanly")
    except Exception as exc:
        findings.append(f"FAIL: ensure_table() raised: {type(exc).__name__}: {exc}")
        return findings

    # Step 2: verify the table actually exists in BQ after the bootstrap.
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project="sky-eye-496604", location="us-west1")
        table = client.get_table("sky-eye-496604.leadlens.api_cache")
        print(f"  table exists post-bootstrap. schema:")
        for f in table.schema:
            print(f"    {f.name:<12} {f.field_type:<10} {f.mode}")
        expected = {"cache_key", "service", "value_json", "expires_at", "created_at"}
        actual = {f.name for f in table.schema}
        missing = expected - actual
        extra = actual - expected
        if missing:
            findings.append(f"FAIL: api_cache missing columns {missing}")
        if extra:
            print(f"  note: extra columns {extra}")
    except Exception as exc:
        msg = str(exc)[:200]
        print(f"  table NOT reachable after ensure_table: {type(exc).__name__}: {msg}")
        findings.append(f"FAIL: api_cache not reachable post-bootstrap: {msg}")
    return findings


# ----------------------- CASE 9: cache_warmer effectiveness --------------

async def case_cache_warmer() -> list[str]:
    hr("CASE 9: cache_warmer — does it actually populate the cache?")
    findings: list[str] = []
    _fresh()
    from api.middleware import ttl_cache
    from api.services import cache_warmer

    points = [(34.05 + i * 0.01, -118.25, f"{i*10} Warm St") for i in range(3)]
    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)), \
         patch("api.services.solar_api.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.services.census.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.services.nrel.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.services.geocoding.httpx.AsyncClient", _FakeAsyncClient), \
         patch("api.config.get_settings", return_value=_settings_mock()):
        stats = await cache_warmer.warm(points, concurrency=3)
        print(f"  stats: {stats.to_dict()}")

    redis_client = ttl_cache._redis_client
    keys = sorted(await redis_client.keys("*"))
    print(f"  redis keys after warm ({len(keys)}):")
    for k in keys[:8]:
        print(f"    {k}")
    if len(keys) < 9:  # 3 points × 3 services (solar, census, nrel) + 3 geocodes = up to 12, conservative floor
        findings.append(f"FAIL: cache_warmer only produced {len(keys)} keys for 3 points (expected ≥9)")

    if stats.solar_fetched != 3:
        findings.append(f"FAIL: solar_fetched={stats.solar_fetched}, expected 3")
    if stats.failed:
        findings.append(f"FAIL: warmer reported {stats.failed} failures: {stats.errors}")
    return findings


# ----------------------- CASE 10: concurrent rate-limit + cache race ----

async def case_thundering_herd() -> list[str]:
    hr("CASE 10: thundering herd — 20 simultaneous cold-cache requests for same key")
    findings: list[str] = []
    _fresh()
    from api.services import solar_api

    call_counter = [0]
    class _CountingClient(_FakeAsyncClient):
        async def get(self, url, params=None, **kw):
            call_counter[0] += 1
            await asyncio.sleep(0.005)
            return await super().get(url, params, **kw)

    with patch("api.middleware._bq_cache.get", new=AsyncMock(return_value=None)), \
         patch("api.middleware._bq_cache.set", new=AsyncMock(return_value=None)), \
         patch("api.services.solar_api.httpx.AsyncClient", _CountingClient), \
         patch("api.config.get_settings", return_value=_settings_mock()):
        results = await asyncio.gather(*[
            solar_api.get_roof_data(34.05, -118.25, "100 Forensic St")
            for _ in range(20)
        ])

    hits = sum(1 for _, h in results if h)
    misses = 20 - hits
    print(f"  20 simultaneous cold-cache requests for same key:")
    print(f"    actual upstream calls: {call_counter[0]}")
    print(f"    cache_hit=True in results: {hits}")
    print(f"    cache_hit=False in results: {misses}")
    # All 20 see cold cache (no dedup). 20 actual fetches expected.
    if call_counter[0] < 1:
        findings.append("FAIL: no upstream calls — fetch path bypassed")
    # No dedup is acceptable; just want to know how many duplicates we ate.
    print(f"  NOTE: no in-flight dedup in current design — {call_counter[0]} Solar API calls "
          f"were issued for the same key. Not a bug, but a known cost characteristic.")
    return findings


async def main() -> None:
    hr("PHASE 4 DEEP FORENSIC AUDIT")
    cases = [
        case_storage_e2e,
        case_forever_ttl,
        case_solar_404_override,
        case_narrative_token_counter,
        case_serialization_fragility,
        case_silent_swallows,
        case_envelope_corruption,
        case_live_bq_table_probe,
        case_cache_warmer,
        case_thundering_herd,
    ]
    summary: list[tuple[str, list[str]]] = []
    for c in cases:
        try:
            findings = await c()
        except Exception as exc:
            findings = [f"FAIL (uncaught): {type(exc).__name__}: {exc}"]
        summary.append((c.__name__, findings))

    hr("SUMMARY")
    total = 0
    for name, findings in summary:
        total += len(findings)
        flag = "OK " if not findings else f"FAIL({len(findings)})"
        print(f"  {flag}  {name}")
        for f in findings:
            print(f"      {f}")
    print(f"\n  TOTAL FINDINGS: {total}")


if __name__ == "__main__":
    asyncio.run(main())
