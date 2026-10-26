from app.apps.rpg.world.causal_state import build_mutable_world_state
from app.apps.rpg.world.pressure_effects import apply_pressure_tick, pressure_deltas_for_tick


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
    assert result.effects[0].status_before == "active"
    assert result.effects[0].status_after == "escalated"
    assert result.effects[0].transitioned is True
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
    assert result.effects[0].status_after == "contained"


def test_volatile_pressure_is_tick_deterministic() -> None:
    plan, state = _fixture("volatile")
    odd_deltas, odd_effects = pressure_deltas_for_tick(plan, state, tick=3)
    even_deltas, even_effects = pressure_deltas_for_tick(plan, state, tick=4)

    assert odd_deltas == pressure_deltas_for_tick(plan, state, tick=3)[0]
    assert odd_effects[0].severity_delta == 2
    assert even_effects[0].severity_delta == -1
    assert odd_deltas[1].value == 5
    assert even_deltas[1].value == 4


def test_resolved_pressure_stops_emitting_deltas() -> None:
    plan, state = _fixture("contained")
    state["cells"]["pressure:001"]["values"]["pressure_severity"] = 19

    resolved_state, first = apply_pressure_tick(
        plan,
        state,
        tick=1,
        pressure_statuses={"pressure:001": "active"},
    )
    repeated_state, second = apply_pressure_tick(
        plan,
        resolved_state,
        tick=2,
        pressure_statuses={"pressure:001": "resolved"},
    )

    assert first.effects[0].status_after == "resolved"
    assert first.effects[0].resolved is True
    assert second.deltas == ()
    assert second.effects[0].status_before == "resolved"
    assert second.effects[0].status_after == "resolved"
    assert second.effects[0].transitioned is False
    assert repeated_state["state_hash"] == resolved_state["state_hash"]


def test_an_escalated_pressure_is_answered_by_the_world_and_stirs_again() -> None:
    """Roadmap §7 Q-10: a rising pressure that escalated is held in check (it falls as a contained one does), never
    escalated again on the next tick, and stirs again WORLD_ANSWER_SPAN below its escalation threshold."""
    from app.apps.rpg.world.pressure_effects import WORLD_ANSWER_SPAN

    plan, state = _fixture("escalating")
    threshold = float(plan["pressures"][0]["escalation_threshold"])
    state["cells"]["pressure:001"]["values"]["pressure_severity"] = threshold + 5

    _, held = apply_pressure_tick(plan, state, tick=2, pressure_statuses={"pressure:001": "escalated"})
    assert (held.effects[0].status_after, held.effects[0].escalated) == ("contained", False)
    assert held.effects[0].severity_delta < 0

    state["cells"]["pressure:001"]["values"]["pressure_severity"] = threshold - WORLD_ANSWER_SPAN + 1
    _, stirring = apply_pressure_tick(plan, state, tick=3, pressure_statuses={"pressure:001": "contained"})
    assert stirring.effects[0].status_after == "active" and stirring.effects[0].transitioned is True


def test_pressure_tick_result_carries_reduction_receipt() -> None:
    plan, state = _fixture("escalating")
    next_state, result = apply_pressure_tick(plan, state, tick=7)

    assert result.tick == 7
    assert result.reduction.previous_state_hash == state["state_hash"]
    assert result.reduction.next_state_hash == next_state["state_hash"]
    assert result.reduction.tick == 7
