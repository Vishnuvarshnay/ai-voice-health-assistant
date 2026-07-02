"""Skeleton adapter for a future hospital HTTP API.

This class is intentionally a STUB. It exists so the wiring, config keys
and factory selection are in place — but it does NOT assume any endpoint
path, method, request/response shape, or auth scheme, because those are
owned by the hospital-management team and are not yet defined.

To activate when the hospital API is available:
  1. Fill in the body of `forward()` per the hospital's API contract.
  2. Set `HOSPITAL_API_URL` (+ optional `HOSPITAL_API_KEY`) in `.env`.
No change to `intent_classifier`, `voice_agent`, or REST endpoints required.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.core.logging import logger
from app.services.hospital_api.base import HospitalApiAdapter


class HttpHospitalApiAdapter(HospitalApiAdapter):
    """Placeholder for the future HTTP integration."""

    name = "http"

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        # Nothing is assumed about the URL shape or auth mechanism; the values
        # are simply held for whoever fills in `forward()` later.
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or None

    async def forward(self, payload: dict[str, Any]) -> None:  # pragma: no cover
        # Intentionally not implemented — waiting on the hospital API contract.
        # When the contract is known:
        #   * pick the right endpoint path (e.g. POST /requests)
        #   * translate `payload` to whatever field names the hospital expects
        #   * add auth headers per their spec (Bearer, HMAC, mTLS, etc.)
        #   * decide retry/backoff and idempotency semantics
        logger.warning(
            "hospital_api.http_adapter.stub_invoked",
            base_url=self._base_url,
            service_code=payload.get("service_code"),
            note=(
                "HttpHospitalApiAdapter is a stub. Implement forward() once "
                "the hospital API contract is finalized."
            ),
        )
        _ = settings  # silence unused-import warnings
