"""Generate tests/fixtures/labeled_addresses.json from BQ — Phase 1.5c fixture seed.

Per option (a): sample BQ for both known landmark addresses (high-risk) and
zip-code-bucketed random residential SFRs. Output a JSON fixture annotated
with which records need human spot-check at portal.assessor.lacounty.gov.

Truth-first: the fixture file header documents the source and the
manual-verification gate (8 high-risk records must be confirmed at the
portal before the fixture is treated as authoritative).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from google.cloud import bigquery

PROJECT = "sky-eye-496604"
TABLE = f"{PROJECT}.parcels_raw.la_county_attributes"
OUT_PATH = Path(r"D:\EYE-Lead\Sky-eye\tests\fixtures\labeled_addresses.json")

# Known landmark addresses to find via partial match (LIKE). The advisor's
# 8-property manual-verification gate covers the first 5 non-residential
# entries plus 3 complex residential picks made after sampling.
LANDMARK_QUERIES: list[tuple[str, str, str]] = [
    # (label, LIKE pattern on property_location, expected category)
    ("Edison Theatre",         "100 LONG BEACH BLVD%LONG BEACH%",   "non_residential"),
    ("LA Convention Center",   "1201 S FIGUEROA ST%LOS ANGELES%",   "non_residential"),
    ("Long Beach City Hall",   "411 W OCEAN BLVD%LONG BEACH%",      "non_residential"),
    ("LACMA Museum",           "5905 WILSHIRE BLVD%LOS ANGELES%",   "non_residential"),
    ("USC main campus",        "3551 TROUSDALE PKWY%LOS ANGELES%",  "non_residential"),
    ("Cedars-Sinai Hospital",  "8700 BEVERLY BLVD%LOS ANGELES%",    "non_residential"),
    ("Dodger Stadium",         "1000 VIN SCULLY AVE%LOS ANGELES%",  "non_residential"),
]


def fetch_landmarks(bq: bigquery.Client) -> list[dict]:
    """For each landmark, find the closest BQ row by property_location LIKE."""
    results = []
    for label, pattern, expected in LANDMARK_QUERIES:
        sql = f"""
            SELECT ain, property_location, city, zip_code_1 AS zip,
                   use_code_1st_digit AS use_category,
                   property_use_code AS use_code,
                   home_owners_exemption,
                   property_taxable,
                   location_latitude AS lat,
                   location_longitude AS lng
            FROM `{TABLE}`
            WHERE roll_year = '2024' AND property_location LIKE @pattern
            LIMIT 3
        """
        rows = list(bq.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("pattern", "STRING", pattern)]
            ),
        ).result())
        if not rows:
            results.append({"label": label, "status": "NOT_FOUND", "pattern": pattern})
            continue
        row = dict(rows[0])
        row["label"] = label
        row["expected_category"] = expected
        row["needs_manual_verification"] = True
        row["verify_at"] = "https://portal.assessor.lacounty.gov/"
        results.append(row)
    return results


def fetch_residential_samples(bq: bigquery.Client) -> list[dict]:
    """Pull residential SFRs from a spread of LA County zip codes."""
    # zip codes spanning Belmont Shore, Bixby Knolls, LA City westside,
    # Pasadena, South Bay, etc. -- good geographic + price-band diversity.
    zip_codes = ['90803', '90807', '90802', '90712', '90274',
                 '91011', '91024', '90049', '90064', '90042']
    samples_per_zip = 2  # 10 zips * 2 = 20 picks; trim later if needed
    sql = f"""
        WITH ranked AS (
          SELECT ain, property_location, city, zip_code_1 AS zip,
                 use_code_1st_digit AS use_category,
                 property_use_code AS use_code,
                 use_code_2nd_digit AS use_subcategory,
                 home_owners_exemption,
                 property_taxable,
                 location_latitude AS lat,
                 location_longitude AS lng,
                 ROW_NUMBER() OVER (PARTITION BY zip_code_1 ORDER BY FARM_FINGERPRINT(ain)) AS rn
          FROM `{TABLE}`
          WHERE roll_year = '2024'
            AND use_code_1st_digit = 'Residential'
            AND use_code_2nd_digit = 'Single Family Residence'
            AND zip_code_1 IN UNNEST(@zips)
            AND property_location IS NOT NULL
            AND ARRAY_LENGTH(SPLIT(property_location, ' ')) >= 3
        )
        SELECT * EXCEPT(rn) FROM ranked WHERE rn <= @per_zip
    """
    rows = list(bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("zips", "STRING", zip_codes),
            bigquery.ScalarQueryParameter("per_zip", "INT64", samples_per_zip),
        ]),
    ).result())
    out = []
    for r in rows:
        d = dict(r)
        d["label"] = f"Residential SFR (zip {d['zip']})"
        d["expected_category"] = "residential"
        d["needs_manual_verification"] = False
        out.append(d)
    return out


def fetch_complex_residential(bq: bigquery.Client) -> list[dict]:
    """3 edge-case residential picks. Uses actual LA County subcategory strings."""
    queries = [
        ("Duplex (residential)",
         "use_code_2nd_digit = 'Double, Duplex, or Two Units'",
         "residential"),
        ("Apartment building (5+ units, residential)",
         "use_code_2nd_digit = 'Five or More Units or Apartments (Any Combination)'",
         "residential"),
        ("Manufactured home (residential)",
         "use_code_2nd_digit = 'Manufactured Home'",
         "residential"),
    ]
    out = []
    for label, where_clause, expected in queries:
        sql = f"""
            SELECT ain, property_location, city, zip_code_1 AS zip,
                   use_code_1st_digit AS use_category,
                   property_use_code AS use_code,
                   use_code_2nd_digit AS use_subcategory,
                   home_owners_exemption, property_taxable,
                   location_latitude AS lat, location_longitude AS lng
            FROM `{TABLE}`
            WHERE roll_year = '2024' AND use_code_1st_digit = 'Residential'
              AND {where_clause}
              AND property_location IS NOT NULL
            ORDER BY FARM_FINGERPRINT(ain) LIMIT 1
        """
        rows = list(bq.query(sql).result())
        if rows:
            d = dict(rows[0])
            d["label"] = label
            d["expected_category"] = expected
            d["needs_manual_verification"] = True
            d["verify_at"] = "https://portal.assessor.lacounty.gov/"
            out.append(d)
    return out


def fetch_nonresidential_by_category(bq: bigquery.Client) -> list[dict]:
    """Sample 1 parcel from each non-residential category for type coverage."""
    categories = [
        "Commercial", "Industrial", "Institutional",
        "Recreational", "Miscellaneous", "Dry Farm", "Irrigated Farm",
    ]
    out = []
    for cat in categories:
        sql = f"""
            SELECT ain, property_location, city, zip_code_1 AS zip,
                   use_code_1st_digit AS use_category,
                   property_use_code AS use_code,
                   use_code_2nd_digit AS use_subcategory,
                   home_owners_exemption, property_taxable,
                   location_latitude AS lat, location_longitude AS lng
            FROM `{TABLE}`
            WHERE roll_year = '2024' AND use_code_1st_digit = @cat
              AND property_location IS NOT NULL
              AND property_location != ''
              AND location_latitude IS NOT NULL
            ORDER BY FARM_FINGERPRINT(ain) LIMIT 1
        """
        rows = list(bq.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("cat", "STRING", cat)],
            ),
        ).result())
        if rows:
            d = dict(rows[0])
            d["label"] = f"{cat} sample"
            d["expected_category"] = "non_residential"
            d["needs_manual_verification"] = False
            out.append(d)
    return out


def main() -> int:
    bq = bigquery.Client(project=PROJECT, location="us-west1")
    print("Fetching 7 landmark non-residentials by partial-match...")
    landmarks_raw = fetch_landmarks(bq)
    landmarks = [x for x in landmarks_raw if x.get("ain")]  # drop NOT_FOUND
    print(f"  got {len(landmarks)} of {len(landmarks_raw)}")
    print("Fetching 1 sample per non-residential category...")
    nonres_samples = fetch_nonresidential_by_category(bq)
    print(f"  got {len(nonres_samples)}")
    print("Fetching residential SFRs across 10 zip codes...")
    residential = fetch_residential_samples(bq)
    print(f"  got {len(residential)}")
    print("Fetching 3 complex-residential edge cases (duplex/apt/manufactured)...")
    complex_res = fetch_complex_residential(bq)
    print(f"  got {len(complex_res)}")

    # Compose ~30 total: 5 landmark + 7 category samples + 12 residential SFR + 3 complex res = 27
    residential = residential[:12]
    all_records = landmarks + nonres_samples + complex_res + residential

    fixture = {
        "_meta": {
            "purpose": "Phase 1.5c residential-filter and parcel-lookup test fixture",
            "generated_from": TABLE,
            "roll_year": "2024",
            "rules": [
                "Records with needs_manual_verification=true MUST be verified against "
                "portal.assessor.lacounty.gov before the fixture is treated as authoritative.",
                "Test intent: address -> geocode -> ST_CONTAINS(parcel polygon) -> expected_ain match",
                "The Geocoding API is an independent variable from LA County's polygon, "
                "so apn-match validates spatial intersection precision, not string equality.",
            ],
        },
        "records": all_records,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(fixture, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}  ({len(fixture['records'])} records)")

    # Summary table of the 8 verify-me-please records
    print("\n=== Records flagged for manual portal verification ===")
    print(f"{'#':>2}  {'label':<24}  {'AIN':<12}  {'use_category':<16}  {'property_location':<50}")
    for i, r in enumerate(fixture["records"], 1):
        if r.get("needs_manual_verification"):
            print(f"{i:>2}  {r['label'][:24]:<24}  {r.get('ain','?'):<12}  "
                  f"{r.get('use_category','?'):<16}  {r.get('property_location','?')[:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
