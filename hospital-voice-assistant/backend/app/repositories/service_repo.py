"""Data-access layer for hospital services."""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import HospitalService, ServiceCategory


class ServiceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_categories(self) -> Sequence[ServiceCategory]:
        result = await self.session.execute(select(ServiceCategory))
        return result.scalars().all()

    async def get_or_create_category(
        self, code: str, name: str, description: str | None = None
    ) -> ServiceCategory:
        result = await self.session.execute(
            select(ServiceCategory).where(ServiceCategory.code == code)
        )
        cat = result.scalar_one_or_none()
        if cat is not None:
            return cat
        cat = ServiceCategory(code=code, name=name, description=description)
        self.session.add(cat)
        await self.session.flush()
        return cat

    async def list_services(self) -> Sequence[HospitalService]:
        result = await self.session.execute(
            select(HospitalService).options(selectinload(HospitalService.category))
        )
        return result.scalars().all()

    async def get_by_id(self, service_id: int) -> HospitalService | None:
        return await self.session.get(HospitalService, service_id)

    async def get_by_code(self, code: str) -> HospitalService | None:
        result = await self.session.execute(
            select(HospitalService).where(HospitalService.code == code)
        )
        return result.scalar_one_or_none()

    async def upsert_service(
        self,
        code: str,
        name: str,
        description: str,
        category_id: int,
        example_utterances: list[str],
        keywords: list[str],
        required_slots: list[str],
        priority: str = "normal",
    ) -> HospitalService:
        svc = await self.get_by_code(code)
        if svc is None:
            svc = HospitalService(code=code, category_id=category_id)
            self.session.add(svc)
        svc.name = name
        svc.description = description
        svc.category_id = category_id
        svc.example_utterances = list(example_utterances)
        svc.keywords = list(keywords)
        svc.required_slots = list(required_slots)
        svc.priority = priority
        await self.session.flush()
        return svc

    async def delete_by_code(self, code: str) -> bool:
        svc = await self.get_by_code(code)
        if svc is None:
            return False
        await self.session.delete(svc)
        return True
