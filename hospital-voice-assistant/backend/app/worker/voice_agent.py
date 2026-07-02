"""LiveKit voice agent worker.

Joins every LiveKit room, greets the patient in <500ms, streams Deepgram STT,
classifies each finalized utterance via the hybrid intent pipeline, and speaks
a Cartesia TTS confirmation back to the patient.

Run:

    python -m app.worker.voice_agent
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.plugins import cartesia, deepgram, silero

from app.config import settings
from app.core.logging import configure_logging, latency, logger
from app.db.session import AsyncSessionLocal
from app.models.orm import ServiceRequest
from app.repositories.request_repo import RequestRepo
from app.repositories.service_repo import ServiceRepo
from app.services import hospital_api
from app.services.embedding_service import embedding_service
from app.services.intent_classifier import classify
from app.core.startup import rebuild_faiss_from_db


GREETING_EN = (
    "Hello, I'm your hospital assistant. How may I help you today? "
    "You can speak in any language."
)


class HospitalAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You confirm what service the patient requested. "
                "Always speak in English. Keep answers to a single short sentence."
            ),
        )


async def _handle_transcript(transcript: str, room_name: str, identity: str) -> str:
    """Run the hybrid intent pipeline for one final transcript and persist it."""
    if not transcript.strip():
        return "Sorry, I didn't catch that. Could you repeat?"

    async with AsyncSessionLocal() as session:
        with latency("worker.classify", transcript_len=len(transcript)):
            result = await classify(session, transcript=transcript)

        if not result.service_code:
            return (
                "I couldn't identify a matching hospital service. "
                "Could you rephrase your request?"
            )

        svc_repo = ServiceRepo(session)
        svc = await svc_repo.get_by_code(result.service_code)
        if svc is None:
            return "Sorry, that service isn't available right now."

        req_repo = RequestRepo(session)
        vs = await req_repo.get_session_by_room(room_name) or await req_repo.create_session(
            room_name=room_name, identity=identity, detected_language=result.detected_language
        )

        payload: dict[str, Any] = {
            "service_code": svc.code,
            "service_name": svc.name,
            "category": svc.category.code if svc.category else None,
            "priority": svc.priority,
            "slots": result.slots,
            "confidence": result.confidence,
            "used_fallback": result.used_fallback,
        }
        req = ServiceRequest(
            session_id=vs.id,
            service_id=svc.id,
            raw_transcript=transcript,
            normalized_transcript_en=result.normalized_transcript_en,
            detected_language=result.detected_language,
            confidence=result.confidence,
            used_fallback=result.used_fallback,
            payload=payload,
        )
        await req_repo.create_request(req)
        await session.commit()

        logger.info(
            "worker.request_persisted",
            room=room_name,
            service=svc.code,
            confidence=result.confidence,
            used_fallback=result.used_fallback,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )

        # Optional: forward to the hospital's own API (no-op if unset).
        try:
            await hospital_api.forward(
                {
                    "room_name": room_name,
                    "identity": identity,
                    "raw_transcript": transcript,
                    "normalized_transcript_en": result.normalized_transcript_en,
                    "detected_language": result.detected_language,
                    **payload,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("worker.hospital_api.failed", error=str(exc))
        return (
            f"Got it. I've placed a {svc.name.lower()} request for you. "
            "A team member will attend shortly."
        )


async def entrypoint(ctx: JobContext) -> None:
    configure_logging()
    logger.info("worker.job.start", room=ctx.room.name)

    # Warm ML components (cheap after first load thanks to module-level singletons).
    await embedding_service.load()
    if 0 == 1:  # index is (re)built on FastAPI startup and by the seed script
        await rebuild_faiss_from_db()

    session = AgentSession(
        stt=deepgram.STT(
            api_key=settings.DEEPGRAM_API_KEY,
            model=settings.DEEPGRAM_MODEL,
            language=settings.DEEPGRAM_LANGUAGE,
            interim_results=True,
            smart_format=True,
        ),
        tts=cartesia.TTS(
            api_key=settings.CARTESIA_API_KEY,
            model=settings.CARTESIA_MODEL,
            voice=settings.CARTESIA_VOICE_ID,
        ),
        vad=silero.VAD.load(),
    )

    @session.on("user_input_transcribed")
    def _on_transcribed(ev):
        if not getattr(ev, "is_final", False):
            return
        transcript = getattr(ev, "transcript", "") or ""
        logger.info("worker.stt.final", transcript=transcript)
        # Handle asynchronously so we don't block the STT loop.
        asyncio.create_task(_respond(session, transcript, ctx))

    async def _respond(sess: AgentSession, transcript: str, ctx: JobContext) -> None:
        identity = "patient"
        try:
            for p in ctx.room.remote_participants.values():
                identity = p.identity
                break
        except Exception:
            pass

        reply = await _handle_transcript(transcript, ctx.room.name, identity)
        await sess.say(reply, allow_interruptions=True)

    await session.start(
        room=ctx.room,
        agent=HospitalAssistant(),
        room_input_options=RoomInputOptions(),
    )

    # Greet immediately for the <500ms SLA (Cartesia streams first audio chunk fast).
    with latency("worker.greeting"):
        await session.say(GREETING_EN, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
