"""Phase 1.5c.2a Amendment 2 — split-parity spot check.

Calls every dimension builder with hand-crafted, deterministic inputs and
dumps a JSON snapshot of every DimensionValue output. Run BEFORE the
_dimension_builders.py -> api/services/dimensions/*.py split, save snapshot
to snapshots/split_parity_before.json. Run AFTER the split. Diff. The two
snapshots MUST be byte-identical — the split is purely structural; any
divergence is a silent regression.

Why direct dim-builder calls instead of full scoring path:
  - Eliminates external API latency / non-determinism
  - Exercises exactly the surface the split can break (imports + wiring)
  - 5 scenarios x 5 dimensions = 25 DimensionValue outputs to compare

Usage:
  python tests/check_split_parity.py snapshots/split_parity_before.json
  # ... do the split ...
  python tests/check_split_parity.py snapshots/split_parity_after.json
  python tests/check_split_parity.py --diff
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Import target switches with the split — use the public re-export path so the
# snapshot file content does not encode an internal module name. Both the
# monolithic _dimension_builders.py and the post-split api/services/dimensions
# package are wired to re-export through api.services.dimensions.
try:
    from api.services.dimensions import (  # noqa: E402
        bill_pain_dim,
        equity_proxy_dim_from_parcel,
        income_dim,
        ownership_dim_from_parcel,
        roof_potential_dim,
    )
except ImportError:
    # Pre-split fallback — _dimension_builders.py is still the source of truth
    from api.services._dimension_builders import (  # noqa: E402
        bill_pain_dim,
        equity_proxy_dim_from_parcel,
        income_dim,
        ownership_dim_from_parcel,
        roof_potential_dim,
    )

from api.models.lead import (  # noqa: E402
    CensusData,
    NRELData,
    ParcelData,
    SolarRoofData,
    UtilityInfo,
)

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def _parcel(apn: str, residential: bool, exempt: bool, arms_year: int | None) -> ParcelData:
    return ParcelData(
        apn=apn,
        address_situs=f"{apn} TEST ST",
        city="LOS ANGELES",
        zip="90001",
        use_category="Residential" if residential else "Commercial",
        is_residential=residential,
        is_taxable=True,
        stream="private" if residential else "not_residential",
        has_homeowners_exemption=exempt,
        arms_length_year=arms_year,
        recording_year=arms_year,
    )


def build_snapshot() -> dict:
    """Run every dimension builder against fixed inputs and return outputs."""
    # 5 ParcelData scenarios covering every ownership/equity branch
    p_exempt_long = _parcel("5814009007", True, True, 1995)
    p_noex_short = _parcel("3247010043", True, False, 2018)
    p_noex_long = _parcel("9999999999", True, False, 1975)  # long-tenure unfiled
    p_noex_no_year = _parcel("9999999998", True, False, None)  # null tenure
    p_commercial = _parcel("4334006009", False, False, 2010)

    # Fixed input fixtures
    roof_25k = SolarRoofData(max_kwh_year=25_000.0)
    roof_60k = SolarRoofData(max_kwh_year=60_000.0)
    roof_null = SolarRoofData(max_kwh_year=None)

    cens_low = CensusData(median_household_income=45_000.0, block_group_geoid="060371234001")
    cens_peak = CensusData(median_household_income=130_000.0, block_group_geoid="060371234002")
    cens_high = CensusData(median_household_income=350_000.0, block_group_geoid="060371234003")
    cens_null = CensusData(median_household_income=None, block_group_geoid="060371234004")

    nrel_typical = NRELData(ac_annual_kwh=6500.0, capacity_factor=0.21, solar_radiation=5.8)
    nrel_null = NRELData(ac_annual_kwh=None)

    util_ladwp = UtilityInfo(
        utility_name="LADWP", representative_rate=0.28, tariff_variant="R-1A",
        nem_regime="1:1 retained", confidence_level="precise", rate_source_note="LADWP R-1A",
    )

    return {
        "roof_potential": {
            "25k_kWh":  roof_potential_dim(roof_25k).model_dump(),
            "60k_kWh":  roof_potential_dim(roof_60k).model_dump(),
            "null":     roof_potential_dim(roof_null).model_dump(),
        },
        "income": {
            "low_45k":   income_dim(cens_low).model_dump(),
            "peak_130k": income_dim(cens_peak).model_dump(),
            "high_350k": income_dim(cens_high).model_dump(),
            "null":      income_dim(cens_null).model_dump(),
        },
        "ownership": {
            "exempt_long":      ownership_dim_from_parcel(p_exempt_long).model_dump(),
            "noex_short":       ownership_dim_from_parcel(p_noex_short).model_dump(),
            "noex_long_tenure": ownership_dim_from_parcel(p_noex_long).model_dump(),
            "noex_no_year":     ownership_dim_from_parcel(p_noex_no_year).model_dump(),
            "commercial":       ownership_dim_from_parcel(p_commercial).model_dump(),
        },
        "equity_proxy": {
            "exempt_1995":  equity_proxy_dim_from_parcel(p_exempt_long).model_dump(),
            "noex_2018":    equity_proxy_dim_from_parcel(p_noex_short).model_dump(),
            "noex_1975":    equity_proxy_dim_from_parcel(p_noex_long).model_dump(),
            "noex_no_year": equity_proxy_dim_from_parcel(p_noex_no_year).model_dump(),
        },
        "bill_pain": {
            "ladwp":      bill_pain_dim(nrel_typical, util_ladwp).model_dump(),
            "no_utility": bill_pain_dim(nrel_typical, None).model_dump(),
            "null_kwh":   bill_pain_dim(nrel_null, util_ladwp).model_dump(),
        },
    }


def main() -> int:
    args = sys.argv[1:]
    if args == ["--diff"]:
        before = SNAPSHOT_DIR / "split_parity_before.json"
        after = SNAPSHOT_DIR / "split_parity_after.json"
        if not before.exists() or not after.exists():
            print(f"missing snapshot: {before.exists()=}  {after.exists()=}")
            return 1
        a = before.read_text(encoding="utf-8")
        b = after.read_text(encoding="utf-8")
        if a == b:
            print("PARITY OK — before and after snapshots are byte-identical.")
            return 0
        print("PARITY FAIL — snapshots differ. Diff:")
        import difflib
        for line in difflib.unified_diff(
            a.splitlines(), b.splitlines(), fromfile="before", tofile="after",
            lineterm="",
        ):
            print(line)
        return 1

    out_path = Path(args[0]) if args else SNAPSHOT_DIR / "split_parity_snapshot.json"
    snapshot = build_snapshot()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(f"snapshot written: {out_path}  ({len(out_path.read_text()):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
