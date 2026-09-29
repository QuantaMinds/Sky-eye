# Sky-eye (EYE-Lead)

Rooftop solar lead intelligence platform, built by QuantaMind. Sky-eye ships two products on one FastAPI backend and one React frontend:

| Product | What it does | Endpoint |
|---|---|---|
| **LeadLens** | Scores a residential address as a solar lead across 7 dimensions, with a Gemini-written narrative and a PDF report | `POST /api/v1/score-lead` |
| **TaxLens** | Detects unpermitted construction by comparing aerial imagery between two years for a bounding box | `POST /api/v1/detect-changes` |

> **Truth-first:** unknown values are returned as `null` with a `source` of `unavailable` or `mock`. Nothing is filled in with a plausible-looking constant. See [CLAUDE.md](CLAUDE.md) and [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md).

## API

All routes are mounted in `api/main.py`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/api/v1/score-lead` | Score one address (LeadLens) |
| POST | `/api/v1/score-lead/{apn}/narrative` | Gemini narrative for a scored parcel |
| POST | `/api/v1/batch-score` | Start a batch scoring job from CSV |
| GET | `/api/v1/batch-score/{job_id}` | Batch job status |
| GET | `/api/v1/batch-score/{job_id}/export` | Export batch results |
| POST | `/api/v1/generate-report` | Generate the PDF report |
| POST | `/api/v1/detect-changes` | Change detection for a bbox (TaxLens) |

### TaxLens pipeline

`POST /api/v1/detect-changes` takes `bbox` (`[lon_min, lat_min, lon_max, lat_max]`, WGS84), `year_a`, `year_b`, `min_confidence` (default 0.6) and `top_n` (default 50). It runs:

1. **AlphaEarth embeddings** rank parcels by cosine distance between the two years (cheap first filter).
2. **NAIP chip pair** is extracted for each candidate.
3. **Gemini Pro vision classifier** labels the change type and estimated added sqft.
4. **Permit matcher** does a tri-state lookup (permit, no permit, unavailable).
5. **5-gate confidence pipeline** produces a final score with a per-gate audit trail.
6. Detections below `min_confidence` are dropped and the rest are returned ranked.

The endpoint is synchronous. Expect 30–90 seconds for a small bbox because the Gemini call dominates.

The confidence-pipeline thresholds are **not yet validated** against labelled data. Treat scores as relative rankings until calibration is done.

## Repository layout

```
Sky-eye/
├── api/            FastAPI app: routers, services, models, middleware, infra SQL
├── frontend/       Vite + React 19 + TypeScript UI (Tailwind v4, shadcn/ui)
├── scripts/        Data loading, BigQuery setup, audits, labeling tools
├── tests/          pytest suite (phase 0-5)
├── fixtures/       Sample data
├── CLAUDE.md                  Mandatory operating rules
├── ENGINEERING_PRINCIPLES.md  Six engineering rules
├── verify_credentials.py      Connectivity checks for all external services
├── pyproject.toml             Dependency ranges (source of truth)
└── requirements.txt           Exact pinned lock file
```

## External services

Gemini (via Vertex AI, using Application Default Credentials, no API key), BigQuery, Google Cloud Storage, Earth Engine (AlphaEarth, NAIP, Sentinel-2), Google Solar API, Census ACS, NREL PVWatts. Redis is used for production caching and rate limiting. Local development falls back to a SQLite cache.

## Getting started

Requires Python 3.11+ and Node 20+.

### Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then fill in the keys
gcloud auth application-default login
python verify_credentials.py  # checks every external service
uvicorn api.main:app --reload # http://localhost:8000
```

Environment variables are documented in [.env.example](.env.example). PDF generation uses WeasyPrint, which needs system libraries (Pango, Cairo). See the WeasyPrint install docs for your OS.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev UI talks to the backend at `http://localhost:8000`. Routes: `/` (landing), `/batch`, `/score/:apn`.

### Try it

```bash
curl -X POST http://localhost:8000/api/v1/score-lead \
  -H "Content-Type: application/json" \
  -d '{"address":"100 Long Beach Blvd, Long Beach, CA"}'
```

## Testing

```bash
pytest tests/ -v              # backend
cd frontend && npm run test:run
```

Passing tests are necessary but not enough. Every change also needs a data-quality check that outputs are correct, in the right units and on the right entity (Rule 4 in [CLAUDE.md](CLAUDE.md)).

## Contributing

Read [CLAUDE.md](CLAUDE.md) first. In short:

- Files stay under 100 lines of code, or are exactly one cohesive module.
- Tests must pass before a phase is marked done.
- Never fabricate values. Unknowns surface as `null` with a `source`.
- Regenerate `requirements.txt` with `pip freeze --exclude-editable > requirements.txt` after any dependency change.

## License

Proprietary. © QuantaMind.
