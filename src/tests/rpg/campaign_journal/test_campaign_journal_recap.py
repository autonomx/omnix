from app.rpg.campaign_journal.journal import (
    build_campaign_journal,
    build_player_story_recap,
    record_campaign_journal_entry,
)
from app.rpg.companions.offers import accept_companion_offer
from app.rpg.lore.state import upsert_lore_entry
from app.rpg.npc_evolution.state import apply_npc_evolution_delta, start_npc_arc
from app.rpg.social.reputation import set_relationship_values
from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_event_queue.queue import enqueue_story_event


def test_campaign_journal_excludes_unrevealed_secret_lore():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:secret_debt",
            "title": "Secret Debt",
            "truth_status": "secret",
            "revealed_to_player": False,
        },
    )

    journal = build_campaign_journal(simulation_state)

    assert journal["known_lore"] == []


def test_campaign_journal_marks_rumors_as_rumors():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "summary": "A gang may be active nearby.",
        },
    )

    journal = build_campaign_journal(simulation_state)

    assert journal["known_lore"][0]["lore_id"] == "lore:red_sashes"
    assert journal["known_lore"][0]["truth_status"] == "rumor"


def test_campaign_recap_includes_active_arcs_pending_consequences_and_npc_evolution():
    simulation_state = {}
    start_story_arc(
        simulation_state,
        "arc:bandit_pressure",
        title="Bandit Pressure",
        stage="rumors",
        pressure=60,
    )
    enqueue_story_event(
        simulation_state,
        {"event_id": "event:delayed_attack", "arc_id": "arc:bandit_pressure", "effects": []},
        enqueued_turn=1,
        due_turn=5,
    )
    start_npc_arc(
        simulation_state,
        "bran",
        "npc_arc:bran_revenge",
        motivation="revenge_against_red_sashes",
        profession="former_innkeeper",
    )

    recap = build_player_story_recap(simulation_state, turn_index=2)

    assert recap["format_version"] == "campaign_story_recap_v1"
    assert recap["active_arcs"][0]["arc_id"] == "arc:bandit_pressure"
    assert recap["pending_consequences"][0]["event_id"] == "event:delayed_attack"
    assert recap["npc_evolution"][0]["npc_id"] == "bran"
    assert "Do not reveal hidden or secret lore." in recap["narrator_context"]["rules"]


def test_companion_acceptance_records_journal_entry():
    simulation_state = {}
    start_npc_arc(
        simulation_state,
        "bran",
        "npc_arc:bran_revenge",
        motivation="revenge_against_red_sashes",
        role="companion",
    )
    apply_npc_evolution_delta(simulation_state, "bran", companion_eligible=True)
    set_relationship_values(simulation_state, "bran", {"trust": 80})

    result = accept_companion_offer(simulation_state, "bran", turn_index=4)
    journal = build_campaign_journal(simulation_state)

    assert result["ok"] is True
    assert any(row["kind"] == "companion" for row in journal["entries"])


def test_player_story_recap_is_bounded():
    simulation_state = {}
    for i in range(80):
        record_campaign_journal_entry(
            simulation_state,
            kind="story_event",
            summary=f"Story event {i}",
            turn_index=i,
            source_id=f"event:{i}",
        )

    recap = build_player_story_recap(simulation_state, turn_index=80, max_items=10)

    assert len(recap["latest_journal_entries"]) <= 10
    assert recap["bounded"]["max_items"] == 10