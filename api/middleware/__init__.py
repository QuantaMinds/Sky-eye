"""Phase 4 middleware: production-quality caching + rate limiting.

Two modules:
  - rate_limiter: sliding-window + concurrency caps + token counters per service
  - ttl_cache:    Redis (hot) -> BigQuery (cold) with per-service TTL policy

Both expose headroom / hit-rate metrics consumed by the /health endpoint.
"""
