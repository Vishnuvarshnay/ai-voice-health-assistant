"""Intent classification endpoint (semantic-primary, multilingual)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.orm import UnknownRequest
from app.repositories.request_repo import RequestRepo
from app.schemas.dto import IntentClassifyIn, IntentClassifyOut
from app.services.intent_classifier import STATUS_UNKNOWN, classify

router = APIRouter(prefix="/intent", tags=["intent"])


@router.post("/classify", response_model=IntentClassifyOut)
async def classify_intent(
    payload: IntentClassifyIn, session: AsyncSession = Depends(get_db)
) -> IntentClassifyOut:
    result = await classify(
        session, transcript=payload.transcript, detected_language=payload.detected_language
    )

    # Persist unknown utterances so hospital admins can review + extend the catalog.
    if result.status == STATUS_UNKNOWN:
        top = result.top_candidates[0] if result.top_candidates else None
        unk = UnknownRequest(
            raw_transcript=result.raw_transcript,
            detected_language=result.detected_language,
            top_semantic_score=float(top["semantic_score"]) if top else 0.0,
            top_candidate_code=top["service_code"] if top else None,
        )
        await RequestRepo(session).create_unknown(unk)
        await session.commit()
        logger.info(
            "intent.unknown_persisted",
            transcript=result.raw_transcript[:80],
            top_candidate=unk.top_candidate_code,
        )

    return IntentClassifyOut(
        status=result.status,
        service_code=result.service_code,
        service_name=result.service_name,
        confidence=result.confidence,
        used_fallback=result.used_fallback,
        detected_language=result.detected_language,
        raw_transcript=result.raw_transcript,
        normalized_transcript_en=result.normalized_transcript_en,
        slots=result.slots,
        top_candidates=result.top_candidates,
    )
