from __future__ import annotations

import json

from app.rpg.session.response_builder import build_apply_turn_response
from app.rpg.survival_tick_runtime import (
    apply_survival_runtime_tick,
    classify_survival_tick_context,
)


def _session(*, survival=None, runtime_state=None):
    return {
        "manifest": {"id": "session:bf", "schema_version": 2},
        "simulation_state": {
            "session_id": "session:bf",
            "survival": survival or {
                "enabled": True,
                "hunger": 10,
                "thirst": 20,
                "fatigue": 30,
                "events": [],
            },
        },
        "runtime_state": runtime_state or {"tick": 1},
    }


def _authoritative_result(*, session=None, player_input="look around", tick=1, turn_id="turn:bf:1", resolved_result=None):
    return {
        "ok": True,
        "player_input": player_input,
        "authoritative": {
            "turn_id": turn_id,
            "tick": tick,
            "resolved_result": resolved_result or {
                "ok": True,
                "player_input": player_input,
                "summary": "The turn resolves.",
            },
            "deterministic_fallback_narration": "You take stock of the moment.",
        },
        "result": {
            "turn_id": turn_id,
            "tick": tick,
            "player_input": player_input,
        },
        "turn_contract": {
            "ok": True,
            "turn_id": turn_id,
            "tick": tick,
            "player_input": player_input,
            "resolved_result": resolved_result or {"ok": True, "player_input": player_input},
        },
        "session": session or _session(runtime_state={"tick": tick}),
    }


def test_bundle_bf_classifies_context_without_llm() -> None:
    assert classify_survival_tick_context(player_input="I travel to the old road")["profile"] == "travel"
    assert classify_survival_tick_context(player_input="I wait and listen")["profile"] == "wait"
    assert classify_survival_tick_context(player_input="I sleep for the night")["profile"] == "sleep"
    direct = classify_survival_tick_context(
        player_input="I drink water",
        survival_result={"action_category": "survival", "action": "drink_water"},
    )
    assert direct["profile"] == "survival_action"
    assert direct["skip_tick"] is True


def test_bundle_bf_standard_turn_applies_one_passive_tick_and_records_evidence() -> None:
    session = _session(runtime_state={"tick": 3})
    authoritative_result = _authoritative_result(
        session=session,
        player_input="look around the tavern",
        tick=3,
        turn_id="turn:bf:standard",
    )

    response = build_apply_turn_response(authoritative_result)

    survival = response["session"]["simulation_state"]["survival"]
    assert survival["hunger"] == 11
    assert survival["thirst"] == 22
    assert survival["fatigue"] == 31
    assert survival["events"][-1]["kind"] == "survival_tick"
    assert survival["events"][-1]["reason"] == "standard_turn"
    tick_result = response["turn_contract"]["survival_tick_result"]
    assert tick_result["applied"] is True
    assert tick_result["reason"] == "standard_turn"
    assert response["result"]["survival_tick_result"] == tick_result
    history = response["session"]["runtime_state"]["survival_tick_history"]
    assert history[-1]["turn_id"] == "turn:bf:standard"
    json.dumps(response)


def test_bundle_bf_travel_turn_uses_higher_pressure_rates() -> None:
    session = _session(
        survival={
            "enabled": True,
            "hunger": 10,
            "thirst": 20,
            "fatigue": 30,
            "events": [],
        },
        runtime_state={"tick": 4},
    )
    authoritative_result = _authoritative_result(
        session=session,
        player_input="travel to the ruined mill",
        tick=4,
        turn_id="turn:bf:travel",
    )

    response = build_apply_turn_response(authoritative_result)

    survival = response["session"]["simulation_state"]["survival"]
    assert survival["hunger"] == 12
    assert survival["thirst"] == 23
    assert survival["fatigue"] == 32
    assert response["result"]["survival_tick_result"]["context"]["profile"] == "travel"


def test_bundle_bf_direct_survival_action_does_not_double_tick() -> None:
    session = _session(
        survival={
            "enabled": True,
            "hunger": 10,
            "thirst": 40,
            "fatigue": 30,
            "events": [{"kind": "drink_water", "source": "runtime_action_resolver"}],
        },
        runtime_state={"tick": 5},
    )
    resolved_result = {
        "ok": True,
        "player_input": "drink water",
        "survival_result": {
            "ok": True,
            "action_category": "survival",
            "action": "drink_water",
            "effects": {"thirst_delta": -30},
        },
    }
    authoritative_result = _authoritative_result(
        session=session,
        player_input="drink water",
        tick=5,
        turn_id="turn:bf:drink",
        resolved_result=resolved_result,
    )

    response = build_apply_turn_response(authoritative_result)

    survival = response["session"]["simulation_state"]["survival"]
    assert survival["hunger"] == 10
    assert survival["thirst"] == 40
    assert survival["fatigue"] == 30
    tick_result = response["result"]["survival_tick_result"]
    assert tick_result["applied"] is False
    assert tick_result["skipped"] is True
    assert tick_result["reason"] == "direct_survival_action"


def test_bundle_bf_tick_is_idempotent_per_turn_id() -> None:
    session = _session(runtime_state={"tick": 6})
    authoritative_result = _authoritative_result(
        session=session,
        player_input="look around",
        tick=6,
        turn_id="turn:bf:idempotent",
    )
    first = apply_survival_runtime_tick(
        authoritative_result=authoritative_result,
        session=session,
        turn_contract=authoritative_result["turn_contract"],
        result_payload=authoritative_result["result"],
        resolved_result=authoritative_result["authoritative"]["resolved_result"],
    )
    second = apply_survival_runtime_tick(
        authoritative_result=authoritative_result,
        session=first["session"],
        turn_contract=first["turn_contract"],
        result_payload=first["result_payload"],
        resolved_result=first["result_payload"]["resolved_result"],
    )

    assert first["session"]["simulation_state"]["survival"]["hunger"] == 11
    assert second["session"]["simulation_state"]["survival"]["hunger"] == 11
    assert second["survival_tick_result"]["applied"] is False
    assert second["survival_tick_result"]["skipped"] is True
    assert second["survival_tick_result"]["reason"] == "already_applied_for_turn"
