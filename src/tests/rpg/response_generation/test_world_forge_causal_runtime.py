import copy

import pytest

from app.rpg.world.causal_runtime import (
    advance_causal_runtime,
    advance_installed_causal_runtime,
    bootstrap_causal_runtime,
    install_causal_runtime,
    replay_causal_events,
)
from app.rpg.world.world_event_log import get_world_event_state


def _planning_topics(trend: str = "escalating"):
    return {
        "present_day_state": {
            "state": {
                "ent:regions:001": {
                    "political_stability": 60,
                    "trade_access": 50,
                    "resource_access": 70,
                    "population_index": 55,
                }
            }
        },
        "political_claim_graph": {"claims": []},
        "settlement_origin_plan": {"settlements": []},
        "culture_lineage_plan": {"lineages": []},
        "pressure_plan": {
            "pressures": [
                {
                    "pressure_id": "pressure:001",
                    "severity": 30,
                    "trend": trend,
                    "next_tick_delta": {
                        "target_id": "ent:regions:001",
                        "dimension": "political_stability",
                        "operation": "decrease",
                        "value": 4,
                    },
                    "escalation_threshold": 32,
                    "resolution_threshold": 20,
                }
            ]
        },
    }


def test_runtime_bootstrap_is_deterministic_and_separates_initial_state() -> None:
    first = bootstrap_causal_runtime(_planning_topics())
    second = bootstrap_causal_runtime(_planning_topics())

    assert first == second
    assert first["schema_version"] == "rpg_causal_world_runtime_v1"
    assert first["pressure_statuses"] == {"pressure:001": "active"}
    assert first["events"] == []
    assert first["state"] == first["initial_state"]
    assert first["state"] is not first["initial_state"]
    assert first["runtime_hash"].startswith("sha256:")


def test_runtime_tick_emits_aggregate_and_propagated_status_event() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    advanced, emitted = advance_causal_runtime(runtime, tick=1)

    assert [event.event_type for event in emitted] == [
        "pressure_tick",
        "pressure_escalated",
    ]
    assert emitted[1].parent_event_id == emitted[0].event_id
    assert advanced["last_tick"] == 1
    assert advanced["pressure_statuses"] == {"pressure:001": "escalated"}
    assert advanced["state"]["cells"]["pressure:001"]["values"]["pressure_severity"] == 33
    assert advanced["state"]["cells"]["ent:regions:001"]["values"]["political_stability"] == 56


def test_escalation_event_is_not_repeated_on_later_ticks() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    first, emitted = advance_causal_runtime(runtime, tick=1)
    second, later = advance_causal_runtime(first, tick=2)

    assert [event.event_type for event in emitted] == [
        "pressure_tick",
        "pressure_escalated",
    ]
    assert [event.event_type for event in later] == ["pressure_tick"]
    assert second["pressure_statuses"]["pressure:001"] == "escalated"


def test_resolved_pressure_stops_runtime_mutation() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics("contained"))
    runtime["state"]["cells"]["pressure:001"]["values"]["pressure_severity"] = 19
    runtime["state"]["state_hash"] = ""

    first, emitted = advance_causal_runtime(runtime, tick=1)
    before_second = copy.deepcopy(first["state"])
    second, later = advance_causal_runtime(first, tick=2)

    assert [event.event_type for event in emitted] == [
        "pressure_tick",
        "pressure_resolved",
    ]
    assert [event.event_type for event in later] == ["pressure_tick"]
    assert second["pressure_statuses"]["pressure:001"] == "resolved"
    assert second["state"] == before_second


def test_runtime_tick_is_idempotent_and_replay_exact() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    first, emitted = advance_causal_runtime(runtime, tick=1)
    repeated, repeated_events = advance_causal_runtime(first, tick=1)
    replayed = replay_causal_events(first["initial_state"], first["events"])

    assert repeated == first
    assert tuple(event.event_id for event in repeated_events) == tuple(
        event.event_id for event in emitted
    )
    assert replayed == first["state"]


def test_replay_rejects_tampered_hash_chain() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    advanced, _ = advance_causal_runtime(runtime, tick=1)
    events = copy.deepcopy(advanced["events"])
    events[0]["before_state_hash"] = "sha256:tampered"

    with pytest.raises(ValueError, match="causal_replay_before_hash_mismatch"):
        replay_causal_events(advanced["initial_state"], events)


def test_installed_runtime_publishes_to_existing_world_event_log_once() -> None:
    simulation_state = {}
    install_causal_runtime(simulation_state, bootstrap_causal_runtime(_planning_topics()))

    first, emitted = advance_installed_causal_runtime(simulation_state, tick=1)
    second, repeated = advance_installed_causal_runtime(simulation_state, tick=1)
    world_events = get_world_event_state(simulation_state)["events"]

    assert first == second
    assert len(emitted) == len(repeated) == 2
    assert len(world_events) == 2
    assert {row["source"] for row in world_events} == {"deterministic_causal_runtime"}
    assert {row["event_id"] for row in world_events} == {
        event.event_id for event in emitted
    }
