import json

from app.rpg.campaign_journal.journal import record_campaign_journal_entry
from app.rpg.campaign_journal.state import normalize_campaign_journal_state


def test_campaign_journal_records_entry():
    simulation_state = {}
    result = record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        title="Bandit Attack",
        summary="Bandits attacked the road.",
        turn_index=3,
        event_ids=["event:bandit_attack"],
    )

    assert result["ok"] is True
    assert simulation_state["campaign_journal_state"]["entries"][0]["summary"] == "Bandits attacked the road."


def test_campaign_journal_entry_is_idempotent():
    simulation_state = {}
    first = record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        summary="Bandits attacked the road.",
        turn_index=3,
        source_id="event:x",
    )
    second = record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        summary="Bandits attacked the road.",
        turn_index=3,
        source_id="event:x",
    )

    assert first["reason"] == "recorded"
    assert second["reason"] == "already_recorded"
    assert len(simulation_state["campaign_journal_state"]["entries"]) == 1


def test_campaign_journal_state_json_roundtrip():
    simulation_state = {}
    record_campaign_journal_entry(
        simulation_state,
        kind="story_event",
        summary="Bandits attacked the road.",
        turn_index=3,
        source_id="event:x",
    )

    encoded = json.dumps(simulation_state["campaign_journal_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_campaign_journal_state(decoded)

    assert normalized["entries"][0]["summary"] == "Bandits attacked the road."


def test_campaign_journal_history_bounded():
    simulation_state = {}
    for i in range(350):
        record_campaign_journal_entry(
            simulation_state,
            kind="story_event",
            summary=f"Event {i}",
            turn_index=i,
            source_id=f"event:{i}",
        )

    assert len(simulation_state["campaign_journal_state"]["entries"]) == 300