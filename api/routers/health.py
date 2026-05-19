"""GET /health — liveness + Phase 4 observability surface.

Returns a status snapshot:
  - status: "healthy" (top-level liveness probe — unchanged from Phase 0)
  - cache_hit_rate_per_service_last_1h: rolling per-service hit rate
  - rate_limit_headroom_per_service: remaining burst + concurrency room
  - bigquery_write_success_rate_last_1h: how often api_cache writes are
    landing (None when no writes recorded in the window)

In-process metrics — each uvicorn worker has its own view. For
cluster-wide rates, sum across workers in your monitoring system.
"""
from fastapi import APIRouter

from api.middleware import rate_limiter, ttl_cache

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "cache_hit_rate_per_service_last_1h": ttl_cache.hit_rates(),
        "rate_limit_headroom_per_service": rate_limiter.headroom(),
        "bigquery_write_success_rate_last_1h": ttl_cache.bq_success_rate(),
    }
