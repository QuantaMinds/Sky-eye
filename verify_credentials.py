"""Phase 0 credential verification.

Runs 6 connectivity checks for the external services EYE-Lead depends on.
Each check prints PASS/FAIL with elapsed time. Exits 0 iff all pass.

Required env vars (see .env.example):
    GEMINI_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_APPLICATION_CREDENTIALS,
    GOOGLE_SOLAR_API_KEY, NREL_API_KEY
Optional: EARTH_ENGINE_PROJECT, CENSUS_API_KEY, GEMINI_MODEL
"""
from __future__ import annotations

import os
import sys
import time
from typing import Callable

import httpx
from dotenv import load_dotenv

load_dotenv()

CheckResult = tuple[bool, float, str]
CheckFn = Callable[[], CheckResult]


def _timed(fn: Callable[[], str]) -> CheckResult:
    start = time.perf_counter()
    try:
        message = fn()
        return True, time.perf_counter() - start, message
    except Exception as exc:
        return False, time.perf_counter() - start, f"{type(exc).__name__}: {exc}"


def check_gemini() -> CheckResult:
    """Vertex AI / Gemini 2.5 Flash via the unified google-genai SDK.
    Auth via Application Default Credentials. Billed to GOOGLE_CLOUD_PROJECT.
    """
    def run() -> str:
        from google import genai
        from google.genai import types

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT not set")
        location = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

        client = genai.Client(vertexai=True, project=project, location=location)
        resp = client.models.generate_content(
            model=model_name,
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=1, temperature=0.0),
        )
        return f"model={model_name} project={project} chars={len(resp.text or '')}"

    return _timed(run)


def check_bigquery() -> CheckResult:
    def run() -> str:
        from google.cloud import bigquery

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT not set")
        client = bigquery.Client(project=project)
        datasets = list(client.list_datasets(max_results=10))
        return f"project={project} datasets_listed={len(datasets)}"

    return _timed(run)


def check_earth_engine() -> CheckResult:
    def run() -> str:
        import ee

        project = (
            os.environ.get("EARTH_ENGINE_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
        # Round-trip a trivial server call to confirm the session works.
        value = ee.Number(1).getInfo()
        return f"project={project or 'default'} echo={value}"

    return _timed(run)


def check_solar_api() -> CheckResult:
    """Apple HQ: 37.3318, -122.0312."""
    def run() -> str:
        api_key = os.environ.get("GOOGLE_SOLAR_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_SOLAR_API_KEY not set")
        params = {
            "location.latitude": 37.3318,
            "location.longitude": -122.0312,
            "requiredQuality": "HIGH",
            "key": api_key,
        }
        r = httpx.get(
            "https://solar.googleapis.com/v1/buildingInsights:findClosest",
            params=params,
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        name = (data.get("name") or "")[:48]
        return f"building={name or '?'}"

    return _timed(run)


def check_census_acs() -> CheckResult:
    """ACS5 2022 block-group query: San Mateo County (state=06, county=081)."""
    def run() -> str:
        api_key = os.environ.get("CENSUS_API_KEY")
        params = {
            "get": "B01001_001E,NAME",
            "for": "block group:1",
            "in": "state:06 county:081 tract:611200",
        }
        if api_key:
            params["key"] = api_key
        r = httpx.get(
            "https://api.census.gov/data/2022/acs/acs5",
            params=params,
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        # Shape: [header_row, *data_rows]
        rows = len(data) - 1
        pop = data[1][0] if rows else "n/a"
        return f"rows={rows} pop={pop}"

    return _timed(run)


def check_nrel_pvwatts() -> CheckResult:
    """PVWatts v8 estimate at Apple HQ."""
    def run() -> str:
        api_key = os.environ.get("NREL_API_KEY")
        if not api_key:
            raise RuntimeError("NREL_API_KEY not set")
        params = {
            "api_key": api_key,
            "lat": 37.3318,
            "lon": -122.0312,
            "system_capacity": 4,
            "module_type": 0,
            "losses": 14,
            "array_type": 1,
            "tilt": 20,
            "azimuth": 180,
        }
        r = httpx.get(
            "https://developer.nrel.gov/api/pvwatts/v8.json",
            params=params,
            timeout=20.0,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"NREL errors: {data['errors']}")
        ac_annual = data.get("outputs", {}).get("ac_annual")
        return f"ac_annual_kwh={ac_annual}"

    return _timed(run)


CHECKS: list[tuple[str, CheckFn]] = [
    ("Gemini Flash", check_gemini),
    ("BigQuery", check_bigquery),
    ("Earth Engine", check_earth_engine),
    ("Google Solar", check_solar_api),
    ("Census ACS", check_census_acs),
    ("NREL PVWatts", check_nrel_pvwatts),
]


def main() -> int:
    print(f"Running {len(CHECKS)} credential checks...\n")
    failures = 0
    for name, fn in CHECKS:
        passed, elapsed, message = fn()
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name:<14} {elapsed * 1000:>7.0f} ms   {message}")
        if not passed:
            failures += 1
    print()
    if failures:
        print(f"{failures}/{len(CHECKS)} checks FAILED")
        return 1
    print(f"All {len(CHECKS)} checks PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
