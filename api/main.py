from fastapi import FastAPI

from api.config import get_settings
from api.routers import batch, health, lead_score, narrative as narrative_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Rooftop solar lead intelligence platform",
)

app.include_router(health.router)
app.include_router(lead_score.router)
app.include_router(batch.router)
app.include_router(narrative_router.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}
