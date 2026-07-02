"""LiveKit token minting."""
from datetime import timedelta

from livekit import api

from app.config import settings


def mint_access_token(room_name: str, identity: str, ttl_hours: int = 6) -> str:
    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_ttl(timedelta(hours=ttl_hours))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )
    return token.to_jwt()
