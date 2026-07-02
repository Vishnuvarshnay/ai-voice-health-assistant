"""Basic smoke tests (no external services required)."""
from app.services import rule_engine


def test_rule_engine_extracts_room_and_scores():
    result = rule_engine.evaluate(
        transcript_en="Please clean my room 305 immediately",
        keywords=["clean", "cleaning", "room"],
        required_slots=["room_number"],
    )
    assert "room_number" in result.extracted_slots
    assert result.extracted_slots["room_number"] == "305"
    assert result.keyword_score > 0
    assert "clean" in result.matched_keywords


def test_rule_engine_no_match():
    result = rule_engine.evaluate(
        transcript_en="I want to check out today",
        keywords=["nurse", "medicine"],
        required_slots=[],
    )
    assert result.keyword_score == 0.0
    assert result.matched_keywords == []
