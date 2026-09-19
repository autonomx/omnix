from __future__ import annotations

from app.gateway.main import create_gateway_app


def test_audiobook_api_is_registered_on_gateway() -> None:
    gateway = create_gateway_app()
    paths = {route.path for route in gateway.routes}
    assert "/api/audiobook/projects" in paths
    assert "/api/audiobook/projects/{project_id}" in paths
    assert "/api/audiobook/projects/{project_id}/source" in paths
    assert "/api/audiobook/projects/{project_id}/cover" in paths
    assert "/api/audiobook/projects/{project_id}/speakers" in paths
    assert "/api/audiobook/projects/{project_id}/speakers/{speaker_id}/casting" in paths
    assert "/api/audiobook/projects/{project_id}/review/{issue_id}" in paths
    assert "/api/audiobook/projects/{project_id}/spans/{span_id}/annotation" in paths
    assert "/api/audiobook/projects/{project_id}/render" in paths
    assert "/api/audiobook/projects/{project_id}/jobs/{job_id}/cancel" in paths
