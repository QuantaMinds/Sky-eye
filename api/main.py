"""FastAPI application entrypoint + lifespan wiring.

Phase 4 startup hook ensures the BigQuery api_cache table exists before
serving traffic. Failure to bootstrap does NOT block startup — the
CREATE TABLE IF NOT EXISTS DDL is idempotent and will retry on first
write. We log loud so a deploy-time IAM issue is visible without
silently breaking the prod cache.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.middleware import _bq_cache
from api.routers import batch, health, lead_score, narrative as narrative_router, reports

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap the BQ cache table before traffic, tolerate failure.

    The CREATE TABLE IF NOT EXISTS is idempotent — running it on every
    worker startup is harmless. If BQ is unreachable at startup (IAM
    hiccup, transient outage), we log + continue: writes will lazy-create
    on first hit. Crashing on startup would be worse than degraded
    caching.
    """
    try:
        await _bq_cache.ensure_table()
        logger.info("api_cache table ensured (leadlens.api_cache)")
    except Exception as exc:  # noqa: BLE001 — startup must continue
        logger.warning(
            "ensure_table() failed at startup: %s. "
            "Cache writes will attempt to recover lazily.",
            exc,
        )
    yield
    # No teardown — Redis client is process-local and dies with the worker.


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Rooftop solar lead intelligence platform",
    lifespan=lifespan,
)

# Dev-time CORS: the Vite frontend at :5173 (or 127.0.0.1:5173) makes
# cross-origin XHR to this backend at :8000. Without this middleware the
# preflight OPTIONS returns 405 and the browser blocks the POST. Tighten
# / remove this list when fronted by a reverse proxy in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(lead_score.router)
app.include_router(batch.router)
app.include_router(narrative_router.router)
app.include_router(reports.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}
