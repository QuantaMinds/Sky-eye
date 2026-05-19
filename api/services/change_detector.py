"""Bbox -> ranked list of parcels likely to have changed between two years.

Uses AlphaEarth annual embeddings as the cheap first filter (one
reduceRegion per parcel per year, runs entirely server-side in EE).
Cosine distance between the year_a and year_b mean vectors is the
ranking score.

Truth-first: parcels with EITHER embedding missing are dropped (NOT
ranked at the bottom — a missing embedding is "we don't know if this
parcel changed", which is different from "we know it didn't"). The
caller sees source='unavailable' if they query a dropped APN directly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from api.services import ee_alphaearth, lb_parcels


@dataclass(frozen=True)
class ChangeCandidate:
    apn: str
    distance: float
    year_a: int
    year_b: int
    embedding_a_date: str
    embedding_b_date: str


def cosine_distance(a: list[float], b: list[float]) -> float:
    """1 - cos(a,b). Range [0, 2]; 0 == identical direction. AlphaEarth
    embeddings are not L2-normalized, so we normalize here."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        # Zero-norm vectors come from masked-everywhere reductions, which
        # ee_alphaearth already surfaces as source='unavailable'. If we got
        # here something upstream substituted zeros — treat as unknown.
        return float("nan")
    dot = sum(x * y for x, y in zip(a, b))
    return 1.0 - dot / (na * nb)


def detect_changes_in_bbox(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
    year_a: int, year_b: int, *, top_n: int = 50, max_parcels: int = 2000,
) -> list[ChangeCandidate]:
    """For each residential parcel in bbox, compute cosine distance
    between AlphaEarth embeddings of year_a and year_b. Return top_n
    parcels by distance.

    Dropped (NOT ranked) when either embedding is unavailable. Caller
    can re-query the APN through get_alphaearth_embeddings to see the
    source='unavailable' attribution.
    """
    apns = lb_parcels.list_apns_in_bbox(
        lon_min, lat_min, lon_max, lat_max, limit=max_parcels,
    )
    candidates: list[ChangeCandidate] = []
    for apn in apns:
        parcel = lb_parcels.get_parcel_geometry(apn)
        if parcel is None or parcel.get("geojson") is None:
            continue
        geo = parcel["geojson"]
        emb_a = ee_alphaearth.get_alphaearth_embeddings(geo, year_a)
        emb_b = ee_alphaearth.get_alphaearth_embeddings(geo, year_b)
        if emb_a.vector is None or emb_b.vector is None:
            continue
        dist = cosine_distance(emb_a.vector, emb_b.vector)
        if math.isnan(dist):
            continue
        candidates.append(ChangeCandidate(
            apn=apn, distance=dist,
            year_a=year_a, year_b=year_b,
            embedding_a_date=emb_a.image_date or "",
            embedding_b_date=emb_b.image_date or "",
        ))
    candidates.sort(key=lambda c: c.distance, reverse=True)
    return candidates[:top_n]
