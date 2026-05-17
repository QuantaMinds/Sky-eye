"""Phase 1.5d spot-check — 5 utility-classification cases.

Validates the SCE / LADWP / unknown polygon routing without re-verifying the
27-record Phase 1.5c fixture. Full fixture re-verification is deferred to
Phase 1.5d follow-up (see project-phase15-backlog).

Five cases cover:
  1. Edison Theatre, Long Beach     -> SCE (LB is SCE territory)
  2. LA City Hall                   -> LADWP (LA City proper)
  3. Burbank City Hall              -> unknown (Burbank Water & Power, neither SCE nor LADWP)
  4. Belmont Shore SFR (LB)         -> SCE (LB residential)
  5. Wilmington (LA harbor area)    -> LADWP (LA City annex, near SCE/LADWP boundary)

Exit 0 if all 5 produce expected utility; non-zero otherwise.
"""
from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from api.services import utility  # noqa: E402

CASES = [
    # (label, lat, lng, expected_utility)
    ("Edison Theatre, Long Beach",          33.7683013, -118.1887403, "SCE"),
    ("LA City Hall (downtown)",             34.0537,    -118.2428,    "LADWP"),
    ("Burbank City Hall",                   34.1834,    -118.3084,    "unknown"),
    ("Belmont Shore SFR, Long Beach",       33.7600,    -118.1380,    "SCE"),
    ("Wilmington / LA Harbor (border)",     33.7800,    -118.2650,    "LADWP"),
]


async def main() -> int:
    print(f"Phase 1.5d utility spot-check: {len(CASES)} cases\n")
    failed: list[tuple[str, str, str]] = []
    for label, lat, lng, expected in CASES:
        util, _ = await utility.lookup_by_point(lat, lng)
        ok = util.utility_name == expected
        marker = "PASS" if ok else "FAIL"
        print(f"  {marker}  {label[:38]:<38}  expected={expected:<8} got={util.utility_name:<8} "
              f"rate=${util.representative_rate:.2f}/kWh  conf={util.confidence_level}")
        if not ok:
            failed.append((label, expected, util.utility_name))

    print()
    if failed:
        print(f"  {len(failed)} of {len(CASES)} FAILED:")
        for label, exp, got in failed:
            print(f"    - {label}: expected {exp!r}, got {got!r}")
        return 1
    print(f"  ALL {len(CASES)} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
