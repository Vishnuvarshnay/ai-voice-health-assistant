"""Hybrid semantic intent classifier for the hospital voice assistant.

Pipeline (semantic-primary, non-hallucinating):

    1.  BGE-M3 multilingual embedding of the ORIGINAL transcript
        (no translation before search — BGE-M3 handles multilingual).
    2.  FAISS top-K nearest-neighbour search over the service catalog.
    3.  Business rule engine per candidate:
          * slot extraction (room_number, quantity, time, …)
          * optional keyword boost (≤ +0.10) — never dominates semantics.
    4.  Confidence = min(semantic_score + keyword_boost, 0.99).
    5.  If confidence ≥ CONFIDENCE_THRESHOLD (default 0.85) → return match.
    6.  Else if best semantic score ≥ MIN_SEMANTIC_THRESHOLD (default 0.35)
        → Groq LLM fallback, constrained to the top-K catalog subset.
    7.  Every service code returned by FAISS AND by the LLM is re-fetched
        from the DB (`ServiceRepo.get_by_code`) — anything not found is
        rejected. Nothing that isn't in the live catalog can leak out.
    8.  If no candidate survives → status = UNKNOWN_SERVICE.

Invariants enforced by unit tests:
  * The classifier never returns a service_code that isn't in the DB.
  * The LLM is called only when confidence < CONFIDENCE_THRESHOLD.
  * A high semantic + no LLM path still validates the catalog membership.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from langdetect import DetectorFactory, detect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import latency, logger
from app.models.orm import HospitalService
from app.repositories.service_repo import ServiceRepo
from app.services import llm_fallback as _llm_fallback_module
from app.services import rule_engine as _rule_engine_module
from app.services.faiss_index import faiss_index as _faiss_index_singleton

DetectorFactory.seed = 0  # deterministic language detection

STATUS_MATCHED = "MATCHED"
STATUS_UNKNOWN = "UNKNOWN_SERVICE"

SEMANTIC_WEIGHT = 1.0        # semantic score IS the base confidence
KEYWORD_BOOST_MAX = 0.10     # rule engine can nudge at most +0.10
CONFIDENCE_CAP = 0.99        # never claim absolute certainty


# --------------------------- data classes --------------------------------- #

@dataclass
class Candidate:
    service_id: int
    service_code: str
    service_name: str
    semantic_score: float
    keyword_score: float
    matched_keywords: list[str]
    slots: dict[str, Any]
    hybrid_confidence: float

    def to_public(self) -> dict[str, Any]:
        return {
            "service_code": self.service_code,
            "service_name": self.service_name,
            "semantic_score": round(self.semantic_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "hybrid_confidence": round(self.hybrid_confidence, 4),
        }


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


# --------------------------- port interfaces ------------------------------ #
# Small protocols so unit tests can inject fakes without touching FAISS,
# BGE-M3, or Groq.

class FaissPort(Protocol):
    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]: ...


class RuleEnginePort(Protocol):
    def evaluate(self, transcript: str, keywords, required_slots): ...


class LlmFallbackPort(Protocol):
    async def classify_with_llm(
        self, transcript_en: str, catalog: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    async def translate_to_english(
        self, transcript: str, source_language: str | None
    ) -> str: ...


# --------------------------- classifier ----------------------------------- #

class HybridIntentClassifier:
    """Semantic-primary, catalog-validated hybrid classifier."""

    def __init__(
        self,
        faiss: FaissPort | None = None,
        rule_engine: RuleEnginePort | None = None,
        llm: LlmFallbackPort | None = None,
    ) -> None:
        self._faiss = faiss or _faiss_index_singleton
        self._rule_engine = rule_engine or _rule_engine_module
        self._llm = llm or _llm_fallback_module

    # -------- public entrypoint -------- #

    async def classify(
        self,
        session: AsyncSession,
        transcript: str,
        detected_language: str | None = None,
    ) -> ClassifyResult:
        with latency("intent.classify", transcript_len=len(transcript)):
            lang = detected_language or self._detect_language(transcript)
            transcript_en = await self._optional_translate(transcript, lang)
            repo = ServiceRepo(session)

            candidates = await self._semantic_search(transcript)
            if not candidates:
                logger.info("intent.no_candidates")
                return self._unknown(lang, transcript, transcript_en, [], 0.0)

            scored = await self._score_candidates(transcript, candidates, repo)
            if not scored:
                # All FAISS hits pointed to services no longer in the catalog.
                logger.warning("intent.all_candidates_invalid")
                return self._unknown(lang, transcript, transcript_en, [], 0.0)

            best = max(scored, key=lambda c: c.hybrid_confidence)
            top_semantic = max(c.semantic_score for c in scored)

            # Hard floor — the "coconut water vs DRINKING_WATER" guard.
            if top_semantic < settings.MIN_SEMANTIC_THRESHOLD:
                logger.info(
                    "intent.below_min_semantic",
                    top_score=top_semantic,
                    threshold=settings.MIN_SEMANTIC_THRESHOLD,
                )
                return self._unknown(lang, transcript, transcript_en, scored, top_semantic)

            # Accept without LLM if we're confident enough.
            if best.hybrid_confidence >= settings.CONFIDENCE_THRESHOLD:
                svc = await self._validate_in_catalog(repo, best.service_code)
                if svc is None:  # defensive — should never happen
                    return self._unknown(
                        lang, transcript, transcript_en, scored, top_semantic
                    )
                return self._matched(
                    svc, best, used_fallback=False, lang=lang,
                    transcript=transcript, transcript_en=transcript_en,
                    scored=scored,
                )

            # LLM fallback (constrained to the top-K catalog subset).
            fallback = await self._try_llm_fallback(
                repo=repo,
                transcript_en=transcript_en,
                scored=scored,
                previous_best=best,
            )
            if fallback is None:
                return self._unknown(lang, transcript, transcript_en, scored, top_semantic)
            svc, new_confidence, extra_slots = fallback
            merged_slots = {**best.slots, **extra_slots}
            merged_best = Candidate(
                service_id=svc.id,
                service_code=svc.code,
                service_name=svc.name,
                semantic_score=best.semantic_score,
                keyword_score=best.keyword_score,
                matched_keywords=best.matched_keywords,
                slots=merged_slots,
                hybrid_confidence=new_confidence,
            )
            return self._matched(
                svc, merged_best, used_fallback=True, lang=lang,
                transcript=transcript, transcript_en=transcript_en,
                scored=scored,
            )

    # -------- pipeline steps -------- #

    def _detect_language(self, text: str) -> str | None:
        try:
            return detect(text)
        except Exception:  # pragma: no cover
            return None

    async def _optional_translate(self, transcript: str, lang: str | None) -> str:
        """Translation is OPTIONAL and only for audit / reporting."""
        if not settings.TRANSLATE_FOR_AUDIT:
            return transcript
        if lang and lang.lower().startswith("en"):
            return transcript
        try:
            with latency("intent.translate_for_audit", src_lang=lang):
                return await self._llm.translate_to_english(transcript, lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent.translate.failed", error=str(exc))
            return transcript

    async def _semantic_search(self, transcript: str) -> list[dict[str, Any]]:
        with latency("intent.faiss_search"):
            return await self._faiss.search(transcript, top_k=settings.FAISS_TOP_K)

    async def _score_candidates(
        self,
        transcript: str,
        raw_candidates: list[dict[str, Any]],
        repo: ServiceRepo,
    ) -> list[Candidate]:
        """Validate each FAISS hit exists in the catalog + apply rule engine."""
        scored: list[Candidate] = []
        for cand in raw_candidates:
            # Catalog validation #1 — reject FAISS hits for services that
            # no longer exist (e.g. deleted after the index was built).
            svc = await repo.get_by_id(cand["service_id"])
            if svc is None:
                logger.warning(
                    "intent.candidate.not_in_catalog",
                    service_id=cand.get("service_id"),
                    service_code=cand.get("service_code"),
                )
                continue
            rule = self._rule_engine.evaluate(transcript, svc.keywords, svc.required_slots)
            semantic = float(cand["semantic_score"])
            boost = min(rule.keyword_score * KEYWORD_BOOST_MAX, KEYWORD_BOOST_MAX)
            hybrid = min(SEMANTIC_WEIGHT * semantic + boost, CONFIDENCE_CAP)
            scored.append(
                Candidate(
                    service_id=svc.id,
                    service_code=svc.code,
                    service_name=svc.name,
                    semantic_score=semantic,
                    keyword_score=rule.keyword_score,
                    matched_keywords=rule.matched_keywords,
                    slots=dict(rule.extracted_slots),
                    hybrid_confidence=hybrid,
                )
            )
        return scored

    async def _try_llm_fallback(
        self,
        repo: ServiceRepo,
        transcript_en: str,
        scored: list[Candidate],
        previous_best: Candidate,
    ) -> tuple[HospitalService, float, dict[str, Any]] | None:
        """Call Groq with the top-K catalog subset. Refuse anything else."""
        catalog_subset = [
            {
                "code": c.service_code,
                "name": c.service_name,
                "keywords": c.matched_keywords,
            }
            for c in scored
        ]
        allowed_codes = {c.service_code for c in scored}
        with latency("intent.llm_fallback"):
            llm_out = await self._llm.classify_with_llm(transcript_en, catalog_subset)

        llm_code = llm_out.get("service_code")
        llm_conf = float(llm_out.get("confidence", 0.0))

        # Anti-hallucination gate #1 — LLM returned something outside catalog.
        if llm_code is None:
            return None
        if llm_code not in allowed_codes:
            logger.warning(
                "intent.llm.invented_service_rejected",
                llm_code=llm_code,
                allowed=list(allowed_codes),
            )
            return None

        # Anti-hallucination gate #2 — re-validate against the DB even though
        # we already checked the top-K allow-list.
        svc = await self._validate_in_catalog(repo, llm_code)
        if svc is None:
            return None

        # Only accept LLM if it's at least as confident as the semantic path.
        if llm_conf < previous_best.hybrid_confidence:
            return None

        confidence = min(max(llm_conf, previous_best.hybrid_confidence), CONFIDENCE_CAP)
        extra_slots = llm_out.get("slots") or {}
        return svc, confidence, extra_slots

    async def _validate_in_catalog(
        self, repo: ServiceRepo, code: str
    ) -> HospitalService | None:
        """Single choke-point for catalog membership."""
        return await repo.get_by_code(code)

    # -------- result builders -------- #

    def _matched(
        self,
        svc: HospitalService,
        best: Candidate,
        used_fallback: bool,
        lang: str | None,
        transcript: str,
        transcript_en: str,
        scored: list[Candidate],
    ) -> ClassifyResult:
        return ClassifyResult(
            status=STATUS_MATCHED,
            service_code=svc.code,
            service_name=svc.name,
            service_id=svc.id,
            confidence=round(best.hybrid_confidence, 4),
            used_fallback=used_fallback,
            detected_language=lang,
            raw_transcript=transcript,
            normalized_transcript_en=transcript_en,
            slots=best.slots,
            top_candidates=[c.to_public() for c in scored],
        )

    def _unknown(
        self,
        lang: str | None,
        transcript: str,
        transcript_en: str,
        scored: list[Candidate],
        top_semantic: float,
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
            top_candidates=[c.to_public() for c in scored],
        )


# --------------------------- module-level facade -------------------------- #
# Backward compatibility for existing callers.

_default_classifier = HybridIntentClassifier()


async def classify(
    session: AsyncSession,
    transcript: str,
    detected_language: str | None = None,
) -> ClassifyResult:
    return await _default_classifier.classify(
        session=session, transcript=transcript, detected_language=detected_language
    )
