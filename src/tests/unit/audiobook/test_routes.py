from __future__ import annotations

from app.gateway.main import create_gateway_app


def test_audiobook_api_is_registered_on_gateway() -> None:
    gateway = create_gateway_app()
    paths = {route.path for route in gateway.routes}
    assert "/api/audiobook/projects" in paths
    assert "/api/audiobook/projects/{project_id}" in paths
    assert "/api/audiobook/projects/{project_id}/source" in paths
