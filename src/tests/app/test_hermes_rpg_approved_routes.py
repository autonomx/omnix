from __future__ import annotations

from app.assist_core.hermes_rpg_approved_routes import hermes_rpg_approved_flow_route_payload


def test_hermes_rpg_approved_flow_route_is_disabled_by_default() -> None:
    payload = hermes_rpg_approved_flow_route_payload(
        {
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
        "state_changed": False,
    }
