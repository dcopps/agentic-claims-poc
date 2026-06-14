from fastapi import APIRouter

from backend.app.api.pipeline import pipeline_router

# Top-level API router. Sub-routers (pipeline, and future claims/audit) mount
# here under the /api prefix.
api_router = APIRouter(prefix="/api")
api_router.include_router(pipeline_router)
