"""Adapter factory + module-level singleton.

Selection rule (kept intentionally simple):
  * If `HOSPITAL_API_URL` is unset  →  NullHospitalApiAdapter (no-op)
  * If `HOSPITAL_API_URL` is set    →  HttpHospitalApiAdapter (stub today)

The core application only imports `hospital_api_adapter` from this module.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.services.hospital_api.base import HospitalApiAdapter
from app.services.hospital_api.http_adapter import HttpHospitalApiAdapter
from app.services.hospital_api.null_adapter import NullHospitalApiAdapter


@lru_cache
def get_adapter() -> HospitalApiAdapter:
    if settings.HOSPITAL_API_URL.strip():
        return HttpHospitalApiAdapter(
            base_url=settings.HOSPITAL_API_URL.strip(),
            api_key=settings.HOSPITAL_API_KEY.strip() or None,
        )
    return NullHospitalApiAdapter()


# Convenience singleton for imports elsewhere.
hospital_api_adapter: HospitalApiAdapter = get_adapter()


__all__ = ["HospitalApiAdapter", "get_adapter", "hospital_api_adapter"]
