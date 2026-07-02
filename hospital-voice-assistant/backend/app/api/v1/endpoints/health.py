"""Health + readiness endpoints (/healthz, /readyz)."""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.services.embedding_service import embedding_service
from app.services.faiss_index import faiss_index

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    """Process liveness — no external calls."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness — verifies Postgres, Redis and ML components."""
    checks: dict[str, dict] = {}
    ready = True

    # PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = {"ok": False, "error": str(exc)}
        ready = False

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        pong = await r.ping()
        await r.aclose()
        checks["redis"] = {"ok": bool(pong)}
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = {"ok": False, "error": str(exc)}
        ready = False

    # Embedding model
    model_loaded = embedding_service._model is not None
    checks["embedding_model"] = {"ok": model_loaded, "name": settings.EMBEDDING_MODEL}
    if not model_loaded:
        ready = False

    # FAISS index
    checks["faiss_index"] = {"ok": faiss_index.size > 0, "size": faiss_index.size}
    if faiss_index.size == 0:
        ready = False

    body = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(
        content=body,
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
