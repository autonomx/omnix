"""Phase 9.3 — Companion Narrative Integration unit tests."""
from app.rpg.party.party_state import (
    ensure_party_state,
    add_companion,
    update_companion_loyalty,
    set_companion_status,
)
from app.rpg.party.companion_narrative import (
    choose_scene_interjections,
    build_companion_scene_reactions,
    record_companion_narrative_event,
    build_party_narrative_summary,
    build_companion_presence_summary,
    _pick_tone,
)


def _base_player_state():
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_borin", "Borin")
    player_state = add_companion(player_state, "npc_lyra", "Lyra")
    return player_state


def test_choose_scene_interjections_is_deterministic():
    """Interjections must be identical across repeated calls with same state."""
    player_state = _base_player_state()
    simulation_state = {"player_state": player_state}
    scene_state = {
        "scene_id": "scene_market",
        "tone": "tense",
        "location_id": "loc_market",
    }
    first = choose_scene_interjections(simulation_state, scene_state)
    second = choose_scene_interjections(simulation_state, scene_state)
    assert first == second


def test_downed_companions_do_not_interject():
    """Downed companions should not appear in interjections."""
    player_state = _base_player_state()
    player_state = set_companion_status(player_state, "npc_borin", "downed")
    simulation_state = {"player_state": player_state}
    scene_state = {
        "scene_id": "scene_market",
        "tone": "tense",
        "location_id": "loc_market",
    }
    interjections = choose_scene_interjections(simulation_state, scene_state)
    npc_ids = [i.get("npc_id") for i in interjections]
    assert "npc_borin" not in npc_ids


def test_absent_companions_do_not_interject():
    """Absent companions should not appear in interjections."""
    player_state = _base_player_state()
    player_state = set_companion_status(player_state, "npc_lyra", "absent")
    simulation_state = {"player_state": player_state}
    scene_state = {
        "scene_id": "scene_market",
        "tone": "tense",
        "location_id": "loc_market",
    }
    interjections = choose_scene_interjections(simulation_state, scene_state)
    npc_ids = [i.get("npc_id") for i in interjections]
    assert "npc_lyra" not in npc_ids


def test_low_loyalty_companion_produces_resentful_tone():
    """Companions with low loyalty should produce resentful tone."""
    player_state = _base_player_state()
    player_state = update_companion_loyalty(player_state, "npc_borin", -1.0)
    comp = None
    for c in ensure_party_state(player_state).get("party_state", {}).get("companions", []):
        if c.get("npc_id") == "npc_borin":
            comp = c
            break
    assert comp is not None
    tone = _pick_tone(comp)
    assert tone == "resentful"


def test_build_companion_scene_reactions_skips_absent():
    """Absent companions should not appear in scene reactions."""
    player_state = _base_player_state()
    player_state = set_companion_status(player_state, "npc_lyra", "absent")
    scene_state = {
        "scene_id": "scene_camp",
        "tone": "calm",
        "location_id": "loc_camp",
    }
    reactions = build_companion_scene_reactions(player_state, scene_state)
    npc_ids = [r.get("npc_id") for r in reactions]
    assert "npc_lyra" not in npc_ids


def test_record_companion_narrative_event_is_bounded():
    """Narrative history must never exceed 20 entries."""
    player_state = _base_player_state()
    for idx in range(40):
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
    assert len(history) <= 20


def test_build_party_narrative_summary_returns_expected_keys():
    """Summary must contain history_size, last_interjection, last_scene_reactions."""
    player_state = _base_player_state()
    player_state = record_companion_narrative_event(player_state, {
        "tick": 1,
        "scene_id": "scene_test",
        "npc_id": "npc_borin",
        "kind": "interjection",
        "summary": "Test event",
    })
    party_state = ensure_party_state(player_state).get("party_state", {})
    summary = build_party_narrative_summary(party_state)
    assert "history_size" in summary
    assert "last_interjection" in summary
    assert "last_scene_reactions" in summary
    assert summary["history_size"] >= 1


def test_build_companion_presence_summary_returns_expected_keys():
    """Presence summary must contain party_summary and present_companions."""
    player_state = _base_player_state()
    presence = build_companion_presence_summary(player_state)
    assert "party_summary" in presence
    assert "present_companions" in presence
    assert len(presence["present_companions"]) > 0