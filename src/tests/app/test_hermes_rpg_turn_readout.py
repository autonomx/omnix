from __future__ import annotations

from app.assist_core.hermes_rpg_turn_readout import hermes_rpg_turn_readout_payload


def test_hermes_rpg_turn_readout_reports_systems_and_effects() -> None:
    payload = hermes_rpg_turn_readout_payload(
        {
            "session_id": "session-1",
            "turn": {
                "turn": 7,
                "command": "ask Bran about the witness",
                "category": "dialogue",
                "response": "Bran lowers his voice.",
                "effects": {"memory": "witness lead", "journal": "updated"},
                "grounding": {"status": "checked"},
            },
        }
    )

    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["source"] == "rpg_turn"
    assert payload["session_id"] == "session-1"
    assert payload["turn"]["turn_id"] == 7
    assert payload["turn"]["command"] == "ask Bran about the witness"
    assert payload["turn"]["category"] == "dialogue"
    assert payload["turn"]["narration_present"] is True
    assert "npc_dialogue" in payload["systems"]
    assert "grounding_validator" in payload["systems"]
    assert "presentation" in payload["systems"]
    assert payload["effect_count"] == 2
    assert payload["grounding_status"] == "checked"


def test_hermes_rpg_turn_readout_can_read_latest_session_turn(monkeypatch) -> None:
    from app.rpg.session import service

    def fake_load_session(session_id: str) -> dict[str, object]:
        assert session_id == "session-2"
        return {
            "state": {
                "turns": [
                    {"turn": 1, "command": "check inventory"},
                    {"turn": 2, "command": "travel down the road", "effects": ["moved"]},
                ]
            }
        }

    monkeypatch.setattr(service, "load_session", fake_load_session)

    payload = hermes_rpg_turn_readout_payload({"session_id": "session-2"})

    assert payload["ok"] is True
    assert payload["session_id"] == "session-2"
    assert payload["turn"]["turn_id"] == 2
    assert payload["turn"]["category"] == "travel"
    assert "travel_gate" in payload["systems"]
    assert payload["effect_count"] == 1


def test_hermes_rpg_turn_readout_requires_turn() -> None:
    payload = hermes_rpg_turn_readout_payload({})

    assert payload == {"ok": False, "error": "missing_turn", "read_only": True, "source": "rpg_turn"}
