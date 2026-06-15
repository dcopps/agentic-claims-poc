from fastapi import APIRouter

from backend.app.api.agents_test import agents_test_router
from backend.app.api.audit import audit_router
from backend.app.api.claims import claims_router
from backend.app.api.human import human_router
from backend.app.api.pipeline import pipeline_router
from backend.app.api.runs import runs_router

# Top-level API router. Sub-routers mount here under the /api prefix.
api_router = APIRouter(prefix="/api")
api_router.include_router(pipeline_router)
api_router.include_router(claims_router)
api_router.include_router(runs_router)
api_router.include_router(audit_router)
api_router.include_router(human_router)
api_router.include_router(agents_test_router)
