from __future__ import annotations

from app.assist_core.omnix_mode_api_surface import omnix_mode_surfaces


def test_omnix_mode_surface_is_read_only() -> None:
    surface = omnix_mode_surfaces()[0]

    assert surface["method"] == "GET"
    assert surface["read_only"] is True
    assert surface["executes"] is False
