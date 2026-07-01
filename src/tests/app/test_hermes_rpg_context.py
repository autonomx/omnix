from __future__ import annotations

from app.assist_core.hermes_planner_context import hermes_planner_context_from_session
from app.assist_core.hermes_rpg_context import hermes_rpg_context_from_session, hermes_rpg_context_payload


def test_hermes_rpg_context_from_session_returns_bounded_read_only_snapshot() -> None:
    payload = hermes_rpg_context_from_session(
        "session-1",
        {
            "name": "Road to Glimmerdeep",
            "state": {
                "current_location": "Rusty Flagon Tavern",
                "active_npc": "Bran",
                "player": {
                    "name": "Aria",
                    "level": 2,
                    "xp": 35,
                    "currency": {"gold": 1, "silver": 5},
                    "inventory": [{"name": "Torch"}, {"name": "Ration"}],
                },
                "party": [{"name": "Bran"}],
                "quest_log": {"active": [{"name": "Find the witness"}]},
                "recent_turns": [
                    {"turn": 1, "action": "ask Bran about the witness", "category": "dialogue"},
                    {"turn": 2, "action": "buy two rations", "category": "service"},
                ],
                "combat_state": {"active": False},
                "service_state": {"active": True},
            },
        },
    )

    assert payload["ok"] is True
    assert payload["read_only"] is True
    context = payload["context"]
    assert context["session_id"] == "session-1"
    assert context["location"] == "Rusty Flagon Tavern"
    assert context["active_npc"] == "Bran"
    assert context["player"]["name"] == "Aria"
    assert context["player"]["currency"] == {"gold": 1, "silver": 5}
    assert context["party"] == ["Bran"]
    assert context["inventory"] == ["Torch", "Ration"]
    assert context["objectives"] == ["Find the witness"]
    assert context["recent_turns"][-1]["category"] == "service"
    assert context["state_flags"] == {"in_combat": False, "in_service": True, "can_travel": True}
    assert "save" not in payload


def test_hermes_rpg_context_payload_requires_session_id() -> None:
    payload = hermes_rpg_context_payload({})

    assert payload == {
        "ok": False,
        "error": "missing_session_id",
        "read_only": True,
        "source": "rpg_session",
    }


def test_hermes_planner_context_adds_commands_and_hash() -> None:
    session = {
        "state": {
            "current_location": "Rusty Flagon Tavern",
            "active_npc": "Bran",
            "player": {"name": "Aria", "inventory": [{"name": "Torch"}]},
            "recent_turns": [{"turn": 4, "action": "look around", "category": "general"}],
            "service_state": {"active": True},
        }
    }

    payload = hermes_planner_context_from_session("session-1", session)
    repeated = hermes_planner_context_from_session("session-1", session)

    assert payload["planner_ready"] is True
    assert payload["turn_id"] == 4
    assert len(payload["context_hash"]) == 16
    assert payload["context_hash"] == repeated["context_hash"]
    assert "buy" in payload["context"]["available_commands"]
    assert "travel" in payload["context"]["available_commands"]
