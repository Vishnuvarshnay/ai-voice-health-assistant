"""Default adapter used while the hospital API is not yet available.

The voice assistant remains fully functional: the validated JSON is already
persisted to Postgres and returned to the frontend by the caller. This adapter
simply logs the forward-intent for observability and returns.

DO NOT hardcode any hospital-specific behavior here.
"""
from __future__ import annotations

from typing import Any

from app.core.logging import logger
from app.services.hospital_api.base import HospitalApiAdapter


class NullHospitalApiAdapter(HospitalApiAdapter):
    """No-op adapter — the default when no hospital API is configured."""

    name = "null"

    async def forward(self, payload: dict[str, Any]) -> None:
        logger.info(
            "hospital_api.null_adapter.skipped",
            service_code=payload.get("service_code"),
            reason="HOSPITAL_API_URL not configured — request stored locally only",
        )
