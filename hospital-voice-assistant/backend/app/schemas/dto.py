"""Pydantic DTOs for API surface."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ServiceCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: Optional[str] = None


class ServiceCategoryCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class HospitalServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str
    category_id: int
    example_utterances: list[str] = []
    keywords: list[str] = []
    required_slots: list[str] = []
    priority: str = "normal"


class HospitalServiceCreate(BaseModel):
    code: str
    name: str
    description: str
    category_code: str
    example_utterances: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    required_slots: list[str] = Field(default_factory=list)
    priority: str = "normal"


class IntentClassifyIn(BaseModel):
    transcript: str = Field(..., min_length=1)
    detected_language: Optional[str] = None


class IntentSlots(BaseModel):
    model_config = ConfigDict(extra="allow")


class IntentClassifyOut(BaseModel):
    status: str  # "MATCHED" | "UNKNOWN_SERVICE"
    service_code: Optional[str]
    service_name: Optional[str]
    confidence: float
    used_fallback: bool
    detected_language: Optional[str]
    raw_transcript: str
    normalized_transcript_en: str
    slots: dict = {}
    top_candidates: list[dict] = []


class VoiceTokenIn(BaseModel):
    room_name: str
    identity: str


class VoiceTokenOut(BaseModel):
    token: str
    url: str
    room_name: str
    identity: str


class ServiceRequestIn(BaseModel):
    session_id: Optional[int] = None
    service_code: str
    raw_transcript: str
    normalized_transcript_en: str
    detected_language: Optional[str] = None
    confidence: float
    used_fallback: bool = False
    payload: dict = Field(default_factory=dict)


class ServiceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    raw_transcript: str
    normalized_transcript_en: str
    detected_language: Optional[str] = None
    confidence: float
    used_fallback: bool
    payload: dict
    created_at: datetime
