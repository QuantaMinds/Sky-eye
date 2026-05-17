from fastapi import FastAPI

from app.config import get_settings
from app.routers import health

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Rooftop solar lead intelligence platform",
)

app.include_router(health.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}
