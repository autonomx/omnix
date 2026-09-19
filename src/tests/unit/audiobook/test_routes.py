from __future__ import annotations

import subprocess
import sys

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
    assert "/api/audiobook/projects/{project_id}/jobs/{job_id}/retry" in paths


def test_gateway_registration_does_not_import_audiobook_runtime_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from app.gateway.main import create_gateway_app; "
                "create_gateway_app(); "
                "assert 'app.audiobook.service' not in sys.modules; "
                "assert 'app.providers.faster_qwen3_tts_provider' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
