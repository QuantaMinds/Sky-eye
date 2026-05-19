"""Per-parcel chip orchestration.

Two roles:
  1. fetch_pair(apn, year_a, year_b) — given an APN, pull NAIP+S2 chips
     for both years. Returns a dict with all four images (or None each)
     plus source attribution, so callers can render or run a classifier.
  2. montage(...) — compose the four chips into a single 2x2 PNG for
     human labeling. Missing chips render as a "(unavailable)" tile so
     the labeler can see the gap rather than receive a misleading image.

Truth-first: missing chips stay None all the way out — montage draws an
explicit placeholder, never a synthetic image.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from api.services import ee_naip, ee_sentinel2, lb_parcels
from api.services.ee_naip import ChipResult


@dataclass(frozen=True)
class ParcelChipSet:
    apn: str
    parcel: dict[str, Any] | None
    naip_a: ChipResult
    naip_b: ChipResult
    s2_a: ChipResult
    s2_b: ChipResult

    @property
    def has_naip_pair(self) -> bool:
        return self.naip_a.source == "naip" and self.naip_b.source == "naip"


def _unavailable(note: str) -> ChipResult:
    return ChipResult(png=None, source="unavailable", image_date=None, note=note)


def fetch_pair(apn: str, year_a: int, year_b: int) -> ParcelChipSet:
    """Look up the parcel and fetch NAIP+S2 chips for both years."""
    parcel = lb_parcels.get_parcel_geometry(apn)
    if parcel is None or parcel.get("geojson") is None:
        miss = _unavailable("parcel geometry not found")
        return ParcelChipSet(apn, None, miss, miss, miss, miss)
    geo = parcel["geojson"]
    return ParcelChipSet(
        apn=apn,
        parcel=parcel,
        naip_a=ee_naip.get_naip_chip(geo, year_a, size_px=256),
        naip_b=ee_naip.get_naip_chip(geo, year_b, size_px=256),
        s2_a=ee_sentinel2.get_sentinel2_chip(geo, year_a, size_px=128),
        s2_b=ee_sentinel2.get_sentinel2_chip(geo, year_b, size_px=128),
    )


def _tile(chip: ChipResult, size: int, label: str) -> Image.Image:
    tile = Image.new("RGB", (size, size + 24), color=(40, 40, 40))
    if chip.png is not None:
        img = Image.open(io.BytesIO(chip.png)).convert("RGB").resize((size, size))
        tile.paste(img, (0, 24))
    else:
        draw = ImageDraw.Draw(tile)
        msg = chip.note or "unavailable"
        draw.text((6, size // 2), f"(unavailable)\n{msg[:48]}", fill=(220, 80, 80))
    draw = ImageDraw.Draw(tile)
    draw.text((6, 4), label, fill=(255, 255, 255))
    return tile


def montage(chipset: ParcelChipSet, year_a: int, year_b: int) -> bytes:
    """Compose a 2x2 (NAIP top, S2 bottom) montage PNG. Tile size 256."""
    s = 256
    canvas = Image.new("RGB", (s * 2, (s + 24) * 2), color=(20, 20, 20))
    canvas.paste(_tile(chipset.naip_a, s, f"NAIP {year_a}"), (0, 0))
    canvas.paste(_tile(chipset.naip_b, s, f"NAIP {year_b}"), (s, 0))
    canvas.paste(_tile(chipset.s2_a, s, f"S2 {year_a}"), (0, s + 24))
    canvas.paste(_tile(chipset.s2_b, s, f"S2 {year_b}"), (s, s + 24))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
