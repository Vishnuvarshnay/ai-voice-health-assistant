"""Health + readiness endpoints."""
from fastapi import APIRouter

from app.services.embedding_service import embedding_service
from app.services.faiss_index import faiss_index

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    return {
        "status": "ok" if embedding_service._model is not None and faiss_index.size > 0 else "warming",
        "embedding_loaded": embedding_service._model is not None,
        "faiss_size": faiss_index.size,
    }
