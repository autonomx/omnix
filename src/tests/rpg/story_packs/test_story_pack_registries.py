from app.rpg.story_packs.definition_registries import (
    get_escalation_rule_definition,
    get_story_event_definition,
    list_escalation_rule_definitions,
    register_escalation_rule_definition,
    register_story_event_definition,
)


def test_story_event_definition_registry_registers_event():
    simulation_state = {}
    result = register_story_event_definition(
        simulation_state,
        {
            "event_id": "event:x",
            "arc_id": "arc:x",
            "effects": [],
        },
        pack_id="storypack:test",
    )

    assert result["ok"] is True
    event = get_story_event_definition(simulation_state, "event:x")
    assert event["metadata"]["pack_id"] == "storypack:test"


def test_escalation_rule_registry_registers_and_lists_rule():
    simulation_state = {}
    result = register_escalation_rule_definition(
        simulation_state,
        {
            "rule_id": "rule:x",
            "arc_id": "arc:x",
            "priority": 80,
            "event": {"event_id": "event:x", "effects": []},
        },
        pack_id="storypack:test",
    )

    assert result["ok"] is True
    rule = get_escalation_rule_definition(simulation_state, "rule:x")
    rows = list_escalation_rule_definitions(simulation_state, arc_id="arc:x")
    assert rule["metadata"]["pack_id"] == "storypack:test"
    assert rows[0]["rule_id"] == "rule:x"