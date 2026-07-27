from copy import deepcopy

from app.rpg.economy.price_modifiers import calculate_price_modifier
from app.rpg.locations.travel import apply_causal_travel_projection
from app.rpg.session.causal_turn_runtime import advance_causal_runtime_for_turn
from app.rpg.world.causal_runtime import bootstrap_causal_runtime


def _planning_topics():
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
        "political_claim_graph": {
            "claims": [
                {
                    "claim_id": "claim:001",
                    "claimant_group_id": "ent:groups:001",
                    "control_index": 50,
                }
            ]
        },
        "settlement_origin_plan": {"settlements": []},
        "culture_lineage_plan": {"lineages": []},
        "opening_scope_plan": {"actor_ids": ["ent:actors:001"]},
        "pressure_plan": {
            "pressures": [
                {
                    "pressure_id": "pressure:001",
                    "severity": 30,
                    "trend": "escalating",
                    "affected_group_ids": ["ent:groups:001"],
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


def _session_with_bootstrap():
    runtime = bootstrap_causal_runtime(_planning_topics())
    return {
        "simulation_state": {
            "campaign_bible": {
                "manifest": {"causal_runtime_bootstrap": runtime}
            }
        },
        "runtime_state": {
            "tick": 1,
            "last_turn_contract": {
                "turn_id": "turn:001",
                "turn_index": 1,
            },
        },
    }


def test_authoritative_turn_installs_projects_and_is_idempotent() -> None:
    store = {"session:001": _session_with_bootstrap()}
    saves = []

    def loader(session_id):
        return deepcopy(store.get(session_id))

    def saver(session):
        store["session:001"] = deepcopy(session)
        saves.append(deepcopy(session))

    payload = {
        "ok": True,
        "turn": 1,
        "turn_id": "turn:001",
        "result": {"ok": True},
        "authoritative": {"mechanic_resolved": True},
    }
    first = advance_causal_runtime_for_turn(
        "session:001",
        payload,
        loader=loader,
        saver=saver,
    )

    receipt = first["causal_world_runtime"]
    simulation = first["session"]["simulation_state"]
    assert receipt["applied"] is True
    assert receipt["tick"] == 1
    assert simulation["causal_world_runtime"]["last_tick"] == 1
    assert simulation["causal_runtime_projection"]["tick"] == 1
    assert simulation["economy_state"]["causal_price_multiplier_bps"] > 10000
    assert simulation["travel_state"]["causal_cost_multiplier_bps"] > 10000
    assert simulation["faction_reputation"]["ent:groups:001"]["causal_control_index"] == 50
    assert simulation["npc_presence"]["ent:actors:001"]["next_action"]["pressure_id"] == "pressure:001"
    assert first["simulation_state"] == simulation
    assert first["result"]["causal_world_runtime"]["applied"] is True
    assert first["authoritative"]["causal_world_runtime"]["applied"] is True
    assert len(saves) == 1

    repeated = advance_causal_runtime_for_turn(
        "session:001",
        payload,
        loader=loader,
        saver=saver,
    )
    assert repeated["causal_world_runtime"]["applied"] is False
    assert repeated["causal_world_runtime"]["reason"] == "turn_already_applied"
    assert store["session:001"]["simulation_state"]["causal_world_runtime"]["last_tick"] == 1
    assert len(saves) == 1


def test_legacy_session_without_bootstrap_is_unchanged() -> None:
    session = {"simulation_state": {}, "runtime_state": {"tick": 1}}
    saved = []

    result = advance_causal_runtime_for_turn(
        "legacy:001",
        {"ok": True, "turn": 1},
        loader=lambda _session_id: deepcopy(session),
        saver=lambda value: saved.append(value),
    )

    assert result == {"ok": True, "turn": 1}
    assert saved == []


def test_causal_economy_and_travel_projections_are_consumed() -> None:
    buy = calculate_price_modifier(
        player_state={},
        merchant_state={
            "causal_price_multiplier_bps": 12000,
            "stock": [{"item_id": "ration", "qty": 4}],
        },
        merchant_id="merchant:test",
        item_id="ration",
        kind="buy",
    )
    assert any(
        row.get("modifier") == "causal_world_economy"
        and row.get("basis_points_delta") == 2000
        for row in buy["modifiers"]
    )
    assert buy["multiplier_bps"] == 12000

    travel = apply_causal_travel_projection(
        {
            "ok": True,
            "totals": {
                "minutes": 20,
                "fatigue": 4,
                "ration_units": 1,
                "water_units": 1,
            },
            "risk_flags": [],
        },
        {
            "causal_cost_multiplier_bps": 12500,
            "causal_safety_index": 20,
        },
    )
    assert travel["base_totals"]["minutes"] == 20
    assert travel["totals"]["minutes"] == 25
    assert travel["totals"]["fatigue"] == 5
    assert "causal_instability" in travel["risk_flags"]
