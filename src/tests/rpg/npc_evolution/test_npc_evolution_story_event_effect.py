from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_events.application import apply_story_event


def test_story_event_applies_npc_evolution_effect():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", stage="aftermath")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:tavern_lost",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {
                    "type": "npc_evolution",
                    "npc_id": "bran",
                    "npc_arc_id": "npc_arc:bran_revenge",
                    "profession": "former_innkeeper",
                    "motivation": "revenge_against_red_sashes",
                    "personality_deltas": {"vengeful": 20, "cautious": 10},
                    "flags": {"tavern_lost": True},
                }
            ],
        },
    )

    evolution = get_npc_evolution(simulation_state, "bran")
    assert result["ok"] is True
    assert "npc_arc:bran_revenge" in evolution["active_arcs"]
    assert evolution["profession"] == "former_innkeeper"
    assert evolution["motivation"] == "revenge_against_red_sashes"
    assert evolution["personality"]["vengeful"] == 20
    assert evolution["flags"]["tavern_lost"] is True