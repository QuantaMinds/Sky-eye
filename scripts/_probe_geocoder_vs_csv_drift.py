"""Check whether the 3 gate-failing addresses pass when geocoded via Google
(the real production path) instead of using the CSV's baked-in lat/lng."""
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from api.services import geocoding, parcel_lookup  # noqa: E402

FAILING_AINS = {"4315015068", "7273028019", "7265014060"}


async def main():
    fixture_path = Path(r"D:\EYE-Lead\Sky-eye\tests\fixtures\labeled_addresses.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    for rec in fixture["records"]:
        if str(rec.get("ain", "")) not in FAILING_AINS:
            continue
        addr = rec.get("property_location", "")
        csv_lat = float(rec.get("lat"))
        csv_lng = float(rec.get("lng"))
        expected_apn = rec.get("ain")
        print(f"\n=== AIN {expected_apn}  /  {addr.strip()} ===")
        print(f"  CSV-baked coord:    ({csv_lat:.7f}, {csv_lng:.7f})")

        # 1. CSV-coord -> parcel
        p_csv, _ = await parcel_lookup.lookup_by_point(float(csv_lat), float(csv_lng))
        print(f"  CSV-coord lookup:   {'None' if p_csv is None else p_csv.apn}")

        # 2. Google-geocoded -> parcel
        try:
            geo, _ = await geocoding.geocode(addr)
        except Exception as exc:
            print(f"  Google geocoding FAILED: {exc}")
            continue
        print(f"  Google geocoded:    ({geo.lat:.7f}, {geo.lng:.7f})  "
              f"delta=({geo.lat - csv_lat:+.6f}, {geo.lng - csv_lng:+.6f}) deg")
        p_g, _ = await parcel_lookup.lookup_by_point(geo.lat, geo.lng)
        print(f"  Google-coord lookup:{'None' if p_g is None else p_g.apn}")

        verdict = ("MATCH expected" if p_g and p_g.apn == expected_apn else "still mismatch")
        print(f"  verdict (Google):   {verdict}")


asyncio.run(main())
