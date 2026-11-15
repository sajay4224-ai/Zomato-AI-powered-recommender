import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import RecommendationResponse, RequestPreferences
from app.services.orchestration import RecommendationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("zomato_ai")

settings = get_settings()
app = FastAPI(title=settings.app_name)
service = RecommendationService(settings)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


@app.get("/", response_class=FileResponse)
async def home() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "templates" / "index.html")


@app.get("/api/options")
async def recommendation_options() -> dict[str, list[str]]:
    if service.catalog_error or not service.catalog.restaurants:
        detail = service.catalog_error or "The restaurant catalog is empty or unavailable."
        raise HTTPException(status_code=503, detail=detail)

    locations: dict[str, str] = {}
    cuisines: dict[str, str] = {}
    for restaurant in service.catalog.restaurants:
        for value in (restaurant.city, restaurant.location):
            if value and value.strip():
                cleaned = " ".join(value.split())
                locations.setdefault(cleaned.casefold(), cleaned)
        for cuisine in restaurant.cuisines:
            if cuisine and cuisine.strip():
                cleaned = " ".join(cuisine.split())
                cuisines.setdefault(cleaned.casefold(), cleaned)

    return {
        "locations": sorted(locations.values(), key=str.casefold),
        "cuisines": sorted(cuisines.values(), key=str.casefold),
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
async def ready() -> dict[str, str | bool]:
    ready_state = service.is_ready
    logger.info("Readiness check: %s (catalog_loaded=%s)", ready_state, ready_state)
    return {
        "status": "ready" if ready_state else "not_ready",
        "service": settings.app_name,
        "catalog_loaded": ready_state,
    }


@app.post("/api/recommend", response_model=RecommendationResponse)
async def recommend(request: RequestPreferences) -> RecommendationResponse:
    return service.generate(request)
