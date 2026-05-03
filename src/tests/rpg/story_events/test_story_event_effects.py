from app.rpg.lore.state import get_lore_entry, upsert_lore_entry
from app.rpg.quests.state import get_quest
from app.rpg.social.reputation import get_relationship
from app.rpg.story_arcs.state import get_story_arc, start_story_arc
from app.rpg.story_events.application import apply_story_event


def test_story_event_applies_arc_pressure_delta():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", pressure=20)

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:pressure",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 25},
            ],
        },
        turn_index=2,
    )

    assert result["ok"] is True
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["pressure"] == 45


def test_story_event_reveals_lore():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")
    upsert_lore_entry(simulation_state, {"lore_id": "lore:red_sashes", "title": "The Red Sashes"})

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:reveal_lore",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {"type": "lore_reveal", "lore_id": "lore:red_sashes"},
            ],
        },
    )

    assert result["ok"] is True
    assert get_lore_entry(simulation_state, "lore:red_sashes")["revealed_to_player"] is True


def test_story_event_applies_social_delta():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:social",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {"type": "social_delta", "npc_id": "bran", "fear": 10, "trust": -2},
            ],
        },
    )

    relationship = get_relationship(simulation_state, "bran")
    assert result["ok"] is True
    assert relationship["fear"] == 10
    assert relationship["trust"] == -2


def test_story_event_can_trigger_quest_transition():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:start_quest",
            "arc_id": "arc:bandit_pressure",
            "effects": [
                {
                    "type": "quest_transition",
                    "transition": {
                        "action": "start",
                        "quest_id": "quest:stop_red_sashes",
                        "stage": "investigate",
                    },
                },
            ],
        },
    )

    quest = get_quest(simulation_state, "quest:stop_red_sashes")
    assert result["ok"] is True
    assert quest["stage"] == "investigate"


def test_story_event_emits_world_event():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:world_row",
            "arc_id": "arc:bandit_pressure",
            "kind": "warning",
            "summary": "Bandits warned Bran.",
            "location_id": "tavern_common_room",
            "effects": [
                {"type": "world_event_emit"},
            ],
        },
        turn_index=3,
    )

    rows = simulation_state["world_event_state"]["events"]
    assert result["ok"] is True
    assert len(rows) == 1
    assert rows[0]["source_story_event_id"] == "event:world_row"