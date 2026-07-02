"""Seed the service catalog from `default_services.json` and rebuild the FAISS index.

Usage (inside the backend container):

    python -m app.seed.seed_services
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.logging import configure_logging, logger
from app.core.startup import rebuild_faiss_from_db
from app.db.session import AsyncSessionLocal
from app.repositories.service_repo import ServiceRepo
from app.services.embedding_service import embedding_service


DATA_FILE = Path(__file__).parent / "default_services.json"


CATEGORY_NAMES = {
    "CLEANING": "Cleaning",
    "AC": "AC Issues",
    "TV": "TV Issues",
    "LAUNDRY": "Laundry",
    "ELECTRICAL": "Electrical",
    "MAINTENANCE": "Maintenance",
    "PATIENT_SUPPORT": "Patient Support",
    "PATIENT_DIET": "Patient Diet",
    "SERVICE_COMPLAINT": "Service Complaint",
}


async def seed() -> None:
    configure_logging()
    logger.info("seed.start", file=str(DATA_FILE))
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as session:
        repo = ServiceRepo(session)
        for row in data:
            cat_code = row["category_code"]
            cat = await repo.get_or_create_category(
                code=cat_code, name=CATEGORY_NAMES.get(cat_code, cat_code.title())
            )
            await repo.upsert_service(
                code=row["code"],
                name=row["name"],
                description=row["description"],
                category_id=cat.id,
                example_utterances=row.get("example_utterances", []),
                keywords=row.get("keywords", []),
                required_slots=row.get("required_slots", []),
                priority=row.get("priority", "normal"),
            )
        await session.commit()

    logger.info("seed.services_loaded", count=len(data))
    await embedding_service.load()
    indexed = await rebuild_faiss_from_db()
    logger.info("seed.done", indexed=indexed)


if __name__ == "__main__":
    asyncio.run(seed())
