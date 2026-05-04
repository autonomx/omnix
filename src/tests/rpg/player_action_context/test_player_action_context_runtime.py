from app.rpg.player_action_context.runtime import (
    build_player_action_context,
    build_suggested_actions,
)
from app.rpg.quest_log.runtime import pin_objective
from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc


def _state_with_objective():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:witness", title="Witness Search", stage="rumors", pressure=20)
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:witness",
        milestone_id="milestone:find_witness",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
        quest_id="quest:witness",
        priority=80,
    )
    return simulation_state


def test_player_action_context_includes_active_objective_and_suggestions():
    simulation_state = _state_with_objective()

    context = build_player_action_context(simulation_state, turn_index=2)

    assert context["ok"] is True
    assert context["format_version"] == "player_action_context_v1"
    assert context["active_objectives"][0]["objective_id"] == "milestone:find_witness"
    assert any(row["category"] == "objective" for row in context["suggested_actions"])


def test_suggested_actions_are_bounded():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    for i in range(30):
        add_story_arc_milestone(
            simulation_state,
            arc_id="arc:x",
            milestone_id=f"milestone:{i}",
            title=f"Objective {i}",
            priority=i,
        )

    actions = build_suggested_actions(simulation_state, limit=12)

    assert len(actions) <= 12


def test_player_action_context_prefers_pinned_objective():
    simulation_state = _state_with_objective()
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:witness",
        milestone_id="milestone:inspect_road",
        title="Inspect the road",
        objective_text="Inspect the road outside town.",
        quest_id="quest:witness",
        priority=10,
    )
    pin_objective(simulation_state, "milestone:inspect_road")

    context = build_player_action_context(simulation_state, turn_index=2)

    assert context["active_objectives"][0]["objective_id"] == "milestone:inspect_road"
    assert context["suggested_actions"][0]["objective_id"] == "milestone:inspect_road"


def test_player_action_context_excludes_secret_unrevealed_lore():
    simulation_state = _state_with_objective()
    simulation_state["lore_state"] = {
        "entries": {
            "lore:secret": {
                "lore_id": "lore:secret",
                "title": "Secret Debt",
                "truth_status": "secret",
                "revealed_to_player": False,
                "summary": "Bran secretly owes the Red Sashes.",
            }
        }
    }

    context = build_player_action_context(simulation_state, turn_index=2)
    encoded = str(context)

    assert "Bran secretly owes the Red Sashes" not in encoded


def test_player_action_context_combat_mode_suggests_combat_actions():
    simulation_state = {"combat_state": {"active": True}}

    context = build_player_action_context(simulation_state, turn_index=2)

    assert context["mode"] == "combat"
    assert any(row["category"] == "combat" for row in context["suggested_actions"])