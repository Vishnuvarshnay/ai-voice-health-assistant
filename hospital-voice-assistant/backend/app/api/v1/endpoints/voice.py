"""LiveKit token minting + WebSocket URL discovery."""
from fastapi import APIRouter

from app.config import settings
from app.schemas.dto import VoiceTokenIn, VoiceTokenOut
from app.services.livekit_service import mint_access_token

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/token", response_model=VoiceTokenOut)
async def mint_token(payload: VoiceTokenIn) -> VoiceTokenOut:
    token = mint_access_token(payload.room_name, payload.identity)
    return VoiceTokenOut(
        token=token,
        url=settings.LIVEKIT_WS_URL_PUBLIC,
        room_name=payload.room_name,
        identity=payload.identity,
    )
