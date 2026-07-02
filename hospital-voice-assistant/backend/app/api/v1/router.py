"""API v1 router."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    health,
    intent,
    requests,
    services,
    unknown_requests,
    voice,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router, tags=["health"])
router.include_router(services.router)
router.include_router(intent.router)
router.include_router(voice.router)
router.include_router(requests.router)
router.include_router(unknown_requests.router)
