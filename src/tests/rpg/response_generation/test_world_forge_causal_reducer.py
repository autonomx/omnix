import copy

import pytest

from app.rpg.world.causal_reducer import (
    WorldStateDelta,
    causal_state_hash,
    reduce_world_state,
)
from app.rpg.world.causal_state import build_mutable_world_state


def _state():
    return build_mutable_world_state(
        {
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
            "political_claim_graph": {
                "claims": [{"claim_id": "claim:001", "control_index": 40}]
            },
            "settlement_origin_plan": {
                "settlements": [
                    {
                        "place_id": "ent:places:001",
                        "route_dependency": 50,
                        "strategic_value": 70,
                    }
                ]
            },
            "culture_lineage_plan": {
                "lineages": [
                    {"culture_id": "ent:cultures:001", "cohesion_index": 65}
                ]
            },
            "pressure_plan": {
                "pressures": [{"pressure_id": "pressure:001", "severity": 30}]
            },
        }
    )


def test_reducer_is_pure_deterministic_and_ordered() -> None:
    state = _state()
    original = copy.deepcopy(state)
    deltas = [
        WorldStateDelta(
            delta_id="delta:002",
            tick=2,
            sequence=0,
            target_id="ent:regions:001",
            dimension_id="trade_access",
            operation="increase",
            value=10,
        ),
        WorldStateDelta(
            delta_id="delta:001",
            tick=1,
            sequence=0,
            target_id="ent:regions:001",
            dimension_id="trade_access",
            operation="multiply",
            value=2,
        ),
    ]

    first, receipt = reduce_world_state(state, deltas)
    second, second_receipt = reduce_world_state(state, tuple(reversed(deltas)))

    assert state == original
    assert first == second
    assert receipt == second_receipt
    assert first["cells"]["ent:regions:001"]["values"]["trade_access"] == 100
    assert receipt.applied_delta_ids == ("delta:001", "delta:002")
    assert receipt.previous_state_hash == state["state_hash"]
    assert receipt.next_state_hash == causal_state_hash(first)


def test_reducer_clamps_values_and_advances_revisions() -> None:
    state = _state()
    reduced, receipt = reduce_world_state(
        state,
        [
            {
                "delta_id": "delta:pressure",
                "tick": 4,
                "sequence": 1,
                "target_id": "pressure:001",
                "dimension_id": "pressure_severity",
                "operation": "increase",
                "value": 500,
                "source_event_id": "event:001",
            }
        ],
    )

    assert reduced["cells"]["pressure:001"]["values"]["pressure_severity"] == 100
    assert reduced["cells"]["pressure:001"]["revision"] == 2
    assert reduced["revision"] == state["revision"] + 1
    assert reduced["tick"] == 4
    assert reduced["event_cursor"] == 1
    assert receipt.changed_target_ids == ("pressure:001",)


def test_reducer_rejects_duplicate_delta_ids() -> None:
    delta = {
        "delta_id": "delta:duplicate",
        "tick": 1,
        "target_id": "claim:001",
        "dimension_id": "control_index",
        "operation": "increase",
        "value": 1,
    }

    with pytest.raises(ValueError, match="duplicate_world_state_delta_id"):
        reduce_world_state(_state(), [delta, delta])


def test_reducer_rejects_unknown_targets_and_scope_mismatches() -> None:
    with pytest.raises(ValueError, match="world_state_delta_target_unknown"):
        reduce_world_state(
            _state(),
            [
                {
                    "delta_id": "delta:missing",
                    "tick": 1,
                    "target_id": "ent:regions:999",
                    "dimension_id": "trade_access",
                    "operation": "increase",
                    "value": 1,
                }
            ],
        )

    with pytest.raises(ValueError, match="world_state_delta_scope_mismatch"):
        reduce_world_state(
            _state(),
            [
                {
                    "delta_id": "delta:scope",
                    "tick": 1,
                    "target_id": "pressure:001",
                    "dimension_id": "trade_access",
                    "operation": "increase",
                    "value": 1,
                }
            ],
        )
