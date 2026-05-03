import json

from app.rpg.campaign_director.state import (
    normalize_campaign_director_state,
    record_campaign_director_tick,
)


def test_campaign_director_state_records_tick_history():
    simulation_state = {}
    record_campaign_director_tick(
        simulation_state,
        turn_index=4,
        mode="idle",
        eligible_count=2,
        applied_rule_ids=["rule:x"],
        applied_event_ids=["event:x"],
    )

    state = simulation_state["campaign_director_state"]
    assert state["last_tick_turn"] == 4
    assert state["tick_history"][0]["applied_event_ids"] == ["event:x"]


def test_campaign_director_state_json_roundtrip():
    simulation_state = {}
    record_campaign_director_tick(
        simulation_state,
        turn_index=4,
        mode="idle",
        eligible_count=1,
        applied_rule_ids=["rule:x"],
        applied_event_ids=["event:x"],
    )

    encoded = json.dumps(simulation_state["campaign_director_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_campaign_director_state(decoded)

    assert normalized["last_tick_turn"] == 4
    assert normalized["tick_history"][0]["applied_rule_ids"] == ["rule:x"]


def test_campaign_director_tick_history_is_bounded():
    simulation_state = {}
    for i in range(130):
        record_campaign_director_tick(
            simulation_state,
            turn_index=i,
            mode="idle",
            eligible_count=0,
        )

    assert len(simulation_state["campaign_director_state"]["tick_history"]) == 100