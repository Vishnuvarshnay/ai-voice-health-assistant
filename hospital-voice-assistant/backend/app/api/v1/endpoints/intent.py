"""Intent classification endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.dto import IntentClassifyIn, IntentClassifyOut
from app.services.intent_classifier import classify

router = APIRouter(prefix="/intent", tags=["intent"])


@router.post("/classify", response_model=IntentClassifyOut)
async def classify_intent(
    payload: IntentClassifyIn, session: AsyncSession = Depends(get_db)
) -> IntentClassifyOut:
    result = await classify(
        session, transcript=payload.transcript, detected_language=payload.detected_language
    )
    return IntentClassifyOut(
        service_code=result.service_code,
        service_name=result.service_name,
        confidence=result.confidence,
        used_fallback=result.used_fallback,
        detected_language=result.detected_language,
        normalized_transcript_en=result.normalized_transcript_en,
        slots=result.slots,
        top_candidates=result.top_candidates,
    )
