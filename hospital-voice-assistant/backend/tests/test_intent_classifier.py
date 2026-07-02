"""Behaviour tests for `HybridIntentClassifier` with mocked ports.

These are the tests that guard the *hard* invariants of the classifier:

  1. Never returns a service_code that isn't in the DB catalog.
  2. Rejects LLM answers that invent a service_code outside the top-K.
  3. Skips the LLM entirely when the semantic confidence already clears
     the accept threshold.
  4. Returns UNKNOWN_SERVICE when the top semantic score is below the
     minimum threshold (the "coconut water vs DRINKING_WATER" guard).
  5. Returns UNKNOWN_SERVICE when the LLM refuses to pick a match.

The classifier is exercised with fake FAISS, rule-engine, and LLM
ports; no BGE-M3, FAISS, or Groq calls are made.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services.intent_classifier import (
    STATUS_MATCHED,
    STATUS_UNKNOWN,
    HybridIntentClassifier,
)


# --------------------------- fakes / stand-ins --------------------------- #

class FakeService:
    def __init__(self, id: int, code: str, name: str,
                 keywords=None, required_slots=None):
        self.id = id
        self.code = code
        self.name = name
        self.keywords = keywords or []
        self.required_slots = required_slots or []


class FakeRepo:
    """Stand-in for `ServiceRepo` — patched into the module via monkeypatch."""

    def __init__(self, catalog: list[FakeService]):
        self._by_id = {s.id: s for s in catalog}
        self._by_code = {s.code: s for s in catalog}

    async def get_by_id(self, sid: int):
        return self._by_id.get(sid)

    async def get_by_code(self, code: str):
        return self._by_code.get(code)


class FakeFaiss:
    def __init__(self, hits: list[dict[str, Any]]):
        self._hits = hits

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return list(self._hits)[:top_k]


@dataclass
class RuleOut:
    keyword_score: float
    matched_keywords: list[str]
    extracted_slots: dict[str, str]


class FakeRuleEngine:
    def __init__(self, keyword_score: float = 0.0,
                 slots: dict[str, str] | None = None):
        self._score = keyword_score
        self._slots = slots or {}

    def evaluate(self, transcript, keywords, required_slots):
        return RuleOut(
            keyword_score=self._score,
            matched_keywords=list(keywords)[: max(1, int(self._score * 3))],
            extracted_slots=dict(self._slots),
        )


class FakeLlm:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.call_count = 0

    async def classify_with_llm(self, transcript_en, catalog):
        self.call_count += 1
        return dict(self.response)

    async def translate_to_english(self, transcript, source_language):  # pragma: no cover
        return transcript


class NeverCalledLlm(FakeLlm):
    async def classify_with_llm(self, transcript_en, catalog):
        self.call_count += 1
        raise AssertionError("LLM must not be called for this test case")


# --------------------------- fixtures ------------------------------------ #

CATALOG = [
    FakeService(1, "ROOM_CLEANING", "Room Cleaning"),
    FakeService(2, "TEA", "Tea"),
    FakeService(3, "AC_NOT_COOLING", "AC Not Cooling"),
]


@pytest.fixture(autouse=True)
def _patch_repo(monkeypatch):
    """Replace `ServiceRepo` in the classifier module with the fake."""
    from app.services import intent_classifier as mod
    monkeypatch.setattr(mod, "ServiceRepo", lambda session: FakeRepo(CATALOG))
    yield


# --------------------------- test cases ---------------------------------- #

@pytest.mark.asyncio
async def test_high_semantic_returns_match_without_calling_llm():
    """Confidence ≥ 0.85 → return match, LLM never invoked."""
    faiss = FakeFaiss([
        {"service_id": 1, "service_code": "ROOM_CLEANING",
         "service_name": "Room Cleaning", "semantic_score": 0.92},
        {"service_id": 2, "service_code": "TEA",
         "service_name": "Tea", "semantic_score": 0.30},
    ])
    llm = NeverCalledLlm({})
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=llm)

    result = await clf.classify(session=None, transcript="please clean my room")

    assert result.status == STATUS_MATCHED
    assert result.service_code == "ROOM_CLEANING"
    assert result.used_fallback is False
    assert result.confidence >= 0.85
    assert llm.call_count == 0


@pytest.mark.asyncio
async def test_low_semantic_below_min_threshold_returns_unknown_without_llm():
    """Top semantic < MIN_SEMANTIC_THRESHOLD → UNKNOWN, no LLM call."""
    faiss = FakeFaiss([
        {"service_id": 2, "service_code": "TEA",
         "service_name": "Tea", "semantic_score": 0.20},
    ])
    llm = NeverCalledLlm({})
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=llm)

    result = await clf.classify(session=None, transcript="I need coconut water")

    assert result.status == STATUS_UNKNOWN
    assert result.service_code is None
    assert llm.call_count == 0


@pytest.mark.asyncio
async def test_llm_invented_service_is_rejected():
    """LLM returns a code not in the top-K subset → UNKNOWN."""
    faiss = FakeFaiss([
        {"service_id": 2, "service_code": "TEA",
         "service_name": "Tea", "semantic_score": 0.55},
    ])
    llm = FakeLlm({
        "service_code": "MASSAGE_THERAPY",  # never existed
        "confidence": 0.95,
        "slots": {},
    })
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=llm)

    result = await clf.classify(session=None, transcript="I want tea maybe")

    assert result.status == STATUS_UNKNOWN
    assert result.service_code is None
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_llm_refusal_returns_unknown():
    """LLM returns service_code=null → UNKNOWN."""
    faiss = FakeFaiss([
        {"service_id": 2, "service_code": "TEA",
         "service_name": "Tea", "semantic_score": 0.55},
    ])
    llm = FakeLlm({"service_code": None, "confidence": 0.10, "slots": {}})
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=llm)

    result = await clf.classify(session=None,
                                transcript="do you have wifi passwords")

    assert result.status == STATUS_UNKNOWN
    assert result.service_code is None


@pytest.mark.asyncio
async def test_llm_promotes_borderline_candidate():
    """Semantic in the 0.35–0.85 band → LLM picks the correct top-K code."""
    faiss = FakeFaiss([
        {"service_id": 3, "service_code": "AC_NOT_COOLING",
         "service_name": "AC Not Cooling", "semantic_score": 0.60},
        {"service_id": 2, "service_code": "TEA",
         "service_name": "Tea", "semantic_score": 0.55},
    ])
    llm = FakeLlm({
        "service_code": "AC_NOT_COOLING",
        "confidence": 0.90,
        "slots": {"room_number": "204"},
    })
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=llm)

    result = await clf.classify(session=None,
                                transcript="the room is warm in 204")

    assert result.status == STATUS_MATCHED
    assert result.service_code == "AC_NOT_COOLING"
    assert result.used_fallback is True
    assert result.slots.get("room_number") == "204"
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_faiss_hit_for_deleted_service_is_ignored():
    """If FAISS returns a service_id no longer in the DB → skip it."""
    faiss = FakeFaiss([
        # Not in CATALOG:
        {"service_id": 999, "service_code": "GHOST_SERVICE",
         "service_name": "Ghost", "semantic_score": 0.99},
        {"service_id": 1, "service_code": "ROOM_CLEANING",
         "service_name": "Room Cleaning", "semantic_score": 0.90},
    ])
    clf = HybridIntentClassifier(faiss=faiss, rule_engine=FakeRuleEngine(),
                                 llm=NeverCalledLlm({}))

    result = await clf.classify(session=None, transcript="clean my room")

    assert result.status == STATUS_MATCHED
    assert result.service_code == "ROOM_CLEANING"
