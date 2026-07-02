"""CRUD for service catalog + FAISS index rebuild."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.startup import rebuild_faiss_from_db
from app.db.session import get_db
from app.repositories.service_repo import ServiceRepo
from app.schemas.dto import HospitalServiceCreate, HospitalServiceOut

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[HospitalServiceOut])
async def list_services(session: AsyncSession = Depends(get_db)):
    repo = ServiceRepo(session)
    services = await repo.list_services()
    return services


@router.post("", response_model=HospitalServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: HospitalServiceCreate, session: AsyncSession = Depends(get_db)
):
    repo = ServiceRepo(session)
    category = await repo.get_or_create_category(
        code=payload.category_code, name=payload.category_code.replace("_", " ").title()
    )
    svc = await repo.upsert_service(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        category_id=category.id,
        example_utterances=payload.example_utterances,
        keywords=payload.keywords,
        required_slots=payload.required_slots,
        priority=payload.priority,
    )
    await session.commit()
    return svc


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(code: str, session: AsyncSession = Depends(get_db)):
    repo = ServiceRepo(session)
    ok = await repo.delete_by_code(code)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Service '{code}' not found")
    await session.commit()


@router.post("/rebuild-index")
async def rebuild_index():
    count = await rebuild_faiss_from_db()
    return {"status": "ok", "indexed": count}
