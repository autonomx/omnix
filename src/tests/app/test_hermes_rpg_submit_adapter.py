from __future__ import annotations

from app.assist_core.hermes_rpg_submit_adapter import hermes_rpg_submit_adapter


def test_hermes_rpg_submit_adapter_maps_ready_packet_to_canonical_request() -> None:
    payload = hermes_rpg_submit_adapter(
        {
            "ready_for_rpg_pipeline": True,
            "session_id": " s1 ",
            "command_text": " check inventory ",
            "context_hash": "abc",
        }
    )

    assert payload == {
        "ok": True,
        "source": "hermes_rpg_submit_adapter",
        "session_id": "s1",
        "command_text": "check inventory",
        "input": "check inventory",
        "context_hash": "abc",
        "canonical_path": "rpg_turn_execute",
        "state_changed": False,
    }


def test_hermes_rpg_submit_adapter_rejects_unready_packet() -> None:
    payload = hermes_rpg_submit_adapter({"ready_for_rpg_pipeline": False, "session_id": "s1", "command_text": "look"})

    assert payload["ok"] is False
    assert payload["error"] == "packet_not_ready"
    assert payload["state_changed"] is False


def test_hermes_rpg_submit_adapter_rejects_missing_session() -> None:
    payload = hermes_rpg_submit_adapter({"ready_for_rpg_pipeline": True, "session_id": "", "command_text": "look"})

    assert payload["ok"] is False
    assert payload["error"] == "missing_session_id"
