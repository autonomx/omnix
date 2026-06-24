from __future__ import annotations

from app.rpg.quest_chronicle import (
    ChronicleEntry,
    QuestObjective,
    QuestState,
    chronicle_payload,
    grounded_suggested_actions,
    rumor_to_quest,
    transition_quest_status,
)


def _quest() -> QuestState:
    return QuestState(
        "bandit-trail",
        "Bandit Trail",
        "accepted",
        objectives=(QuestObjective("ask-bran", "Ask Bran about the trail"), QuestObjective("go-quarry", "Travel to the quarry")),
        known_clues=("Bootprints lead north.",),
        npc_ids=("bran",),
        location_ids=("old_quarry",),
        reward="20 silver",
    )


def test_current_objective_and_completion_are_pure() -> None:
    quest = _quest()
    updated = quest.complete_objective("ask-bran")

    assert quest.current_objective().objective_id == "ask-bran"
    assert updated.current_objective().objective_id == "go-quarry"


def test_transition_quest_status_reports_source_event() -> None:
    updated, transition = transition_quest_status(_quest(), "advanced", source_event_id="event-9")

    assert updated.status == "advanced"
    assert transition.as_dict() == {
        "quest_id": "bandit-trail",
        "before": "accepted",
        "after": "advanced",
        "source_event_id": "event-9",
    }


def test_rumor_to_quest_creates_grounded_lead() -> None:
    quest = rumor_to_quest("smoke", "Smoke on the Road", clue="Smoke rises beyond the gate.", location_id="north_gate")

    assert quest.status == "rumored"
    assert quest.known_clues == ("Smoke rises beyond the gate.",)
    assert quest.location_ids == ("north_gate",)


def test_grounded_suggested_actions_use_known_locations() -> None:
    suggestions = grounded_suggested_actions([_quest()], ["old_quarry"])

    assert suggestions[0] == "Work on Bandit Trail: Ask Bran about the trail"
    assert "Travel to old_quarry for Bandit Trail" in suggestions
    assert "Ask bran about Bandit Trail" in suggestions


def test_chronicle_payload_groups_entries_and_quests() -> None:
    payload = chronicle_payload(
        [ChronicleEntry(3, "learned", "Bran mentioned bootprints.", ("bran", "bootprints"))],
        [_quest()],
    )

    assert payload["what_i_learned"][0]["summary"] == "Bran mentioned bootprints."
    assert payload["quests"][0]["quest_id"] == "bandit-trail"
    assert payload["suggested_actions"]
