from __future__ import annotations

from app.rpg.session.runtime_promotions import (
    attach_runtime_promotion_payloads,
    build_climate_survival_runtime_payload,
    build_runtime_promotion_summary,
)


def test_n1222_climate_survival_runtime_payload_is_deterministic_from_live_tick() -> None:
    simulation_state = {
        "tick": 4,
        "player_state": {
            "resources": {
                "hunger": 9,
                "thirst": 11,
                "fatigue": 7,
            }
        },
    }
    runtime_state = {"tick": 4}

    payload = build_climate_survival_runtime_payload(simulation_state, runtime_state)

    assert payload["ok"] is True
    assert payload["runtime_promoted"] is True
    assert payload["source"] == "deterministic_live_session_runtime"
    assert payload["tick"] == 4
    assert payload["time"]["day"] == 1
    assert payload["time"]["hour"] == 1
    assert payload["survival"]["hunger"] == 9
    assert payload["survival"]["thirst"] == 11
    assert payload["survival"]["fatigue"] == 7
    assert payload["display"]["title"] == "Climate + Survival"
    assert "runtime_state.climate_survival" in payload["turn_contract_keys"]


def test_n1222_runtime_promotion_summary_uses_live_runtime_evidence() -> None:
    simulation_state = {
        "tick": 2,
        "player_state": {
            "nearby_npc_ids": ["npc:bran"],
            "inventory_state": {
                "currency": {"copper": 10},
                "items": [{"id": "ration"}],
            },
        },
    }
    runtime_state = {
        "tick": 2,
        "world_pressure": [{"kind": "security_presence", "value": 1}],
        "world_consequences": [{"kind": "rumor", "summary": "Road talk spreads."}],
        "actor_activities": {"npc:bran": {"kind": "serve", "summary": "Bran serves guests."}},
        "transaction_menus": [{"menu_id": "inn_services"}],
        "combat_state": {"round": 1, "turn_index": 0, "participants": {"player": {}, "enemy": {}}},
    }

    summary = build_runtime_promotion_summary(simulation_state, runtime_state)

    assert summary["system_count"] == 5
    assert summary["runtime_promoted_count"] == 5
    assert summary["partial_or_missing_count"] == 0
    assert summary["ok"] is True
    assert {item["name"] for item in summary["systems"]} == {
        "N97-N99 memory_aging_world_state_compression",
        "N100-N102 npc_goal_agency_schedules",
        "N103-N105 economy_pressure_resource_sinks",
        "N106-N108 combat_lifecycle_expansion",
        "N122 climate_survival_runtime_payload",
    }


def test_n1222_attach_runtime_promotion_payloads_embeds_live_payloads() -> None:
    simulation_state = {"tick": 1, "player_state": {"inventory_state": {"items": []}}}
    runtime_state = {"tick": 1, "combat_state": {"participants": {"player": {}}}}

    payload = attach_runtime_promotion_payloads(
        {"presentation": {"existing": True}},
        simulation_state,
        runtime_state,
    )

    assert payload["climate_survival"]["ok"] is True
    assert payload["climate_survival_runtime_payload"]["runtime_promoted"] is True
    assert payload["runtime_promotion_summary"]["system_count"] == 5
    assert payload["runtime_promotion_panel"]["format_version"] == "n1222_runtime_promotion_panel_v1"
    assert payload["runtime_state"]["climate_survival"]["ok"] is True
    assert payload["runtime_state"]["runtime_promotion_summary"]["system_count"] == 5
    assert payload["presentation"]["existing"] is True
    assert payload["presentation"]["climate_survival"]["ok"] is True
    assert payload["presentation"]["runtime_promotion_panel"]["cards"]
