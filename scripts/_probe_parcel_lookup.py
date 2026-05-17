"""Smoke test the new parcel_lookup service end-to-end."""
import asyncio
import time

from dotenv import load_dotenv

load_dotenv()

from api.services import parcel_lookup  # noqa: E402


async def main():
    # 4 test points covering the variety:
    #   1. Edison Theatre  — multi-unit residential, 5+ units, recent sale
    #   2. Belmont Shore SFR  — single family, likely owner-occupied (long tenure)
    #   3. LA Convention Center — non-residential
    #   4. Open ocean   — should resolve to None (not in any parcel)
    cases = [
        ("Edison Theatre",            33.7683013, -118.1887403),
        ("Belmont Shore SFR sample",  33.7600,    -118.1380),
        ("LA Convention Center",      34.0405,    -118.2680),
        ("Open ocean (no parcel)",    33.5000,    -118.7000),
    ]
    for label, lat, lng in cases:
        print(f"\n=== {label}  ({lat}, {lng}) ===")
        t0 = time.time()
        parcel, was_cached = await parcel_lookup.lookup_by_point(lat, lng)
        elapsed = (time.time() - t0) * 1000
        print(f"  elapsed: {elapsed:.0f} ms  cached: {was_cached}")
        if parcel is None:
            print(f"  parcel:  None (no LA County parcel contains this point)")
        else:
            print(f"  apn:                       {parcel.apn}")
            print(f"  address:                   {parcel.address_situs}")
            print(f"  use_category/subcategory:  {parcel.use_category} / {parcel.use_subcategory}")
            print(f"  is_residential / taxable:  {parcel.is_residential} / {parcel.is_taxable}")
            print(f"  stream:                    {parcel.stream}")
            print(f"  homeowner exemption:       {parcel.has_homeowners_exemption}")
            print(f"  arms_length_year:          {parcel.arms_length_year}")
            print(f"  year_built / sqft / value: {parcel.year_built} / {parcel.sqft_main} / {parcel.total_value}")

        # warm re-run (double-click shield test)
        t0 = time.time()
        parcel2, was_cached2 = await parcel_lookup.lookup_by_point(lat, lng)
        elapsed2 = (time.time() - t0) * 1000
        print(f"  warm:    {elapsed2:.0f} ms  cached: {was_cached2}")


asyncio.run(main())
