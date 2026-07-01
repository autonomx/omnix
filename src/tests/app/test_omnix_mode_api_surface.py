from __future__ import annotations

from app.assist_core.omnix_mode_api_surface import omnix_mode_surfaces


def test_omnix_mode_surface_is_read_only() -> None:
    surface = omnix_mode_surfaces()[0]

    assert surface["method"] == "GET"
    assert surface["read_only"] is True
    assert surface["executes"] is False


def test_plan_route_surface_is_review_gated_and_non_executing() -> None:
    surfaces = {surface["path"]: surface for surface in omnix_mode_surfaces()}

    assert surfaces["agent_plan"] == {
        "method": "POST",
        "path": "agent_plan",
        "read_only": True,
        "executes": False,
        "requires_review": True,
    }
    assert surfaces["agent_plan_status"] == {
        "method": "GET",
        "path": "agent_plan_status",
        "read_only": True,
        "executes": False,
        "requires_review": True,
    }
