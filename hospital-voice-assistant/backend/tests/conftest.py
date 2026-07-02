"""Provide minimal environment variables for tests.

The core `Settings` model fails fast when required keys are missing (by
design — see config.py). At test-time we inject dummies BEFORE the app
is imported so the test suite can exercise pure business logic without
docker or real API keys.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost:5432/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("LIVEKIT_URL", "ws://livekit:7880")
os.environ.setdefault("LIVEKIT_WS_URL_PUBLIC", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "test")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-secret-test-secret-test-secret")
os.environ.setdefault("DEEPGRAM_API_KEY", "test")
os.environ.setdefault("CARTESIA_API_KEY", "test")
os.environ.setdefault("GROQ_API_KEY", "test")
