from app.rpg.npc_evolution.conditions import evaluate_npc_evolution_condition
from app.rpg.npc_evolution.state import set_npc_arc_flag, start_npc_arc
from app.rpg.social.reputation import set_relationship_values
from app.rpg.story_arcs.state import start_story_arc


def test_npc_arc_active_condition():
    simulation_state = {}
    start_npc_arc(simulation_state, "bran", "npc_arc:bran_revenge")

    result = evaluate_npc_evolution_condition(
        simulation_state,
        {"type": "npc_arc_active", "npc_id": "bran", "arc_id": "npc_arc:bran_revenge"},
    )

    assert result["ok"] is True


def test_relationship_condition():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 70})

    result = evaluate_npc_evolution_condition(
        simulation_state,
        {"type": "relationship_at_least", "npc_id": "bran", "field": "trust", "minimum": 50},
    )

    assert result["ok"] is True


def test_story_arc_stage_condition():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="aftermath")

    result = evaluate_npc_evolution_condition(
        simulation_state,
        {"type": "story_arc_stage", "npc_id": "bran", "arc_id": "arc:bandit_pressure", "stage": "aftermath"},
    )

    assert result["ok"] is True


def test_npc_flag_condition():
    simulation_state = {}
    set_npc_arc_flag(simulation_state, "bran", "tavern_lost", True)

    result = evaluate_npc_evolution_condition(
        simulation_state,
        {"type": "npc_flag", "npc_id": "bran", "flag": "tavern_lost", "expected": True},
    )

    assert result["ok"] is True