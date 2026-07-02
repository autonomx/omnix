from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_approved_config import FEATURE_FLAG
from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_flow_route_payload


def test_hermes_rpg_approved_flow_replays_same_canonical_submit_payload() -> None:
    seen: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(dict(payload))
        return {
            "ok": True,
            "source": "fake_rpg_turn",
            "session_id": payload["session_id"],
            "command_text": payload["command_text"],
            "turn": 12,
            "narration": "Deterministic turn result.",
            "state_changed": True,
        }

    request = {
        "enabled": True,
        "user_step": {"ready": True, "command_text": "look around"},
        "replay_entry": {"ok": True, "command_text": "look around"},
        "context": {"session_id": "s1", "context_hash": "ctx-1"},
    }
    environ = {FEATURE_FLAG: "true"}

    first = hermes_rpg_approved_flow_route_payload(request, submitter=submitter, environ=environ)
    second = hermes_rpg_approved_flow_route_payload(request, submitter=submitter, environ=environ)

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["state_changed"] is True
    assert second["state_changed"] is True
    assert seen[0] == seen[1]
    assert seen[0] == {
        "ok": True,
        "source": "hermes_rpg_submit_adapter",
        "session_id": "s1",
        "command_text": "look around",
        "input": "look around",
        "context_hash": "ctx-1",
        "canonical_path": "rpg_turn_execute",
        "state_changed": False,
    }
    assert first["readout"] == second["readout"]
    assert first["flow"]["result"]["rpg_result"] == second["flow"]["result"]["rpg_result"]
    assert first["flow"]["packet"]["ready_for_rpg_pipeline"] is True
    assert first["flow"]["packet"]["session_id"] == "s1"
    assert first["flow"]["packet"]["context_hash"] == "ctx-1"
