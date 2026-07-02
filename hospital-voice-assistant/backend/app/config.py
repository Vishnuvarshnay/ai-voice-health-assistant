"""Application settings loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # DB
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # LiveKit
    LIVEKIT_URL: str
    LIVEKIT_WS_URL_PUBLIC: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str

    # Deepgram
    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-2-general"
    DEEPGRAM_LANGUAGE: str = "multi"

    # Cartesia
    CARTESIA_API_KEY: str
    CARTESIA_MODEL: str = "sonic-2"
    CARTESIA_VOICE_ID: str = "a0e99841-438c-4a64-b679-ae501e7d6091"

    # Groq
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Intent classifier
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    CONFIDENCE_THRESHOLD: float = 0.85
    FAISS_TOP_K: int = 5

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:4200"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
