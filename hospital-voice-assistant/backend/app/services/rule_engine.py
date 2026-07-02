"""Keyword / slot rule engine for boosting semantic matches."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass
class RuleResult:
    keyword_score: float
    matched_keywords: list[str]
    extracted_slots: dict[str, str]


_ROOM_RE = re.compile(r"\broom\s*(?:number\s*|no\.?\s*|#\s*)?(\d{1,4}[A-Za-z]?)\b", re.I)
_TIME_RE = re.compile(
    r"\b(\d{1,2}(?:[:\.]\d{2})?\s*(?:am|pm|AM|PM|hours?|hrs?)?)\b"
)
_QTY_RE = re.compile(r"\b(one|two|three|four|five|\d+)\b", re.I)


def _keyword_match(transcript_lower: str, keywords: Iterable[str]) -> tuple[float, list[str]]:
    keywords = [k.strip().lower() for k in keywords if k and k.strip()]
    if not keywords:
        return 0.0, []
    matched = [k for k in keywords if k in transcript_lower]
    if not matched:
        return 0.0, []
    # Score = fraction of unique keywords matched, capped at 1.0.
    unique = set(keywords)
    return min(len(set(matched)) / max(len(unique), 1), 1.0), matched


def _extract_slots(transcript: str, required_slots: Iterable[str]) -> dict[str, str]:
    slots: dict[str, str] = {}
    for slot in required_slots:
        slot_l = slot.lower()
        if slot_l in {"room", "room_number", "room_no"}:
            m = _ROOM_RE.search(transcript)
            if m:
                slots[slot] = m.group(1)
        elif slot_l in {"time", "at_time", "when"}:
            m = _TIME_RE.search(transcript)
            if m:
                slots[slot] = m.group(1)
        elif slot_l in {"quantity", "qty", "count"}:
            m = _QTY_RE.search(transcript)
            if m:
                slots[slot] = m.group(1)
    return slots


def evaluate(
    transcript_en: str,
    keywords: Iterable[str],
    required_slots: Iterable[str],
) -> RuleResult:
    lower = transcript_en.lower()
    kw_score, matched = _keyword_match(lower, keywords)
    slots = _extract_slots(transcript_en, required_slots)
    return RuleResult(keyword_score=kw_score, matched_keywords=matched, extracted_slots=slots)
