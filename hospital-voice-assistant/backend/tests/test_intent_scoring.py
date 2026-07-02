"""Unit tests for the semantic-primary intent classifier scoring rules.

These tests avoid loading BGE-M3 / FAISS or hitting the DB; they exercise
the pure scoring math.
"""
from app.services.intent_classifier import (
    CONFIDENCE_CAP,
    KEYWORD_BOOST_MAX,
    SEMANTIC_WEIGHT,
)


def test_scoring_constants_are_semantic_primary():
    assert SEMANTIC_WEIGHT == 1.0
    assert 0 < KEYWORD_BOOST_MAX <= 0.15
    assert CONFIDENCE_CAP < 1.0


def test_semantic_beats_keyword_only_match():
    # A semantically weak candidate that happens to match all keywords
    # cannot outrank a semantically strong candidate that matches none.
    strong_semantic = SEMANTIC_WEIGHT * 0.90 + min(0.0 * KEYWORD_BOOST_MAX, KEYWORD_BOOST_MAX)
    weak_semantic_full_kw = SEMANTIC_WEIGHT * 0.60 + min(1.0 * KEYWORD_BOOST_MAX, KEYWORD_BOOST_MAX)
    assert strong_semantic > weak_semantic_full_kw
