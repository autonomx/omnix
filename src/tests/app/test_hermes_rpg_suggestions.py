from __future__ import annotations

from app.assist_core.hermes_rpg_suggestions import (
    hermes_rpg_suggestions_from_context,
    hermes_rpg_suggestions_payload,
)


def test_hermes_rpg_suggestions_are_safe_player_inputs() -> None:
    payload = hermes_rpg_suggestions_from_context(
        {
            "location": "Rusty Flagon Tavern",
            "active_npc": "Bran",
            "objectives": ["Find the witness"],
            "inventory": ["Torch"],
            "player": {"level": 1, "xp": 0},
            "state_flags": {"in_combat": False, "in_service": True, "can_travel": True},
        }
    )

    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["source"] == "rpg_context"
    suggestions = payload["suggestions"]
    assert suggestions
    ids = {item["id"] for item in suggestions}
    assert "ask_active_npc" in ids
    assert "pursue_objective" in ids
    assert "buy_supplies" in ids
    for item in suggestions:
        assert item["risk"] == "safe_player_input"
        assert item["requires_user_click"] is True
        assert item["direct_state_write"] is False
        assert item["processed_by"] == "rpg_runtime"


def test_hermes_rpg_suggestions_can_use_inline_context_without_session_load() -> None:
    payload = hermes_rpg_suggestions_payload(
        {
            "context": {
                "location": "Market Road",
                "objectives": [],
                "inventory": [],
                "state_flags": {"in_combat": False, "in_service": False, "can_travel": True},
            }
        }
    )

    ids = {item["id"] for item in payload["suggestions"]}
    assert "check_journal" in ids
    assert "look_for_travel" in ids
    assert "check_inventory" in ids


def test_hermes_rpg_suggestions_reports_missing_session_when_no_context() -> None:
    payload = hermes_rpg_suggestions_payload({})

    assert payload["ok"] is False
    assert payload["error"] == "missing_session_id"
    assert payload["read_only"] is True
    assert payload["suggestions"] == []
    assert payload["count"] == 0
