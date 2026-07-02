"""Startup lifecycle: load embedding model, build FAISS index, warm DB."""
from __future__ import annotations

from sqlalchemy import select

from app.core.logging import latency, logger
from app.db.session import AsyncSessionLocal
from app.models.orm import HospitalService
from app.services.embedding_service import embedding_service
from app.services.faiss_index import IndexedUtterance, faiss_index


async def load_ml_components() -> None:
    with latency("startup.embedding_load"):
        await embedding_service.load()
    await rebuild_faiss_from_db()


async def rebuild_faiss_from_db() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(HospitalService))
        services = result.scalars().all()

    entries: list[IndexedUtterance] = []
    for svc in services:
        # Always index the service name + description as an anchor.
        anchor_texts = [svc.name, svc.description] + list(svc.example_utterances or [])
        for utt in anchor_texts:
            if utt and utt.strip():
                entries.append(
                    IndexedUtterance(
                        service_id=svc.id,
                        service_code=svc.code,
                        service_name=svc.name,
                        utterance=utt.strip(),
                    )
                )
    with latency("startup.faiss_build", entries=len(entries)):
        await faiss_index.build(entries)
    logger.info("startup.faiss_ready", size=faiss_index.size)
    return len(entries)
