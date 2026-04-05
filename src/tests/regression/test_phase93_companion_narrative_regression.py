"""Phase 9.3 — Companion Narrative Integration regression tests.

Ensures determinism, save compatibility, and no unintended side effects.
"""
from app.rpg.party.companion_narrative import (
    choose_scene_interjections,
    build_companion_scene_reactions,
    _pick_tone,
)
from app.rpg.party.party_state import (
    ensure_party_state,
    add_companion,
    update_companion_loyalty,
    set_companion_status,
)
from app.rpg.persistence.migration_manager import migrate_package_to_current
from app.rpg.persistence.migrations.v6_to_v7 import migrate_v6_to_v7
from app.rpg.persistence.save_schema import CURRENT_RPG_SCHEMA_VERSION, ENGINE_VERSION


def test_companion_interjection_is_stable_across_repeated_calls():
    """Interjections must be deterministic across repeated calls."""
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_a", "A")
    player_state = add_companion(player_state, "npc_b", "B")

    scene_state = {"scene_id": "scene_gate", "tone": "tense", "location_id": "loc_gate"}
    sim_state = {"player_state": player_state}

    one = choose_scene_interjections(sim_state, scene_state)
    two = choose_scene_interjections(sim_state, scene_state)
    three = choose_scene_interjections(sim_state, scene_state)
    assert one == two == three


def test_interjection_order_is_deterministic_with_same_state():
    """Multiple companions should always appear in same sorted order."""
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_zara", "Zara")
    player_state = add_companion(player_state, "npc_alfa", "Alfa")
    player_state = add_companion(player_state, "npc_mid", "Mid")

    scene_state = {"scene_id": "scene_camp", "tone": "calm", "location_id": "loc_camp"}
    sim_state = {"player_state": player_state}

    result1 = choose_scene_interjections(sim_state, scene_state)
    result2 = choose_scene_interjections(sim_state, scene_state)

    assert [r["npc_id"] for r in result1] == [r["npc_id"] for r in result2]
    # Should be sorted alphabetically
    npc_ids = [r["npc_id"] for r in result1]
    assert npc_ids == sorted(npc_ids)


def test_v6_to_v7_migration_preserves_existing_companions():
    """Migration must not destroy existing companion data."""
    package = {
        "schema_version": 6,
        "state": {
            "simulation_state": {
                "player_state": {
                    "party_state": {
                        "companions": [
                            {
                                "npc_id": "npc_borin",
                                "name": "Borin",
                                "hp": 80,
                                "max_hp": 100,
                                "loyalty": 0.6,
                                "morale": 0.5,
                                "role": "ally",
                                "status": "active",
                                "equipment": {},
                            }
                        ]
                    }
                }
            }
        },
    }
    out = migrate_package_to_current(package)
    companions = (
        (
            ((out.get("state", {}) or {}).get("simulation_state", {}) or {})
            .get("player_state", {})
            .get("party_state", {})
            or {}
        ).get("companions")
        or []
    )
    assert len(companions) == 1
    assert companions[0]["npc_id"] == "npc_borin"
    assert companions[0]["hp"] == 80
    assert companions[0]["max_hp"] == 100


def test_v6_to_v7_migration_adds_narrative_state():
    """Migration must add narrative_state with expected keys."""
    package = {
        "schema_version": 6,
        "state": {
            "simulation_state": {
                "player_state": {
                    "party_state": {
                        "companions": []
                    }
                }
            }
        },
    }
    out = migrate_package_to_current(package)
    party_state = (
        ((out.get("state", {}) or {}).get("simulation_state", {}) or {})
        .get("player_state", {})
        .get("party_state", {})
        or {}
    )
    narrative_state = party_state.get("narrative_state", {})
    assert "history" in narrative_state
    assert "last_interjection" in narrative_state
    assert "last_scene_reactions" in narrative_state
    assert isinstance(narrative_state["history"], list)


def test_schema_version_and_engine_version_are_updated():
    """Ensure schema and engine versions reflect Phase 9.3."""
    assert CURRENT_RPG_SCHEMA_VERSION >= 7
    assert "phase_9_3" in ENGINE_VERSION


def test_downed_companions_never_appear_in_reactions():
    """Companions with status='downed' or hp<=0 should not react."""
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_fighter", "Fighter")
    player_state = set_companion_status(player_state, "npc_fighter", "downed")

    scene_state = {"scene_id": "scene_battle", "tone": "tense", "location_id": "loc_battlefield"}
    reactions = build_companion_scene_reactions(player_state, scene_state)
    npc_ids = [r.get("npc_id") for r in reactions]
    assert "npc_fighter" not in npc_ids


def test_absent_companions_never_appear_in_reactions():
    """Companions with status='absent' should not react."""
    player_state = ensure_party_state({})
    player_state = add_companion(player_state, "npc_ghost", "Ghost")
    player_state = set_companion_status(player_state, "npc_ghost", "absent")

    scene_state = {"scene_id": "scene_dungeon", "tone": "dark", "location_id": "loc_dungeon"}
    reactions = build_companion_scene_reactions(player_state, scene_state)
    npc_ids = [r.get("npc_id") for r in reactions]
    assert "npc_ghost" not in npc_ids


def test_narrative_tone_reflects_loyalty_and_morale():
    """Tone selection must be deterministic based on loyalty/morale."""
    # Low loyalty -> resentful
    comp_low = {
        "npc_id": "npc_low",
        "name": "Low",
        "loyalty": -0.5,
        "morale": 0.5,
        "role": "ally",
        "status": "active",
        "hp": 100,
    }
    assert _pick_tone(comp_low) == "resentful"

    # Low morale -> fearful
    comp_fear = {
        "npc_id": "npc_fear",
        "name": "Fear",
        "loyalty": 0.0,
        "morale": 0.2,
        "role": "ally",
        "status": "active",
        "hp": 100,
    }
    assert _pick_tone(comp_fear) == "fearful"

    # High loyalty + morale -> supportive
    comp_high = {
        "npc_id": "npc_high",
        "name": "High",
        "loyalty": 0.8,
        "morale": 0.8,
        "role": "ally",
        "status": "active",
        "hp": 100,
    }
    assert _pick_tone(comp_high) == "supportive"

    # Neutral -> guarded
    comp_neutral = {
        "npc_id": "npc_neutral",
        "name": "Neutral",
        "loyalty": 0.0,
        "morale": 0.5,
        "role": "ally",
        "status": "active",
        "hp": 100,
    }
    assert _pick_tone(comp_neutral) == "guarded"


def test_empty_state_does_not_crash_narrative_functions():
    """Functions must handle empty/minimal state gracefully."""
    player_state = ensure_party_state({})
    scene_state = {}

    # Should not raise
    interjections = choose_scene_interjections({"player_state": player_state}, scene_state)
    assert isinstance(interjections, list)

    reactions = build_companion_scene_reactions(player_state, scene_state)
    assert isinstance(reactions, list)