"""Hybrid intent classifier — semantic-primary, multilingual, non-hallucinating.

Design principles (per spec):
  * BGE-M3 is multilingual, so semantic matching runs on the ORIGINAL
    transcript. Translation is NOT required.
  * Semantic (FAISS) is the base confidence signal.
  * Rule engine extracts slots and provides at most a +0.10 keyword boost.
  * Groq LLM is used ONLY when confidence < CONFIDENCE_THRESHOLD and
    MUST pick from the DB catalog (or return null).
  * If neither semantic nor LLM can match → status = UNKNOWN_SERVICE.
  * Translation to English happens only when TRANSLATE_FOR_AUDIT=true and
    is purely for audit/reporting fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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


STATUS_MATCHED = "MATCHED"
STATUS_UNKNOWN = "UNKNOWN_SERVICE"


@dataclass
class ClassifyResult:
    status: str
    service_code: str | None
    service_name: str | None
    service_id: int | None
    confidence: float
    used_fallback: bool
    detected_language: str | None
    raw_transcript: str
    normalized_transcript_en: str
    slots: dict[str, Any] = field(default_factory=dict)
    top_candidates: list[dict[str, Any]] = field(default_factory=list)


def _safe_detect_language(text: str) -> str | None:
    try:
        return detect(text)
    except Exception:  # pragma: no cover - langdetect can throw on very short strings
        return None


def _is_english(lang: str | None) -> bool:
    return bool(lang) and lang.lower().startswith("en")


async def classify(
    session: AsyncSession,
    transcript: str,
    detected_language: str | None = None,
) -> ClassifyResult:
    with latency("intent.classify", transcript_len=len(transcript)):
        lang = detected_language or _safe_detect_language(transcript)

        # BGE-M3 is multilingual → run FAISS search on the ORIGINAL transcript.
        # Optional English rendering only for audit / reporting.
        transcript_en = transcript
        if settings.TRANSLATE_FOR_AUDIT and not _is_english(lang):
            with latency("intent.translate_for_audit", src_lang=lang):
                try:
                    transcript_en = await llm_fallback.translate_to_english(transcript, lang)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("intent.translate.failed", error=str(exc))

        with latency("intent.faiss_search"):
            candidates = await faiss_index.search(transcript, top_k=settings.FAISS_TOP_K)

        if not candidates:
            logger.info("intent.no_candidates")
            return ClassifyResult(
                status=STATUS_UNKNOWN,
                service_code=None,
                service_name=None,
                service_id=None,
                confidence=0.0,
                used_fallback=False,
                detected_language=lang,
                raw_transcript=transcript,
                normalized_transcript_en=transcript_en,
            )

        # Enrich each candidate with rule-engine slot extraction + optional
        # keyword boost. Semantic score dominates.
        repo = ServiceRepo(session)
        best: dict[str, Any] | None = None
        enriched: list[dict[str, Any]] = []

        for cand in candidates:
            svc = await repo.get_by_id(cand["service_id"])
            if svc is None:
                continue
            rule = rule_engine.evaluate(transcript, svc.keywords, svc.required_slots)
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
        top_semantic = float(best["semantic_score"])
        confidence = float(best["hybrid_confidence"])
        used_fallback = False
        slots = dict(best["slots"])
        service_code = best["service_code"]
        service_id = best["service_id"]
        service_name = best["service_name"]

        # Hard floor: if the best candidate is semantically far, skip LLM
        # entirely and mark as UNKNOWN. This is what prevents e.g. "coconut
        # water" from being force-matched to DRINKING_WATER.
        if top_semantic < settings.MIN_SEMANTIC_THRESHOLD:
            logger.info(
                "intent.below_min_semantic",
                top_score=top_semantic,
                threshold=settings.MIN_SEMANTIC_THRESHOLD,
            )
            return _unknown(
                lang, transcript, transcript_en, enriched, top_semantic, service_code
            )

        # LLM fallback ONLY when hybrid confidence is below the accept threshold.
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
            else:
                # LLM refused — no service applies.
                return _unknown(
                    lang, transcript, transcript_en, enriched, top_semantic, service_code
                )

        return ClassifyResult(
            status=STATUS_MATCHED,
            service_code=service_code,
            service_name=service_name,
            service_id=service_id,
            confidence=round(confidence, 4),
            used_fallback=used_fallback,
            detected_language=lang,
            raw_transcript=transcript,
            normalized_transcript_en=transcript_en,
            slots=slots,
            top_candidates=_serialize_candidates(enriched),
        )


def _serialize_candidates(enriched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "service_code": r["service_code"],
            "service_name": r["service_name"],
            "semantic_score": round(r["semantic_score"], 4),
            "keyword_score": round(r["keyword_score"], 4),
            "hybrid_confidence": round(r["hybrid_confidence"], 4),
        }
        for r in enriched
    ]


def _unknown(
    lang: str | None,
    transcript: str,
    transcript_en: str,
    enriched: list[dict[str, Any]],
    top_semantic: float,
    top_code: str | None,
) -> ClassifyResult:
    return ClassifyResult(
        status=STATUS_UNKNOWN,
        service_code=None,
        service_name=None,
        service_id=None,
        confidence=round(top_semantic, 4),
        used_fallback=False,
        detected_language=lang,
        raw_transcript=transcript,
        normalized_transcript_en=transcript_en,
        slots={},
        top_candidates=_serialize_candidates(enriched),
    )
