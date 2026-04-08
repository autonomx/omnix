"""Phase 9.3 — Companion Narrative Integration functional tests."""
import json

from flask import Flask
from flask.testing import FlaskClient

from app.rpg.api.rpg_player_routes import rpg_player_bp


def _make_client() -> FlaskClient:
    """Create test Flask client with RPG player blueprints registered."""
    app = Flask(__name__)
    # Note: rpg_player_bp is already imported
    return app.test_client()


def _make_test_payload():
    return {
        "simulation_state": {
            "player_state": {
                "party_state": {
                    "companions": [
                        {
                            "npc_id": "npc_borin",
                            "name": "Borin",
                            "hp": 100,
                            "max_hp": 100,
                            "loyalty": 0.8,
                            "morale": 0.7,
                            "role": "ally",
                            "status": "active",
                            "equipment": {},
                        }
                    ]
                }
            }
        }
    }


def test_build_player_party_view_returns_presence_summary():
    """Ensure the party view returns presence_summary for narrative payload."""
    from app.rpg.player.player_party import build_player_party_view, ensure_player_party

    sim_state = _make_test_payload()["simulation_state"]
    sim_state = ensure_player_party(sim_state)
    view = build_player_party_view(sim_state)
    assert "presence_summary" in view
    assert "party_summary" in view
    summary = view.get("presence_summary", {})
    assert len(summary.get("present_companions", [])) > 0


def test_build_companion_scene_context_returns_expected_keys():
    """Ensure companion scene context contains scene and location ids."""
    from app.rpg.party.companion_narrative import build_companion_scene_context

    sim_state = _make_test_payload()["simulation_state"]
    scene_state = {
        "scene_id": "scene_test",
        "location_id": "loc_market",
        "tone": "tense",
    }
    ctx = build_companion_scene_context(sim_state, scene_state)
    assert "scene_id" in ctx
    assert "location_id" in ctx
    assert "present_companions" in ctx


def test_build_companion_dialogue_context_returns_expected_keys():
    """Ensure dialogue context returns dialogue_active flag."""
    from app.rpg.party.companion_narrative import build_companion_dialogue_context

    sim_state = _make_test_payload()["simulation_state"]
    dialogue_state = {"target_id": "npc_alice"}
    ctx = build_companion_dialogue_context(sim_state, dialogue_state)
    assert "dialogue_active" in ctx
    assert ctx["dialogue_active"] is True


def test_record_narrative_event_updates_history():
    """Recording a narrative event updates history and last_interjection."""
    from app.rpg.party.companion_narrative import (
        build_party_narrative_summary,
        record_companion_narrative_event,
    )
    from app.rpg.party.party_state import ensure_party_state

    player_state = _make_test_payload()["simulation_state"].get("player_state", {})
    player_state = record_companion_narrative_event(player_state, {
        "tick": 42,
        "scene_id": "scene_gate",
        "npc_id": "npc_borin",
        "kind": "interjection",
        "summary": "Borin speaks at the gate.",
    })
    party_state = ensure_party_state(player_state).get("party_state", {})
    summary = build_party_narrative_summary(party_state)
    assert summary["history_size"] >= 1
    assert "gate" in summary.get("last_interjection", {}).get("scene_id", "")


def test_build_companion_scene_reactions_omits_downed():
    """Downed companion should not appear in scene reactions."""
    from app.rpg.party.companion_narrative import build_companion_scene_reactions
    from app.rpg.party.party_state import (
        add_companion,
        ensure_party_state,
        set_companion_status,
    )

    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_borin", "Borin")
    player_state = set_companion_status(player_state, "npc_borin", "downed")
    reactions = build_companion_scene_reactions(player_state, {
        "scene_id": "scene_battle",
        "tone": "tense",
        "location_id": "loc_battlefield",
    })
    npc_ids = [r.get("npc_id") for r in reactions]
    assert "npc_borin" not in npc_ids


def test_record_companion_narrative_event_keeps_history_bounded():
    """History must never exceed 20 entries after many recordings."""
    from app.rpg.party.companion_narrative import (
        _MAX_NARRATIVE_HISTORY,
        record_companion_narrative_event,
    )
    from app.rpg.party.party_state import add_companion, ensure_party_state

    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_borin", "Borin")
    for idx in range(50):
        player_state = record_companion_narrative_event(player_state, {
            "tick": idx,
            "scene_id": f"scene_{idx}",
            "npc_id": "npc_borin",
            "kind": "interjection",
            "summary": f"Event {idx}",
        })
    party_state = ensure_party_state(player_state).get("party_state", {})
    narrative_state = party_state.get("narrative_state", {})
    history = narrative_state.get("history", [])
    assert len(history) <= _MAX_NARRATIVE_HISTORY