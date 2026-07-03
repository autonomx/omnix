from __future__ import annotations

from app.assist_core.hermes_rpg_context_pack import build_hermes_rpg_context_pack


def test_context_pack_extracts_stable_bounded_fields() -> None:
    session = {
        "id": "session-1",
        "state": {
            "current_location": "Glimmerdeep Pass",
            "player": {"stats": {"wisdom": 12, "strength": 10}},
            "inventory": [{"id": "rope"}, {"id": "torch"}],
            "party": [{"name": "Bran"}],
            "active_quests": [{"id": "q1"}],
            "recent_events": ["arrived", "looked"],
            "known_npcs": [{"name": "Bran"}],
            "combat": {"active": False},
            "service_state": {"provider": "Bran"},
            "travel_state": {"route": "north"},
        },
    }

    pack = build_hermes_rpg_context_pack(session, item_limit=1)

    assert pack["session_id"] == "session-1"
    assert pack["current_location"] == "Glimmerdeep Pass"
    assert list(pack["player_stats"]) == ["strength", "wisdom"]
    assert pack["inventory"] == [{"id": "rope"}]
    assert pack["party"] == [{"name": "Bran"}]
    assert pack["active_combat"] == {"active": False}


def test_context_pack_trims_to_budget() -> None:
    pack = build_hermes_rpg_context_pack(
        {"id": "s", "state": {"inventory": [{"id": str(index)} for index in range(20)], "recent_events": ["x" * 200 for _ in range(20)]}},
        item_limit=20,
        char_budget=500,
    )

    assert len(repr(pack)) <= 700
    assert len(pack["recent_events"]) < 20
