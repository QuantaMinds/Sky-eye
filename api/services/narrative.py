"""Gemini 2.5 Flash narrative via Vertex AI through the unified google-genai SDK.

Why google-genai (not vertexai.generative_models): the legacy
`vertexai.generative_models` module was deprecated 2025-06-24 and is being
removed 2026-06-24. The unified SDK (`from google import genai`) is the
forward-compatible path and supports the same Vertex backend via
`Client(vertexai=True, project=..., location=...)`.

Auth: Application Default Credentials. All charges land on
GOOGLE_CLOUD_PROJECT. No Google AI Studio API key in use anywhere.
Phase 4: cached forever via ttl_cache (we own the artifact per Vertex
ToS); rate-limited at 60/min via the "gemini" service; input/output
token usage recorded from response.usage_metadata for /health.
"""
from __future__ import annotations

import asyncio
import hashlib

from api.config import get_settings
from api.middleware import rate_limiter, ttl_cache
from api.models.lead import ScoreDimensions

_MODEL_NAME = "gemini-2.5-flash"
_SERVICE = "gemini"


def _call_gemini(prompt: str) -> tuple[str, int, int]:
    """Invoke Gemini 2.5 Flash via Vertex. Isolated for monkeypatching.

    Returns (text, input_tokens, output_tokens). Token counts come from
    the response usage_metadata; we surface them so the rate_limiter
    token counter can record actual usage rather than a guess.
    """
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
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=512,
            temperature=0.4,
            candidate_count=1,
            # Disable thinking — for a 5-sentence narrative the thinking
            # budget costs ~15s latency for no quality win.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    return response.text or "", int(in_tok), int(out_tok)


_DIM_NAMES = (
    "roof_potential", "income_qualification", "ownership", "bill_pain",
    "equity_proxy", "no_existing_solar", "intent_signal",
)


def _build_prompt(
    address: str, score: float, dims: ScoreDimensions, confidence: float
) -> str:
    available_lines: list[str] = []
    unavailable_lines: list[str] = []
    for name in _DIM_NAMES:
        dv = getattr(dims, name)
        if dv.value is not None:
            available_lines.append(f"  {name:<22} = {dv.value:.2f}   (source: {dv.source})")
        else:
            note = f" — {dv.note}" if dv.note else ""
            unavailable_lines.append(f"  {name:<22}  UNAVAILABLE{note}")

    unavailable_block = (
        "UNAVAILABLE dimensions (we do NOT have data — never assert facts about these):\n"
        + "\n".join(unavailable_lines) + "\n\n"
        if unavailable_lines else ""
    )
    return (
        "You are advising a residential solar installer. Write ONE paragraph "
        "(4-6 sentences) explaining whether this lead is a good prospect.\n\n"
        f"Address: {address}\n"
        f"Score (over available dimensions only): {score:.2f}\n"
        f"Confidence: {confidence:.0%} of total weight backed by real data\n\n"
        "AVAILABLE dimensions (real measurements — discuss these):\n"
        + "\n".join(available_lines) + "\n\n"
        + unavailable_block
        + "RULES — these are not optional:\n"
        "- Mention only the AVAILABLE dimensions when citing values. NEVER invent numbers.\n"
        "- If important dimensions are UNAVAILABLE, explicitly say we don't have that data "
        "(e.g. 'we don't yet have ownership data') and recommend the installer verify before contact.\n"
        "- NEVER claim the resident is an owner / homeowner, NEVER claim there is or isn't existing "
        "solar, NEVER claim intent unless the corresponding dimension appears in AVAILABLE above.\n"
        "- Be concrete and reference the real values shown.\n"
        "\n"
        "PRECISION RULES for utility / rate / dollar amounts (truth-first prose):\n"
        "- The bill_pain source string includes the utility name, representative rate, and "
        "tariff variant. When mentioning these, hedge with 'approximately' or 'representative'.\n"
        "  CORRECT:   'approximately $0.27/kWh under LADWP R-1A (representative residential blend)'\n"
        "  CORRECT:   'estimated annual cost roughly $2,000 at the LADWP residential rate'\n"
        "  WRONG:     'this home pays exactly $0.273/kWh and will save $1,847 per year'\n"
        "  WRONG:     any dollar amount to the cent without a hedge word in the same sentence.\n"
        "- If the bill_pain source says 'unknown' utility or notes confidence='fallback', "
        "DO NOT name a specific utility. Say 'utility not yet identified for this address' "
        "and recommend manual verification. Do NOT helpfully fill in 'this is probably LADWP'.\n"
        "- For NEM regime: 'LADWP has retained 1:1 net metering' is fine if the source says so. "
        "'SCE NEM 3.0 export compensation is significantly reduced' is fine. Specific export $/kWh "
        "numbers are NOT fine — those depend on hourly Avoided Cost Calculator values we don't model."
    )


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


async def generate_narrative(
    address: str, score: float, dims: ScoreDimensions, confidence: float = 1.0
) -> tuple[str, bool]:
    """Returns (text, cache_hit)."""
    prompt = _build_prompt(address, score, dims, confidence)
    key = _cache_key(prompt)
    cached = await ttl_cache.get(_SERVICE, key)
    if cached is not None:
        return cached["text"], True

    async with await rate_limiter.acquire(_SERVICE):
        text, in_tok, out_tok = await asyncio.to_thread(_call_gemini, prompt)
    rate_limiter.record_gemini_tokens(in_tok, out_tok)
    await ttl_cache.set(_SERVICE, key, {"text": text})
    return text, False
