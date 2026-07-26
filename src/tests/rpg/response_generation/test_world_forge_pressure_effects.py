from app.rpg.world.causal_state import build_mutable_world_state
from app.rpg.world.pressure_effects import apply_pressure_tick, pressure_deltas_for_tick


def _fixture(trend: str = "escalating"):
    pressure = {
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
    plan = {"pressures": [pressure]}
    state = build_mutable_world_state(
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
            "political_claim_graph": {"claims": []},
            "settlement_origin_plan": {"settlements": []},
            "culture_lineage_plan": {"lineages": []},
            "pressure_plan": plan,
        }
    )
    return plan, state


def test_escalating_pressure_changes_severity_and_affected_region() -> None:
    plan, state = _fixture("escalating")
    next_state, result = apply_pressure_tick(plan, state, tick=1)

    assert next_state["cells"]["pressure:001"]["values"]["pressure_severity"] == 33
    assert next_state["cells"]["ent:regions:001"]["values"]["political_stability"] == 56
    assert result.effects[0].escalated is True
    assert result.effects[0].resolved is False
    assert result.effects[0].affected_delta_ids == (
        "delta:pressure:1:pressure:001:severity",
        "delta:pressure:1:pressure:001:affected",
    )


def test_contained_pressure_reduces_severity_and_softens_region_effect() -> None:
    plan, state = _fixture("contained")
    next_state, result = apply_pressure_tick(plan, state, tick=2)

    assert next_state["cells"]["pressure:001"]["values"]["pressure_severity"] == 28
    assert next_state["cells"]["ent:regions:001"]["values"]["political_stability"] == 58
    assert result.effects[0].severity_delta == -2


def test_volatile_pressure_is_tick_deterministic() -> None:
    plan, state = _fixture("volatile")
    odd_deltas, odd_effects = pressure_deltas_for_tick(plan, state, tick=3)
    even_deltas, even_effects = pressure_deltas_for_tick(plan, state, tick=4)

    assert odd_deltas == pressure_deltas_for_tick(plan, state, tick=3)[0]
    assert odd_effects[0].severity_delta == 2
    assert even_effects[0].severity_delta == -1
    assert odd_deltas[1].value == 5
    assert even_deltas[1].value == 4


def test_pressure_tick_result_carries_reduction_receipt() -> None:
    plan, state = _fixture("escalating")
    next_state, result = apply_pressure_tick(plan, state, tick=7)

    assert result.tick == 7
    assert result.reduction.previous_state_hash == state["state_hash"]
    assert result.reduction.next_state_hash == next_state["state_hash"]
    assert result.reduction.tick == 7
