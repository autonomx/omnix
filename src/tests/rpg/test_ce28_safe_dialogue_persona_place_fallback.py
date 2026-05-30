from __future__ import annotations

from app.rpg.session import interactive_first_call_runtime as interactive_runtime
from tests.rpg.test_interactive_intent_matrix_ce25_fallback_telemetry import (
    _install_default_stateful_direct_question,
    _session_override,
)


def _run_safe_fallback(monkeypatch, player_input: str):
    _install_default_stateful_direct_question(monkeypatch, player_input)
    return interactive_runtime.apply_turn(
        session_id="manual_service_bran_ce28_persona_place",
        player_input=player_input,
        session_override=_session_override(),
    )


def test_ce28_identity_question_safe_fallback_is_bran_persona_aware(monkeypatch):
    result = _run_safe_fallback(monkeypatch, "Bran, who are you?")

    assert result["result"]["fallback_topic"] == "identity_inquiry"
    assert result["grounding_validation"]["fallback_used"] is True
    assert result["grounding_validation"]["fallback_source"] == "first_call_dialogue_safe_fallback_v1"

    npc = result["npc"]
    assert npc["speaker"] == "Bran"
    line = npc["line"].lower()
    assert "bran" in line
    assert "tavern" in line
    assert "keeper" in line or "innkeeper" in line


def test_ce28_place_question_safe_fallback_mentions_tavern_road_or_town(monkeypatch):
    result = _run_safe_fallback(monkeypatch, "What do you know about this place?")

    assert result["result"]["fallback_topic"] == "local_knowledge"
    assert result["grounding_validation"]["fallback_used"] is True
    assert result["grounding_validation"]["fallback_source"] == "first_call_dialogue_safe_fallback_v1"

    npc = result["npc"]
    assert npc["speaker"] == "Bran"
    line = npc["line"].lower()
    assert "place" in line
    assert any(term in line for term in ("tavern", "road", "town"))
