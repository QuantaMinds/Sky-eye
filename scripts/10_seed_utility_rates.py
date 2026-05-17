"""Seed parcels_raw.utility_rates — 3-row hand-maintained lookup.

Phase 1.5d. Three rows: LADWP / SCE / unknown.

Numbers sourced from probes 2026-05-17:
  - LADWP R-1A residential tiered rates (current 2026 schedule, blended ~$0.27)
  - SCE TOU-D-PRIME residential (NEM 3.0 default, blended ~$0.31)
  - unknown = flat-rate fallback preserving Phase 1.5c behavior

confidence_level drives narrative hedging (see
feedback-narrative-precision-must-match-data memory entry).
"""
from __future__ import annotations

import sys

from google.cloud import bigquery

PROJECT = "sky-eye-496604"
TABLE_ID = f"{PROJECT}.parcels_raw.utility_rates"

SCHEMA = [
    bigquery.SchemaField("utility_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("representative_rate", "NUMERIC"),
    bigquery.SchemaField("tariff_variant", "STRING"),
    bigquery.SchemaField("nem_regime", "STRING"),
    bigquery.SchemaField("confidence_level", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("rate_source_note", "STRING"),
    bigquery.SchemaField("effective_date", "DATE"),
]

ROWS = [
    {
        "utility_name": "LADWP",
        "representative_rate": "0.27",
        "tariff_variant": "R-1A",
        "nem_regime": "1:1 retained",
        "confidence_level": "approximate",
        "rate_source_note": (
            "LADWP R-1A residential, blended across tier-1 ($0.247/kWh) and "
            "tier-2 ($0.305/kWh) 2026 schedule. ladwp.com/residential-rates. "
            "Municipal utility — not under CPUC jurisdiction; LADWP Board "
            "retained 1:1 NEM (no NEM-3-equivalent restructure)."
        ),
        "effective_date": "2026-01-01",
    },
    {
        "utility_name": "SCE",
        "representative_rate": "0.31",
        "tariff_variant": "TOU-D-PRIME",
        "nem_regime": "NEM 3.0 (ACC export)",
        "confidence_level": "approximate",
        "rate_source_note": (
            "SCE TOU-D-PRIME residential default tariff for NEM 3.0 customers. "
            "Blended across off-peak ($0.24-0.26/kWh), mid-peak ($0.40-0.56/kWh) "
            "and on-peak ($0.59/kWh). NEM 3.0 export compensation uses the "
            "CPUC Avoided Cost Calculator (time-varying, hourly); NOT modeled "
            "as a flat rate. Narrative must hedge any export-comp claim."
        ),
        "effective_date": "2026-01-01",
    },
    {
        "utility_name": "unknown",
        "representative_rate": "0.30",
        "tariff_variant": None,
        "nem_regime": None,
        "confidence_level": "fallback",
        "rate_source_note": (
            "Flat-rate fallback for addresses outside SCE and LADWP coverage "
            "(other LA-area munis: Burbank/Glendale/Pasadena/Vernon/Azusa/"
            "Cerritos electric). Narrative must NOT name a specific utility "
            "when this row is in use. Phase 1.5d.2 will add muni-specific "
            "coverage if customer demand surfaces it."
        ),
        "effective_date": "2026-01-01",
    },
]


def main() -> int:
    bq = bigquery.Client(project=PROJECT, location="us-west1")
    print(f"(Re)creating {TABLE_ID} ...")
    bq.delete_table(TABLE_ID, not_found_ok=True)
    bq.create_table(bigquery.Table(TABLE_ID, schema=SCHEMA))

    errors = bq.insert_rows_json(TABLE_ID, ROWS)
    if errors:
        print(f"  insert errors: {errors}")
        return 1
    print(f"  inserted {len(ROWS)} rows")

    print("\nVerifying:")
    for row in bq.query(f"""
        SELECT utility_name, representative_rate, tariff_variant,
               nem_regime, confidence_level
        FROM `{TABLE_ID}` ORDER BY utility_name
    """).result():
        print(f"  {row.utility_name:8}  ${row.representative_rate}/kWh  "
              f"tariff={row.tariff_variant or '-':<12}  nem={row.nem_regime or '-':<22}  "
              f"confidence={row.confidence_level}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
