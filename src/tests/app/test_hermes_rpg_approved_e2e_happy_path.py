from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_flow_route_payload
from app.assist_core.hermes_rpg_flow_readout import hermes_rpg_flow_readout


def test_hermes_rpg_approved_flow_happy_path_reaches_rpg_turn_result() -> None:
    submitted: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        submitted.append(payload)
        return {
            "ok": True,
            "success": True,
            "source": "fake_rpg_turn_executor",
            "session_id": payload["session_id"],
            "command_text": payload["command_text"],
            "turn": 24,
            "narration": "You inspect the room and mark the exits.",
            "state_changes": {"last_action": payload["command_text"]},
            "events": [{"type": "player_command", "command": payload["command_text"]}],
            "player": {"name": "Test Hero"},
            "state_changed": True,
        }

    result = hermes_rpg_approved_flow_route_payload(
        {
            "enabled": True,
            "user_step": {"ready": True, "command_text": "inspect the room"},
            "replay_entry": {"ok": True, "command_text": "inspect the room"},
            "context": {"session_id": "session-24", "context_hash": "ctx-24"},
        },
        submitter=submitter,
        environ={FEATURE_FLAG: "on"},
    )

    assert result["ok"] is True
    assert result["enabled"] is True
    assert result["config"]["enabled"] is True
    assert result["state_changed"] is True
    assert submitted == [
        {
            "ok": True,
            "source": "hermes_rpg_submit_adapter",
            "session_id": "session-24",
            "command_text": "inspect the room",
            "input": "inspect the room",
            "context_hash": "ctx-24",
            "canonical_path": "rpg_turn_execute",
            "state_changed": False,
        }
    ]

    flow = result["flow"]
    rpg_result = flow["result"]["rpg_result"]
    assert flow["packet"]["ready_for_rpg_pipeline"] is True
    assert rpg_result["source"] == "fake_rpg_turn_executor"
    assert rpg_result["turn"] == 24
    assert rpg_result["events"] == [{"type": "player_command", "command": "inspect the room"}]

    readout = hermes_rpg_flow_readout(flow)
    assert result["readout"] == readout
    assert readout["ok"] is True
    assert readout["status"] == "accepted"
    assert readout["session_id"] == "session-24"
    assert readout["command_text"] == "inspect the room"
    assert readout["state_changed"] is True
