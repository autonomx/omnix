from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core.hermes_rpg_approved_routes import (
    hermes_rpg_approved_flow_config_route,
    hermes_rpg_approved_flow_route_payload,
)


def test_hermes_rpg_approved_flow_route_is_disabled_by_default() -> None:
    payload = hermes_rpg_approved_flow_route_payload(
        {
            "enabled": True,
            "user_step": {"ready": True, "command_text": "look"},
            "replay_entry": {"ok": True, "command_text": "look"},
            "context": {"session_id": "s1"},
        }
    )

    assert payload == {
        "ok": False,
        "source": "hermes_rpg_approved_flow_route",
        "error": "hermes_rpg_approved_flow_disabled",
        "enabled": False,
        "config": {
            "ok": True,
            "source": "hermes_rpg_approved_flow_config",
            "feature_flag": FEATURE_FLAG,
            "default_enabled": False,
            "enabled": False,
            "requires_payload_enabled": True,
            "simulation_owned": True,
        },
        "state_changed": False,
    }


def test_hermes_rpg_approved_flow_config_route_is_disabled_by_default() -> None:
    assert hermes_rpg_approved_flow_config_route()["enabled"] is False


def test_hermes_rpg_approved_flow_route_accepts_fake_submitter_when_enabled() -> None:
    seen: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload)
        return {"ok": True, "turn": 7, "narration": "You look around."}

    payload = hermes_rpg_approved_flow_route_payload(
        {
            "enabled": True,
            "user_step": {"ready": True, "command_text": "look around"},
            "replay_entry": {"ok": True, "command_text": "look around"},
            "context": {"session_id": "s1", "context_hash": "abc"},
        },
        submitter=submitter,
        environ={FEATURE_FLAG: "1"},
    )

    assert seen == [
        {
            "ok": True,
            "source": "hermes_rpg_submit_adapter",
            "session_id": "s1",
            "command_text": "look around",
            "input": "look around",
            "context_hash": "abc",
            "canonical_path": "rpg_turn_execute",
            "state_changed": False,
        }
    ]
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["source"] == "hermes_rpg_approved_flow_route"
    assert payload["config"]["enabled"] is True
    assert payload["readout"]["status"] == "accepted"
    assert payload["readout"]["session_id"] == "s1"
    assert payload["flow"]["result"]["rpg_result"] == {"ok": True, "turn": 7, "narration": "You look around."}
    assert payload["state_changed"] is True
