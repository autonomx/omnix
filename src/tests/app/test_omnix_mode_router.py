from __future__ import annotations

from app.assist_core.omnix_mode_router import list_omnix_mode_routes, omnix_mode_route, omnix_mode_router_payload


def test_omnix_mode_router_lists_expected_modes() -> None:
    routes = list_omnix_mode_routes()

    assert [route["mode"] for route in routes] == [
        "normal_chat",
        "live_chat",
        "agent_mode",
        "house_ai",
        "podcast",
        "rpg",
    ]


def test_omnix_mode_router_keeps_execution_owners_explicit() -> None:
    assert omnix_mode_route("normal_chat")["execution_owner"] == "provider"
    assert omnix_mode_route("live_chat")["execution_owner"] == "voice_pipeline"
    assert omnix_mode_route("agent_mode")["requires_approval"] is True
    assert omnix_mode_route("house_ai")["requires_approval"] is True
    assert omnix_mode_route("podcast")["execution_owner"] == "audio_pipeline"
    assert omnix_mode_route("rpg")["execution_owner"] == "rpg_sim"
    assert omnix_mode_route("rpg")["hermes_role"] == "suggest"


def test_omnix_mode_router_payload_handles_single_and_unknown_modes() -> None:
    assert omnix_mode_router_payload("rpg") == {"ok": True, "route": omnix_mode_route("rpg")}
    assert omnix_mode_router_payload("unknown") == {"ok": False, "error": "unknown_mode", "mode": "unknown"}
