from __future__ import annotations

import json

from app.rpg.session.response_builder import build_apply_turn_response
from app.rpg.survival_action_context import (
    attach_survival_action_context,
    build_survival_action_context,
)


def _simulation_state(*, hunger=0, thirst=0, fatigue=0, items=None):
    return {
        "session_id": "test-session",
        "survival": {
            "enabled": True,
            "hunger": hunger,
            "thirst": thirst,
            "fatigue": fatigue,
            "events": [],
        },
        "player_state": {
            "inventory": {
                "items": list(items or []),
                "equipment": {},
                "carry_capacity": 50,
            }
        },
    }


def test_bundle_bd_builds_survival_pressure_and_recommended_actions_from_ba_state() -> None:
    simulation_state = _simulation_state(
        hunger=35,
        thirst=82,
        fatigue=64,
        items=[
            {
                "item_id": "item:water",
                "definition_id": "def:water",
                "name": "Water",
                "kind": "supply",
                "quantity": 1,
                "stackable": True,
                "tags": ["water", "survival"],
            },
            {
                "item_id": "item:rations",
                "definition_id": "def:rations",
                "name": "Trail Rations",
                "kind": "supply",
                "quantity": 1,
                "stackable": True,
                "tags": ["rations", "food", "survival"],
            },
        ],
    )

    context = build_survival_action_context(simulation_state)

    assert context["format_version"] == "survival_action_context_v1"
    assert context["survival_pressure"] == {
        "hunger": "moderate",
        "thirst": "critical",
        "fatigue": "high",
    }
    assert [row["action"] for row in context["recommended_actions"]] == [
        "drink water",
        "rest",
        "eat rations",
    ]
    assert [row["action"] for row in context["suggested_actions"]] == [
        "drink water",
        "rest",
    ]
    assert context["autoplay_pressure"]["should_respond"] is True
    assert context["autoplay_pressure"]["top_action"] == "drink water"
    json.dumps(context)


def test_bundle_bd_attach_survival_action_context_merges_without_duplicate_domination() -> None:
    simulation_state = _simulation_state(thirst=90, hunger=90, fatigue=10)
    payload = {
        "suggested_actions": [
            {"action_id": "survival:buy_water", "action": "buy water"},
            {"action_id": "story:ask_bran", "action": "ask Bran about the road"},
        ],
        "next_actions": [
            {"action_id": "story:ask_bran", "action": "ask Bran about the road"},
        ],
    }

    attached = attach_survival_action_context(payload, simulation_state)

    suggested_ids = [row["action_id"] for row in attached["suggested_actions"]]
    assert suggested_ids.count("survival:buy_water") == 1
    assert "survival:buy_rations" in suggested_ids
    assert "story:ask_bran" in suggested_ids
    next_ids = [row["action_id"] for row in attached["next_actions"]]
    assert "survival:buy_water" in next_ids
    assert "survival:buy_rations" in next_ids
    assert attached["autoplay_survival_pressure"]["should_respond"] is True


def test_bundle_bd_low_pressure_exports_context_but_no_suggested_actions() -> None:
    simulation_state = _simulation_state(hunger=10, thirst=20, fatigue=24)

    context = build_survival_action_context(simulation_state)

    assert context["survival_pressure"] == {
        "hunger": "low",
        "thirst": "low",
        "fatigue": "low",
    }
    assert context["recommended_actions"] == []
    assert context["suggested_actions"] == []
    assert context["next_actions"] == []
    assert context["autoplay_pressure"]["should_respond"] is False


def test_bundle_bd_build_apply_turn_response_projects_survival_action_context() -> None:
    simulation_state = _simulation_state(
        hunger=55,
        thirst=75,
        fatigue=10,
        items=[
            {
                "item_id": "item:water",
                "definition_id": "def:water",
                "name": "Water",
                "kind": "supply",
                "quantity": 1,
                "stackable": True,
                "tags": ["water", "survival"],
            }
        ],
    )
    authoritative_result = {
        "ok": True,
        "authoritative": {
            "resolved_result": {
                "ok": True,
                "summary": "The turn resolves.",
            },
            "deterministic_fallback_narration": "You pause and take stock.",
        },
        "result": {
            "turn_id": "turn-1",
            "tick": 1,
        },
        "turn_contract": {
            "ok": True,
            "resolved_result": {
                "ok": True,
            },
        },
        "session": {
            "manifest": {"id": "test-session"},
            "simulation_state": simulation_state,
            "runtime_state": {"tick": 1},
        },
    }

    response = build_apply_turn_response(authoritative_result)

    assert response["ok"] is True
    assert response["turn_contract"]["survival_pressure"]["thirst"] == "critical"
    assert response["result"]["survival_pressure"]["hunger"] == "high"
    assert response["result"]["autoplay_survival_pressure"]["should_respond"] is True
    assert [row["action"] for row in response["result"]["suggested_actions"]][:2] == [
        "drink water",
        "buy rations",
    ]
    json.dumps(response)
