"""Admin: list unknown utterances awaiting review."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.orm import UnknownRequest
from app.repositories.request_repo import RequestRepo

router = APIRouter(prefix="/unknown-requests", tags=["unknown-requests"])


class UnknownRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    raw_transcript: str
    detected_language: Optional[str] = None
    top_semantic_score: float
    top_candidate_code: Optional[str] = None
    review_status: str
    created_at: datetime


class UnknownReviewIn(BaseModel):
    review_status: str  # e.g. "pending", "reviewed", "added_to_catalog", "ignored"


@router.get("", response_model=list[UnknownRequestOut])
async def list_unknowns(
    session: AsyncSession = Depends(get_db),
    status: Optional[str] = Query("pending"),
    limit: int = Query(50, ge=1, le=500),
):
    repo = RequestRepo(session)
    return await repo.list_unknowns(limit=limit, status=status)


@router.patch("/{unknown_id}", response_model=UnknownRequestOut)
async def update_review_status(
    unknown_id: int,
    body: UnknownReviewIn,
    session: AsyncSession = Depends(get_db),
):
    unk = await session.get(UnknownRequest, unknown_id)
    if unk is None:
        raise HTTPException(status_code=404, detail="Unknown request not found")
    unk.review_status = body.review_status
    await session.commit()
    await session.refresh(unk)
    return unk
