"""Phase 1.5c.2 probe: identify the per-AIN data endpoint behind the public
Assessor portal. Decides whether a scraper can hit a clean REST endpoint
(httpx, fast, light) or requires a JS-renderer (Playwright, heavy)."""
from __future__ import annotations

import re

import httpx

AIN = "5191014012"  # Boyle Heights DAC SFR fixture
URL = f"https://portal.assessor.lacounty.gov/parceldetail/{AIN}"

API_HINT = re.compile(r"(https?://[^\"'\s]+(?:api|service|rest|assessor|arcgis)[^\"'\s]*)", re.I)
SCRIPT_SRC = re.compile(r'<script[^>]*src="([^"]+)"', re.I)
CONFIG_HINT = re.compile(r'(api[_-]?(?:base|url|root)|service[_-]?url)\s*[:=]\s*["\']([^"\']+)["\']', re.I)


def probe() -> int:
    r = httpx.get(URL, timeout=20, follow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    print(f"GET {URL}")
    print(f"  status:       {r.status_code}")
    print(f"  bytes:        {len(r.text):,}")
    print(f"  content-type: {r.headers.get('content-type')}")
    print(f"  server:       {r.headers.get('server', '?')}")
    print(f"  redirected:   {r.url}")

    apis = sorted({h for h in API_HINT.findall(r.text)})
    scripts = SCRIPT_SRC.findall(r.text)
    configs = CONFIG_HINT.findall(r.text)

    print(f"\n  API/REST/arcgis URLs in page ({len(apis)}):")
    for u in apis[:20]:
        print(f"    {u[:140]}")
    print(f"\n  <script src=> tags ({len(scripts)}):")
    for s in scripts[:10]:
        print(f"    {s[:140]}")
    print(f"\n  inline config hints ({len(configs)}):")
    for k, v in configs[:10]:
        print(f"    {k} = {v[:140]}")

    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(probe())
