"""Data-access for persisted service requests + voice sessions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import ServiceRequest, UnknownRequest, VoiceSession


class RequestRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self, room_name: str, identity: str, detected_language: str | None = None
    ) -> VoiceSession:
        vs = VoiceSession(
            room_name=room_name, identity=identity, detected_language=detected_language
        )
        self.session.add(vs)
        await self.session.flush()
        return vs

    async def get_session_by_room(self, room_name: str) -> VoiceSession | None:
        result = await self.session.execute(
            select(VoiceSession).where(VoiceSession.room_name == room_name)
        )
        return result.scalar_one_or_none()

    async def create_request(self, req: ServiceRequest) -> ServiceRequest:
        self.session.add(req)
        await self.session.flush()
        return req

    async def list_requests(self, limit: int = 50) -> list[ServiceRequest]:
        result = await self.session.execute(
            select(ServiceRequest).order_by(ServiceRequest.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def create_unknown(self, unk: UnknownRequest) -> UnknownRequest:
        self.session.add(unk)
        await self.session.flush()
        return unk

    async def list_unknowns(
        self, limit: int = 50, status: str | None = "pending"
    ) -> list[UnknownRequest]:
        stmt = select(UnknownRequest).order_by(UnknownRequest.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(UnknownRequest.review_status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
