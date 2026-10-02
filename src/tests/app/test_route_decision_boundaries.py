from __future__ import annotations

from app.assist_core.omnix_mode_router import omnix_mode_route


def test_rpg_route_remains_simulation_owned() -> None:
    route = omnix_mode_route("rpg")

    assert route["execution_owner"] == "rpg_sim"
    assert route["hermes_role"] == "suggest"
    assert route["direct_provider_path"] is False
