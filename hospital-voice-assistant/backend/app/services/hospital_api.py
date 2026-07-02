"""Optional webhook forwarder: POSTs confirmed service-request JSON to the
hospital's own API.

Enabled when `HOSPITAL_API_URL` is set in the environment. Silent no-op
otherwise so the project runs standalone during development.
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.logging import logger


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=5))
async def forward(payload: dict) -> None:
    url = settings.HOSPITAL_API_URL
    if not url:
        return  # feature disabled

    headers = {"Content-Type": "application/json"}
    if settings.HOSPITAL_API_KEY:
        headers["Authorization"] = f"Bearer {settings.HOSPITAL_API_KEY}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logger.info(
            "hospital_api.forwarded",
            url=url,
            status=resp.status_code,
            service_code=payload.get("service_code"),
        )
