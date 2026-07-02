"""Persist confirmed service requests."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.orm import ServiceRequest
from app.repositories.request_repo import RequestRepo
from app.repositories.service_repo import ServiceRepo
from app.schemas.dto import ServiceRequestIn, ServiceRequestOut
from app.services import hospital_api

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("", response_model=list[ServiceRequestOut])
async def list_requests(session: AsyncSession = Depends(get_db)):
    repo = RequestRepo(session)
    return await repo.list_requests()


@router.post("", response_model=ServiceRequestOut)
async def create_request(
    payload: ServiceRequestIn, session: AsyncSession = Depends(get_db)
):
    svc_repo = ServiceRepo(session)
    svc = await svc_repo.get_by_code(payload.service_code)
    if svc is None:
        raise HTTPException(
            status_code=404, detail=f"Service '{payload.service_code}' not found"
        )
    req = ServiceRequest(
        session_id=payload.session_id,
        service_id=svc.id,
        raw_transcript=payload.raw_transcript,
        normalized_transcript_en=payload.normalized_transcript_en,
        detected_language=payload.detected_language,
        confidence=payload.confidence,
        used_fallback=payload.used_fallback,
        payload=payload.payload,
    )
    repo = RequestRepo(session)
    req = await repo.create_request(req)
    await session.commit()
    await session.refresh(req)

    # Optional webhook to the hospital API (no-op when unset).
    try:
        await hospital_api.forward(
            {
                "service_code": svc.code,
                "service_name": svc.name,
                "priority": svc.priority,
                "raw_transcript": payload.raw_transcript,
                "normalized_transcript_en": payload.normalized_transcript_en,
                "detected_language": payload.detected_language,
                "confidence": payload.confidence,
                "used_fallback": payload.used_fallback,
                **payload.payload,
            }
        )
    except Exception:
        pass  # non-fatal - failure is already logged inside forward()

    return req
