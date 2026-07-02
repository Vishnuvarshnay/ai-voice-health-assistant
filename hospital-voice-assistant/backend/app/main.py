"""FastAPI entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.logging import configure_logging, logger
from app.core.startup import load_ml_components


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("app.startup.begin", env=settings.APP_ENV)
    await load_ml_components()
    logger.info("app.startup.ready")
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="Hospital AI Voice Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "hospital-voice-assistant",
        "version": "1.0.0",
        "docs": "/docs",
    }
