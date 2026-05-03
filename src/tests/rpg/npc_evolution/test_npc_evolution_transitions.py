from app.rpg.npc_evolution.state import get_npc_evolution, set_npc_arc_flag
from app.rpg.npc_evolution.transitions import apply_npc_evolution_transition
from app.rpg.social.reputation import set_relationship_values


def test_npc_evolution_transition_starts_revenge_arc():
    simulation_state = {}
    result = apply_npc_evolution_transition(
        simulation_state,
        {
            "action": "start_arc",
            "npc_id": "bran",
            "arc_id": "npc_arc:bran_revenge",
            "motivation": "revenge_against_red_sashes",
            "profession": "former_innkeeper",
        },
    )

    evolution = get_npc_evolution(simulation_state, "bran")
    assert result["ok"] is True
    assert "npc_arc:bran_revenge" in evolution["active_arcs"]


def test_npc_evolution_transition_gated_by_flag():
    simulation_state = {}
    set_npc_arc_flag(simulation_state, "bran", "tavern_lost", True)

    result = apply_npc_evolution_transition(
        simulation_state,
        {
            "action": "evolve",
            "npc_id": "bran",
            "motivation": "revenge_against_red_sashes",
            "conditions": [
                {"type": "npc_flag", "npc_id": "bran", "flag": "tavern_lost", "expected": True}
            ],
        },
    )

    assert result["ok"] is True
    assert get_npc_evolution(simulation_state, "bran")["motivation"] == "revenge_against_red_sashes"


def test_companion_offer_requires_high_trust():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 80})

    result = apply_npc_evolution_transition(
        simulation_state,
        {
            "action": "evolve",
            "npc_id": "bran",
            "companion_eligible": True,
            "conditions": [
                {"type": "relationship_at_least", "npc_id": "bran", "field": "trust", "minimum": 70}
            ],
        },
    )

    assert result["ok"] is True
    assert get_npc_evolution(simulation_state, "bran")["companion_eligible"] is True


def test_low_trust_blocks_companion_offer():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 20})

    result = apply_npc_evolution_transition(
        simulation_state,
        {
            "action": "evolve",
            "npc_id": "bran",
            "companion_eligible": True,
            "conditions": [
                {"type": "relationship_at_least", "npc_id": "bran", "field": "trust", "minimum": 70}
            ],
        },
    )

    assert result["ok"] is False
    assert result["reason"] == "conditions_failed"