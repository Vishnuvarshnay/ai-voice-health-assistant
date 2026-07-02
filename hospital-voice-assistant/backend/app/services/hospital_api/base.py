"""Abstract adapter contract for the (future) Hospital Management API.

The core voice-assistant application MUST NOT depend on any concrete hospital
API — endpoint shape, auth, path, method, or payload contract.
It only depends on this interface.

When the hospital API becomes available, add a new adapter (or fill in
`HttpHospitalApiAdapter`) and register it in `factory.get_adapter()`. No
change to the business logic (`intent_classifier`, `voice_agent`, REST
endpoints) is required.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class HospitalApiAdapter(ABC):
    """Abstract port for forwarding a validated service-request JSON to the
    hospital's own downstream system.

    Implementations MUST:
      * be side-effect only (`forward` returns None)
      * be safely awaitable from the voice worker and REST endpoints
      * never raise: transport / auth / validation errors are logged internally

    Implementations MUST NOT:
      * be constructed with hard-coded URLs or credentials
      * mutate the payload dictionary passed in
    """

    name: str = "abstract"

    @abstractmethod
    async def forward(self, payload: dict[str, Any]) -> None:
        """Send the validated service-request JSON downstream.

        The `payload` is the exact dictionary the core app persists to
        Postgres and returns to the frontend — the adapter decides how (or
        whether) to project it onto the hospital's own contract.
        """
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - default no-op
        """Optional teardown hook (e.g. close HTTP client)."""
        return None
