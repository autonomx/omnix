import json

from app.rpg.npc_evolution.state import (
    apply_npc_evolution_delta,
    normalize_npc_evolution_state,
    start_npc_arc,
)


def test_npc_evolution_state_json_roundtrip():
    simulation_state = {}
    start_npc_arc(
        simulation_state,
        "bran",
        "npc_arc:bran_revenge",
        motivation="revenge_against_red_sashes",
    )
    apply_npc_evolution_delta(
        simulation_state,
        "bran",
        personality_deltas={"vengeful": 20},
        companion_eligible=True,
    )

    encoded = json.dumps(simulation_state["npc_evolution_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_npc_evolution_state(decoded)

    evolution = normalized["npcs"]["bran"]
    assert evolution["motivation"] == "revenge_against_red_sashes"
    assert evolution["personality"]["vengeful"] == 20
    assert evolution["companion_eligible"] is True