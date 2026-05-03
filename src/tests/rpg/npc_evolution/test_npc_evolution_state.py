from app.rpg.npc_evolution.state import (
    apply_npc_evolution_delta,
    get_npc_evolution,
    set_npc_arc_flag,
    start_npc_arc,
)


def test_start_npc_arc_sets_motivation_role_profession():
    simulation_state = {}
    result = start_npc_arc(
        simulation_state,
        "bran",
        "npc_arc:bran_revenge",
        motivation="revenge_against_red_sashes",
        role="companion_candidate",
        profession="former_innkeeper",
        turn_index=3,
    )

    evolution = get_npc_evolution(simulation_state, "bran")
    assert result["ok"] is True
    assert "npc_arc:bran_revenge" in evolution["active_arcs"]
    assert evolution["motivation"] == "revenge_against_red_sashes"
    assert evolution["profession"] == "former_innkeeper"


def test_apply_npc_evolution_delta_clamps_personality():
    simulation_state = {}
    apply_npc_evolution_delta(
        simulation_state,
        "bran",
        personality_deltas={"vengeful": 150, "cautious": -150},
    )

    evolution = get_npc_evolution(simulation_state, "bran")
    assert evolution["personality"]["vengeful"] == 100
    assert evolution["personality"]["cautious"] == -100


def test_npc_evolution_flags_and_history_bounded():
    simulation_state = {}
    for i in range(80):
        set_npc_arc_flag(simulation_state, "bran", f"flag_{i}", True, turn_index=i)

    evolution = get_npc_evolution(simulation_state, "bran")
    assert evolution["flags"]["flag_79"] is True
    assert len(evolution["history"]) == 50