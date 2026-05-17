# CLAUDE.md

Operating rules for **EYE-Lead / Sky-eye** (rooftop solar lead intelligence). Read before editing. These rules are **mandatory** — no exceptions without an explicit override from the user in the current conversation.

---

## Rule 1 — File size: <100 LOC or 1 module

Every file MUST satisfy one of:

- **Under 100 lines of code** (blank lines and comments don't count toward the limit, but be honest about it), OR
- **Exactly one cohesive module** — one class, one responsibility, one concept. If a file is doing two things, it's not "one module" and the 100-line cap applies.

If a change would push a file past 100 lines and the file is not a single tight module, **split it before committing**. Prefer many small focused files over one large file.

## Rule 2 — Tests must pass before moving on

Every phase, every feature, every code change MUST pass its test cases before being marked done or moving to the next phase. Do not advance with red tests. Do not "fix it in the next phase."

If a test is wrong, fix the test in the same change and explain why in the commit message. Don't just delete it.

## Rule 3 — Truth-first: never fabricate; unknowns surface as null

If we don't know a value, the response MUST say so — `null`, `None`, or an explicit `source: "unavailable"`. **Never** substitute a plausible-looking constant (`1.0`, `0.5`, `True`) to keep a pipeline running. Fabricated values dressed as real data are worse than no data: they silently poison every downstream decision and the customer's trust the moment they cross-check.

Concretely:

- **Model fields** for any value that might be missing: `Optional[float]` with `default=None`, not a "neutral" midpoint.
- **Mocked / unavailable services**: emit `None` with `source: "mock"` or `source: "unavailable"` — don't return a fake-looking real value.
- **Scoring**: when an input dimension is `None`, drop it from the sum and re-normalize the remaining weights. Don't pretend the dimension scored 0.5.
- **API responses**: include per-dimension `source` so callers can distinguish real signal from missing data.
- **LLM prompts**: instruct the model to never assert facts about an unknown dimension. Phrasing like "the resident is a confirmed owner" is fabrication if we have no ownership signal.

**Canonical failure to avoid** (Phase 1 audit, 2026-05-17): `100 Long Beach Blvd, Long Beach, CA` — Edison Theatre, a commercial landmark — scored `0.82` with a narrative claiming "confirmed homeownership (1.00)". Four of seven dimensions were hard-coded constants. The pipeline ran; the answer was a lie.

## Rule 4 — Data quality is the highest priority, and it is NOT the same as tests passing

**Tests passing ≠ data quality.** Treat them as two separate gates, both required:

| Gate | What it checks | How to verify |
|---|---|---|
| **Tests pass** | Code runs, contracts hold, no exceptions | `pytest` is green |
| **Data quality** | Outputs are *correct, complete, meaningful, in the right units, on the right entity* | Manual inspection, sanity checks vs. known truth, distribution checks, row-count audits, spot-checks against ground truth |

**Data quality is the higher bar.** Green tests only prove the plumbing works — they do NOT prove the answers are right.

Examples of "tests pass, data quality fails" — all real failure modes for this project:

- A Solar API call returns `200 OK` with an empty roof segments array → test passes, but we have no roof to model.
- A BigQuery join silently drops 80% of leads because of a key-type mismatch → test passes, output is wrong.
- Coordinates off by 0.01° (~1 km) → test passes, we're scoring the wrong building.
- Units mismatched (kWh vs MWh, m² vs ft²) → test passes, output is off by 1000× or 10.76×.
- Census ACS query returns rows for the wrong tract → test passes, demographics are for the wrong neighborhood.
- PVWatts called with default tilt instead of measured roof tilt → test passes, generation estimate is generic.

**Every phase MUST include explicit data-quality checks separate from unit tests.** A phase is not done when pytest is green; it is done when both gates pass.

---

## Project status

- **Phase 0:** bootstrap — FastAPI scaffold, credential verification for Gemini (Vertex), BigQuery, Earth Engine, Google Solar, Census ACS, NREL PVWatts. See `verify_credentials.py` and `tests/test_phase0.py`.
- **Phase 1 (current):** MVP `POST /api/v1/score-lead` — 7-dimensional solar lead score with Gemini 2.5 Flash narrative. Cached external calls (SQLite, 30 days). See `api/routers/lead_score.py` and `tests/test_phase1.py`.

## Dependencies

- **`pyproject.toml`** is the source of truth for top-level dependency *ranges*.
- **`requirements.txt`** is a pip-freeze **lock file** with exact pins for every transitive. Regenerate with `pip freeze --exclude-editable > requirements.txt` after any dependency change.
- Python **3.11+** (current venv runs 3.13.5).

## Auth model — Vertex AI only for Gemini

**Gemini calls go through Vertex AI**, never Google AI Studio. No `GEMINI_API_KEY` is used anywhere. Auth flows through Application Default Credentials (`google.auth.default()`), and all charges land on `GOOGLE_CLOUD_PROJECT`.

One-time setup:
```powershell
gcloud auth application-default login
```

Production: set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON path. Both paths use the same `vertexai.init(project=..., location=..., credentials=...)` flow.

## Layout

```
Sky-eye/
├── api/                    FastAPI application package
│   ├── config.py           pydantic-settings (env-driven)
│   ├── main.py             FastAPI entrypoint
│   ├── cache.py            SQLite 30-day TTL cache (.cache.db)
│   ├── rate_limit.py       Sliding-window limiter (Solar API: 100/min)
│   ├── models/lead.py      Request/response + service-internal Pydantic models
│   ├── routers/            HTTP routes (health, lead_score)
│   └── services/           One file per external API + scoring + narrative
├── tests/                  pytest suite (test_phase0.py, test_phase1.py)
├── verify_credentials.py   Phase 0 connectivity checks
├── pyproject.toml          Top-level deps (ranges)
├── requirements.txt        Exact lock (regenerated from pip freeze)
└── .env.example            Required env vars (copy to .env)
```

## Run

```powershell
pip install -e ".[dev]"
copy .env.example .env       # then fill in keys
gcloud auth application-default login
python verify_credentials.py
pytest tests/ -v
uvicorn api.main:app --reload
```

Smoke test for Phase 1:
```powershell
curl -X POST http://localhost:8000/api/v1/score-lead `
  -H "Content-Type: application/json" `
  -d '{"address":"100 Long Beach Blvd, Long Beach, CA"}'
```
