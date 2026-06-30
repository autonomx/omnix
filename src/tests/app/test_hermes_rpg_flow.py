from __future__ import annotations

from app.assist_core.hermes_rpg_suggestions import hermes_rpg_suggestions_payload
from app.assist_core.hermes_rpg_turn_readout import hermes_rpg_turn_readout_payload
from app.assist_core.omnix_route_decision import omnix_route_decision_payload


def test_hermes_rpg_flow_is_read_only_and_click_gated() -> None:
    decision = omnix_route_decision_payload("rpg")
    suggestions = hermes_rpg_suggestions_payload(
        {
            "context": {
                "location": "Rusty Flagon Tavern",
                "active_npc": "Bran",
                "objectives": ["Find the witness"],
                "inventory": ["Torch"],
                "state_flags": {"in_combat": False, "in_service": True, "can_travel": True},
            }
        }
    )
    readout = hermes_rpg_turn_readout_payload(
        {
            "session_id": "session-1",
            "turn": {
                "turn": 3,
                "command": "ask Bran about the witness",
                "category": "dialogue",
                "effects": {"journal": "updated"},
                "grounding": {"status": "checked"},
            },
        }
    )

    assert decision["ok"] is True
    assert decision["mode"] == "rpg"
    assert decision["owner"] == "rpg_sim"
    assert decision["review_required"] is False
    assert suggestions["ok"] is True
    assert suggestions["read_only"] is True
    assert suggestions["policy"]["owner"] == "rpg_sim"
    assert suggestions["adapter"]["owner"] == "rpg_sim"
    assert suggestions["suggestions"]
    for item in suggestions["suggestions"]:
        assert item["requires_user_click"] is True
        assert item["direct_state_write"] is False
        assert item["processed_by"] == "rpg_runtime"
    assert readout["ok"] is True
    assert readout["read_only"] is True
    assert readout["turn"]["category"] == "dialogue"
    assert "npc_dialogue" in readout["systems"]
