from app.rpg.dialogue_context.arc_context import build_arc_dialogue_context
from app.rpg.dialogue_context.rumors import propagate_rumor
from app.rpg.lore.state import upsert_lore_entry
from app.rpg.memory.observation import record_told_memory
from app.rpg.social.reputation import set_relationship_values
from app.rpg.story_arcs.state import start_story_arc


def test_npc_can_discuss_lore_they_know():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "known_by": ["bran"],
        },
    )

    result = build_arc_dialogue_context(
        simulation_state,
        "bran",
        topic_lore_id="lore:red_sashes",
    )

    assert result["can_discuss"] is True
    assert result["known_lore"][0]["lore_id"] == "lore:red_sashes"
    assert result["known_lore"][0]["must_mark_as_rumor"] is True


def test_npc_cannot_discuss_secret_lore_they_do_not_know():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:bran_debt",
            "title": "Bran's Debt",
            "truth_status": "secret",
            "known_by": ["bran"],
        },
    )

    result = build_arc_dialogue_context(
        simulation_state,
        "mira",
        topic_lore_id="lore:bran_debt",
    )

    assert result["can_discuss"] is False
    assert result["known_lore"] == []
    assert result["rejected_lore"][0]["reason"] == "secret_not_known"


def test_npc_discusses_arc_if_linked_to_known_lore():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "known_by": ["bran"],
        },
    )
    start_story_arc(
        simulation_state,
        "arc:bandit_pressure",
        title="Bandit Pressure",
        stage="rumors",
        pressure=20,
        links={"lore": ["lore:red_sashes"]},
    )

    result = build_arc_dialogue_context(
        simulation_state,
        "bran",
        arc_id="arc:bandit_pressure",
    )

    assert result["can_discuss"] is True
    assert result["known_story_arcs"][0]["arc_id"] == "arc:bandit_pressure"


def test_npc_refuses_arc_topic_if_social_hostile():
    simulation_state = {}
    simulation_state["social_state"] = {"relationships": {"bran": {"trust": -20, "hostility": 60}}}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "known_by": ["bran"],
        },
    )

    result = build_arc_dialogue_context(
        simulation_state,
        "bran",
        topic_lore_id="lore:red_sashes",
    )

    assert result["social_stance"] == "hostile"
    assert result["can_discuss"] is False


def test_npc_memory_makes_lore_available_as_rumor():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )
    propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:red_sashes",
        summary="The Red Sashes are active again.",
        explicit_hearers=["mira"],
        turn_index=1,
    )

    result = build_arc_dialogue_context(
        simulation_state,
        "mira",
        topic_lore_id="lore:red_sashes",
    )

    assert result["can_discuss"] is True
    assert result["known_lore"][0]["must_mark_as_rumor"] is True


def test_rumor_hearer_can_discuss_lore_as_rumor():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )
    propagate_rumor(
        simulation_state,
        speaker_id="bran",
        lore_id="lore:red_sashes",
        summary="The Red Sashes are active again.",
        explicit_hearers=["mira"],
        turn_index=1,
    )

    context = build_arc_dialogue_context(
        simulation_state,
        "mira",
        topic_lore_id="lore:red_sashes",
    )

    assert context["can_discuss"] is True
    assert context["known_lore"][0]["lore_id"] == "lore:red_sashes"
    assert context["rumor_permissions"]["must_mark_as_rumor"] is True