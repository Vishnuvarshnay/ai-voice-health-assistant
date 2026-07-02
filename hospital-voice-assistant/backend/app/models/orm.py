"""ORM models for the hospital voice assistant."""
from datetime import datetime, timezone

from sqlalchemy import ARRAY, JSON, Float, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    services: Mapped[list["HospitalService"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class HospitalService(Base):
    __tablename__ = "hospital_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("service_categories.id"))

    # Sample utterances used for embedding + FAISS index
    example_utterances: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Keyword rules the rule engine matches on (lowercase substrings)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Required data slots to be extracted from the utterance
    required_slots: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Priority handled downstream by hospital workflows
    priority: Mapped[str] = mapped_column(String(16), default="normal")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    category: Mapped[ServiceCategory] = relationship(back_populates="services")


class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    identity: Mapped[str] = mapped_column(String(128))
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    requests: Mapped[list["ServiceRequest"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("voice_sessions.id"), nullable=True
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("hospital_services.id"))
    raw_transcript: Mapped[str] = mapped_column(Text)
    normalized_transcript_en: Mapped[str] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    used_fallback: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[VoiceSession | None] = relationship(back_populates="requests")


class UnknownRequest(Base):
    """Utterances that could not be mapped to any catalog service.

    Stored so hospital administrators can review and extend the catalog.
    """
    __tablename__ = "unknown_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("voice_sessions.id"), nullable=True
    )
    raw_transcript: Mapped[str] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    top_semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    top_candidate_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
