"""One-shot forensic probe — do NOT commit. Single live trace through the
Phase 5 stack to verify the implementation actually does what it says.

Budget: one AlphaEarth pair, one NAIP pair, one cosine distance, one
parcel lookup. Skips Gemini Pro (paid) unless --with-gemini is passed.
"""
from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery
from api.services import (
    change_detector,
    chip_extractor,
    confidence_pipeline,
    ee_alphaearth,
    lb_parcels,
    permit_matcher,
)
import datetime as dt


def main(with_gemini: bool, year_a: int, year_b: int) -> int:
    print("=" * 70)
    print("PHASE 5 FORENSIC TRACE")
    print("=" * 70)

    # STEP 1 — pull one LB residential parcel
    print("\n[step 1] Pull one LB residential parcel from BigQuery")
    c = bigquery.Client(project="sky-eye-496604", location="us-west1")
    sql = (
        "SELECT apn FROM `sky-eye-496604.parcels.la_county` "
        "WHERE city = 'LONG BEACH CA' AND is_residential = TRUE "
        "AND geom IS NOT NULL AND sqft_main BETWEEN 1500 AND 3000 "
        "LIMIT 1"
    )
    rows = list(c.query(sql).result())
    if not rows:
        print("  no LB residential parcels in DB — abort")
        return 1
    apn = rows[0]["apn"]
    print(f"  probe APN: {apn}")

    # STEP 2 — get_parcel_geometry: does it return use_subcategory?
    print("\n[step 2] get_parcel_geometry(apn) — checks what fields land")
    parcel = lb_parcels.get_parcel_geometry(apn)
    if parcel is None:
        print("  parcel is None — abort"); return 1
    print(f"  keys returned: {sorted(parcel.keys())}")
    print(f"  use_category: {parcel.get('use_category')!r}")
    print(f"  use_subcategory present? {'use_subcategory' in parcel}")
    print(f"  sqft_main: {parcel.get('sqft_main')}")
    geo = parcel["geojson"]
    geom_type = geo.get("type")
    coords_preview = str(geo.get("coordinates"))[:80]
    print(f"  geojson type={geom_type} coords={coords_preview}...")

    # STEP 3 — AlphaEarth pair
    print(f"\n[step 3] AlphaEarth embeddings for {year_a} and {year_b}")
    emb_a = ee_alphaearth.get_alphaearth_embeddings(geo, year_a)
    emb_b = ee_alphaearth.get_alphaearth_embeddings(geo, year_b)
    print(f"  {year_a}: source={emb_a.source} note={emb_a.note}")
    print(f"  {year_b}: source={emb_b.source} note={emb_b.note}")
    if emb_a.vector and emb_b.vector:
        print(f"  vec lengths: a={len(emb_a.vector)} b={len(emb_b.vector)}")
        print(f"  vec_a[:4]:  {[round(x,4) for x in emb_a.vector[:4]]}")
        print(f"  vec_b[:4]:  {[round(x,4) for x in emb_b.vector[:4]]}")
        dist = change_detector.cosine_distance(emb_a.vector, emb_b.vector)
        print(f"  cosine distance: {dist:.5f}  (threshold gate: > 0.4)")

    # STEP 4 — NAIP chip pair
    print(f"\n[step 4] NAIP chip pair via chip_extractor.fetch_pair")
    chips = chip_extractor.fetch_pair(apn, year_a, year_b)
    print(f"  naip_a: source={chips.naip_a.source} date={chips.naip_a.image_date} png_bytes={len(chips.naip_a.png) if chips.naip_a.png else 0}")
    print(f"  naip_b: source={chips.naip_b.source} date={chips.naip_b.image_date} png_bytes={len(chips.naip_b.png) if chips.naip_b.png else 0}")
    print(f"  s2_a:   source={chips.s2_a.source}   date={chips.s2_a.image_date}   png_bytes={len(chips.s2_a.png) if chips.s2_a.png else 0}")
    print(f"  s2_b:   source={chips.s2_b.source}   date={chips.s2_b.image_date}   png_bytes={len(chips.s2_b.png) if chips.s2_b.png else 0}")

    # STEP 5 — permit_matcher tri-state
    print(f"\n[step 5] permit_matcher.has_permit (tri-state)")
    cov = permit_matcher.has_coverage(dt.date(year_a - 1, 1, 1), dt.date(year_b, 12, 31))
    print(f"  has_coverage({year_a-1}-01-01..{year_b}-12-31): {cov}")
    hp = permit_matcher.has_permit(apn, dt.date(year_a - 1, 1, 1), dt.date(year_b, 12, 31))
    print(f"  has_permit({apn}): {hp!r}   (None expected when coverage absent)")

    # STEP 6 — confidence pipeline with realistic inputs
    print(f"\n[step 6] confidence_pipeline.evaluate (real distance + tri-state permit)")
    if emb_a.vector and emb_b.vector:
        dist = change_detector.cosine_distance(emb_a.vector, emb_b.vector)
    else:
        dist = None
    r = confidence_pipeline.evaluate(
        alphaearth_distance=dist,
        has_permit_result=hp,
        gemini_change_type=None,    # not running classifier in this trace
        gemini_confidence=None,
        gemini_added_sqft=None,
    )
    print(f"  available_gates: {r.available_gates}")
    print(f"  fired_gates:     {r.fired_gates}")
    print(f"  final_score:     {r.final_score}")
    for name, g in r.gates.items():
        print(f"    {name:<24} fired={g.fired!s:<5} note={g.note}")

    # STEP 7 — storage probe: does anything land in BQ?
    print(f"\n[step 7] Storage probe (BEFORE endpoint hit)")
    for fqtn in ["sky-eye-496604.leadlens.change_events",
                 "sky-eye-496604.leadlens.api_cache"]:
        n = next(iter(c.query(f"SELECT COUNT(*) AS n FROM `{fqtn}`").result()))["n"]
        print(f"  {fqtn}: {n} rows")

    if with_gemini:
        print(f"\n[step 8] OPTIONAL — Gemini Pro classifier (one billed call)")
        from api.services import multimodal_classifier as mc
        import asyncio
        async def go():
            return await mc.classify(
                apn=apn, sqft=parcel.get("sqft_main"),
                use_subcategory=parcel.get("use_subcategory", ""),  # field is MISSING from get_parcel_geometry — will be ''
                png_a=chips.naip_a.png, png_b=chips.naip_b.png,
                naip_a_date=chips.naip_a.image_date or "",
                naip_b_date=chips.naip_b.image_date or "",
            )
        result, was_cached = asyncio.run(go())
        print(f"  source: {result.source}")
        print(f"  change_type: {result.change_type}")
        print(f"  confidence: {result.confidence_0_1}")
        print(f"  added_sqft: {result.estimated_added_sqft}")
        print(f"  evidence: {result.evidence}")
        print(f"  cache_hit: {was_cached}")

    print()
    print("=" * 70)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--with-gemini", action="store_true",
                   help="Include the paid Gemini Pro call (one billed inference)")
    p.add_argument("--year-a", type=int, default=2022)
    p.add_argument("--year-b", type=int, default=2024)
    args = p.parse_args()
    sys.exit(main(args.with_gemini, args.year_a, args.year_b))
