from app.rpg.world.npc_biography_registry import get_npc_biography
from app.rpg.world.npc_evolution_state import (
    apply_npc_evolution_event,
    get_npc_evolution,
    merged_npc_identity,
)
from app.rpg.world.npc_evolution_triggers import (
    evolve_npc_from_reputation_thresholds,
    evolve_npcs_from_world_event,
)
from app.rpg.world.npc_profile_loader import (
    clear_npc_profile_cache,
    get_file_npc_profile,
)
from app.rpg.world.npc_reputation_state import update_npc_reputation


def test_file_npc_profile_bran_loads():
    clear_npc_profile_cache()
    profile = get_file_npc_profile("npc:Bran")
    assert profile["npc_id"] == "npc:Bran"
    assert profile["source"] == "file_npc_profile"
    assert "tavern" in profile["role"].lower()


def test_biography_registry_uses_file_profile_first():
    profile = get_npc_biography("npc:Bran")
    assert profile["npc_id"] == "npc:Bran"
    assert profile["source"] == "file_npc_profile"


def test_apply_npc_evolution_event_requires_source_event():
    state = {}
    result = apply_npc_evolution_event(
        state,
        npc_id="npc:Bran",
        event_id="",
        kind="home_or_work_destroyed",
        tick=10,
    )
    assert result["applied"] is False


def test_bran_losing_tavern_creates_displaced_revenge_arc():
    state = {}
    result = evolve_npcs_from_world_event(
        state,
        world_event={
            "event_id": "event:test:bandit_attack",
            "kind": "location_destroyed",
            "location_id": "loc_tavern",
            "summary": "Bandits attacked and burned the Rusty Flagon.",
            "affected_npcs": ["npc:Bran"],
        },
        tick=10,
    )

    assert result["applied"] is True
    evo = get_npc_evolution(state, npc_id="npc:Bran")
    assert evo["current_role"] == "Displaced tavern keeper"
    assert evo["identity_arc"] == "revenge_after_losing_tavern"
    assert evo["party_join_eligibility"]["eligible"] is True


def test_merged_identity_overlays_evolution_role():
    base = get_npc_biography("npc:Bran")
    evo = {
        "current_role": "Displaced tavern keeper",
        "identity_arc": "revenge_after_losing_tavern",
        "personality_modifiers": [{"trait": "vengeful", "strength": 2}],
        "active_motivations": [{"kind": "revenge", "summary": "Find the bandits."}],
    }
    merged = merged_npc_identity(base_profile=base, evolution=evo)

    assert merged["base_role"]
    assert merged["current_role"] == "Displaced tavern keeper"
    assert merged["role"] == "Displaced tavern keeper"
    assert merged["identity_arc"] == "revenge_after_losing_tavern"


def test_reputation_threshold_creates_loyal_modifier():
    state = {}
    update_npc_reputation(
        state,
        npc_id="npc:Bran",
        tick=1,
        familiarity_delta=4,
        trust_delta=4,
        respect_delta=2,
        reason="test",
    )

    result = evolve_npc_from_reputation_thresholds(
        state,
        npc_id="npc:Bran",
        tick=2,
    )

    assert result["applied"] is True
    evo = get_npc_evolution(state, npc_id="npc:Bran")
    assert any("loyal" in str(mod).lower() for mod in evo["personality_modifiers"])
