"""Gemini 2.5 Pro vision classifier for before/after NAIP chip pairs.

This is the ONLY place TaxLens uses Pro (vs Flash for the LeadLens
narrative). Pro is ~10x more expensive than Flash, so we gate it
behind the cheap AlphaEarth distance filter — only top-N candidates
ever reach this classifier.

Truth-first contract:
- Either chip None  -> source='unavailable', Gemini NEVER called
- Malformed JSON   -> source='unavailable' (NOT a heuristic salvage)
- Invalid change_type -> source='unavailable' (NOT 'unknown' fallback)
- Live call cached forever (we own the artifact, per Vertex ToS — same
  cache policy as narrative.py)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from api.config import get_settings
from api.middleware import rate_limiter, ttl_cache

_MODEL_NAME = "gemini-2.5-pro"
_SERVICE = "gemini"
_VALID_TYPES = (
    "new_adu_detached", "addition_to_existing", "new_pool",
    "garage_conversion", "no_significant_change", "demolition",
)


@dataclass(frozen=True)
class ClassificationResult:
    change_type: str | None
    confidence_0_1: float | None
    estimated_added_sqft: float | None
    evidence: str | None
    source: str   # 'gemini_pro' | 'unavailable'
    note: str | None = None


def _build_prompt(apn: str, sqft: int | None, use_subcategory: str) -> str:
    sqft_str = f"{sqft} sqft" if sqft else "unknown sqft"
    return (
        "You are a property assessment specialist analyzing satellite imagery for "
        "unpermitted construction. Compare these two images of the same parcel "
        "taken roughly 2 years apart (BEFORE first, AFTER second).\n\n"
        f"Parcel APN: {apn}\nParcel size: {sqft_str}\n"
        f"Existing use: {use_subcategory or 'unknown'}\n\n"
        "Identify exactly ONE of these change types:\n"
        "  new_adu_detached    -- new accessory dwelling unit, detached\n"
        "  addition_to_existing -- visible addition to the main structure\n"
        "  new_pool            -- pool that was not there before\n"
        "  garage_conversion   -- garage now appears as living space (door removed, windows added)\n"
        "  demolition          -- structure removed\n"
        "  no_significant_change -- nothing visibly different\n\n"
        "Respond ONLY with JSON in this exact shape, no prose, no markdown fences:\n"
        '{"change_type":"<one of the six above>","confidence_0_1":<float 0..1>,'
        '"estimated_added_sqft":<int or null>,"evidence":"<one sentence>"}\n\n'
        "If you cannot determine the change type with at least 0.4 confidence, "
        "output change_type='no_significant_change' with confidence reflecting "
        "your uncertainty. NEVER invent a structure you cannot see in the image."
    )


def _call_gemini_pro(
    prompt: str, png_a: bytes, png_b: bytes,
) -> tuple[str, int, int]:
    """Isolated for monkeypatching. Returns (text, input_tokens, output_tokens)."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.google_cloud_project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT not set — required for Vertex AI")
    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.vertex_ai_location,
    )
    response = client.models.generate_content(
        model=_MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=png_a, mime_type="image/png"),
            types.Part.from_bytes(data=png_b, mime_type="image/png"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=400,
            temperature=0.1,   # deterministic; this is classification, not creative writing
            candidate_count=1,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    return response.text or "", int(in_tok), int(out_tok)


def _parse(text: str) -> ClassificationResult:
    """Strict JSON parse. ANY deviation -> source='unavailable'."""
    try:
        obj = json.loads(text.strip().strip("`").lstrip("json").strip())
    except json.JSONDecodeError as exc:
        return ClassificationResult(
            None, None, None, None, "unavailable",
            note=f"JSON parse failed: {exc}",
        )
    change_type = obj.get("change_type")
    if change_type not in _VALID_TYPES:
        return ClassificationResult(
            None, None, None, None, "unavailable",
            note=f"unrecognized change_type: {change_type!r}",
        )
    conf = obj.get("confidence_0_1")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        return ClassificationResult(
            None, None, None, None, "unavailable",
            note=f"invalid confidence_0_1: {conf!r}",
        )
    added = obj.get("estimated_added_sqft")
    if added is not None and not isinstance(added, (int, float)):
        added = None  # null is fine; non-numeric is dropped to None
    return ClassificationResult(
        change_type=change_type,
        confidence_0_1=float(conf),
        estimated_added_sqft=float(added) if added is not None else None,
        evidence=(obj.get("evidence") or "").strip()[:300] or None,
        source="gemini_pro",
        note=None,
    )


def _cache_key(apn: str, naip_a_date: str, naip_b_date: str, prompt: str) -> str:
    h = hashlib.sha256(f"{apn}|{naip_a_date}|{naip_b_date}|{prompt}".encode()).hexdigest()
    return f"taxlens-classify:{h[:24]}"


async def classify(
    apn: str, sqft: int | None, use_subcategory: str,
    png_a: bytes | None, png_b: bytes | None,
    naip_a_date: str, naip_b_date: str,
) -> tuple[ClassificationResult, bool]:
    """Returns (result, cache_hit). If either chip is None, returns
    source='unavailable' WITHOUT calling Gemini."""
    if png_a is None or png_b is None:
        return ClassificationResult(
            None, None, None, None, "unavailable",
            note="missing NAIP chip pair — classifier not run",
        ), False

    prompt = _build_prompt(apn, sqft, use_subcategory)
    key = _cache_key(apn, naip_a_date, naip_b_date, prompt)
    cached = await ttl_cache.get(_SERVICE, key)
    if cached is not None:
        return ClassificationResult(**cached), True

    async with await rate_limiter.acquire(_SERVICE):
        text, in_tok, out_tok = await asyncio.to_thread(
            _call_gemini_pro, prompt, png_a, png_b,
        )
    rate_limiter.record_gemini_tokens(in_tok, out_tok)
    result = _parse(text)
    if result.source == "gemini_pro":
        await ttl_cache.set(_SERVICE, key, {
            "change_type": result.change_type,
            "confidence_0_1": result.confidence_0_1,
            "estimated_added_sqft": result.estimated_added_sqft,
            "evidence": result.evidence,
            "source": result.source,
            "note": result.note,
        })
    return result, False
