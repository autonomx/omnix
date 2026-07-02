from __future__ import annotations

from typing import Any

from app.assist_core.hermes_rpg_submit_bridge import hermes_rpg_submit_bridge


def test_hermes_rpg_submit_bridge_calls_submitter_when_ready() -> None:
    seen: list[dict[str, Any]] = []

    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload)
        return {"ok": True, "turn_id": 9}

    payload = hermes_rpg_submit_bridge(
        {"ready_for_rpg_pipeline": True, "session_id": "s1", "command_text": "check inventory"},
        submitter,
    )

    assert seen == [
        {
            "ok": True,
            "source": "hermes_rpg_submit_adapter",
            "session_id": "s1",
            "command_text": "check inventory",
            "input": "check inventory",
            "context_hash": None,
            "canonical_path": "rpg_turn_execute",
            "state_changed": False,
        }
    ]
    assert payload["ok"] is True
    assert payload["rpg_result"] == {"ok": True, "turn_id": 9}
    assert payload["state_changed"] is True


def test_hermes_rpg_submit_bridge_blocks_unready_packet() -> None:
    def submitter(payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("submitter should not be called")

    payload = hermes_rpg_submit_bridge({"ready_for_rpg_pipeline": False}, submitter)

    assert payload["ok"] is False
    assert payload["error"] == "packet_not_ready"
    assert payload["state_changed"] is False
