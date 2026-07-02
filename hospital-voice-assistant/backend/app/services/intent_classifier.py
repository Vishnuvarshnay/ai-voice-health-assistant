"""Hybrid intent classifier: semantic (FAISS) + rule engine + optional LLM fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langdetect import DetectorFactory, detect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import latency, logger
from app.repositories.service_repo import ServiceRepo
from app.services import llm_fallback, rule_engine
from app.services.faiss_index import faiss_index

DetectorFactory.seed = 0  # deterministic language detection


SEMANTIC_WEIGHT = 1.0        # semantic similarity IS the primary confidence
KEYWORD_BOOST_MAX = 0.10     # keywords contribute at most a +0.10 nudge
KEYWORD_BOOST_CAP = 0.99     # boosted semantic score never claims certainty


@dataclass
class ClassifyResult:
    service_code: str | None
    service_name: str | None
    service_id: int | None
    confidence: float
    used_fallback: bool
    detected_language: str | None
    normalized_transcript_en: str
    slots: dict[str, Any]
    top_candidates: list[dict[str, Any]]


def _safe_detect_language(text: str) -> str | None:
    try:
        return detect(text)
    except Exception:  # pragma: no cover - langdetect can throw on very short strings
        return None


async def classify(
    session: AsyncSession,
    transcript: str,
    detected_language: str | None = None,
) -> ClassifyResult:
    with latency("intent.classify", transcript_len=len(transcript)):
        lang = detected_language or _safe_detect_language(transcript)

        # Normalize to English so downstream JSON payload is always English.
        if lang and not lang.lower().startswith("en"):
            with latency("intent.translate", src_lang=lang):
                transcript_en = await llm_fallback.translate_to_english(transcript, lang)
        else:
            transcript_en = transcript

        # Semantic top-K over FAISS.
        with latency("intent.faiss_search"):
            candidates = await faiss_index.search(transcript_en, top_k=settings.FAISS_TOP_K)

        if not candidates:
            logger.info("intent.no_candidates")
            return ClassifyResult(
                service_code=None,
                service_name=None,
                service_id=None,
                confidence=0.0,
                used_fallback=False,
                detected_language=lang,
                normalized_transcript_en=transcript_en,
                slots={},
                top_candidates=[],
            )

        # Enrich each candidate with rule-engine slot extraction + optional
        # small keyword boost. Semantic score remains the dominant signal —
        # keywords cannot single-handedly select a match and cannot outweigh
        # a semantically stronger candidate by more than KEYWORD_BOOST_MAX.
        repo = ServiceRepo(session)
        best: dict[str, Any] | None = None
        enriched: list[dict[str, Any]] = []

        for cand in candidates:
            svc = await repo.get_by_id(cand["service_id"])
            if svc is None:
                continue
            rule = rule_engine.evaluate(transcript_en, svc.keywords, svc.required_slots)
            semantic = cand["semantic_score"]
            boost = min(rule.keyword_score * KEYWORD_BOOST_MAX, KEYWORD_BOOST_MAX)
            hybrid = min(SEMANTIC_WEIGHT * semantic + boost, KEYWORD_BOOST_CAP)
            row = {
                **cand,
                "keyword_score": rule.keyword_score,
                "matched_keywords": rule.matched_keywords,
                "slots": rule.extracted_slots,
                "hybrid_confidence": hybrid,
            }
            enriched.append(row)
            if best is None or hybrid > best["hybrid_confidence"]:
                best = row

        assert best is not None
        confidence = float(best["hybrid_confidence"])
        used_fallback = False
        slots = dict(best["slots"])
        service_code = best["service_code"]
        service_id = best["service_id"]
        service_name = best["service_name"]

        # LLM fallback when hybrid confidence is below the threshold.
        if confidence < settings.CONFIDENCE_THRESHOLD:
            with latency("intent.llm_fallback"):
                catalog = [
                    {
                        "code": row["service_code"],
                        "name": row["service_name"],
                        "keywords": row.get("matched_keywords", []),
                    }
                    for row in enriched
                ]
                llm_out = await llm_fallback.classify_with_llm(transcript_en, catalog)
            llm_code = llm_out.get("service_code")
            llm_conf = float(llm_out.get("confidence", 0.0))

            if llm_code:
                svc = await repo.get_by_code(llm_code)
                if svc is not None and llm_conf >= confidence:
                    service_code = svc.code
                    service_id = svc.id
                    service_name = svc.name
                    slots = {**slots, **(llm_out.get("slots") or {})}
                    confidence = min(max(llm_conf, confidence), 0.999)
                    used_fallback = True
            elif llm_code is None and llm_conf > 0:
                # LLM says no service applies - lower our confidence accordingly.
                service_code = None
                service_id = None
                service_name = None
                used_fallback = True

        return ClassifyResult(
            service_code=service_code,
            service_name=service_name,
            service_id=service_id,
            confidence=round(confidence, 4),
            used_fallback=used_fallback,
            detected_language=lang,
            normalized_transcript_en=transcript_en,
            slots=slots,
            top_candidates=[
                {
                    "service_code": r["service_code"],
                    "service_name": r["service_name"],
                    "semantic_score": round(r["semantic_score"], 4),
                    "keyword_score": round(r["keyword_score"], 4),
                    "hybrid_confidence": round(r["hybrid_confidence"], 4),
                }
                for r in enriched
            ],
        )
