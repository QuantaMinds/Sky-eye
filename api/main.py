from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers import batch, health, lead_score, narrative as narrative_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Rooftop solar lead intelligence platform",
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


@app.get("/")
def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}
