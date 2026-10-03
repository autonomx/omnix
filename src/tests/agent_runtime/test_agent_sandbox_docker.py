"""The agent sandbox network reaches the broker relay and nothing else (WP-4.7).

Needs Docker and the sandbox image (`python -m app.agent_runtime.sandbox build`);
skipped where either is missing.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from app.agent_runtime.isolation import DockerStrongIsolation
from app.agent_runtime.sandbox import check_egress


def _sandbox_available() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        image = DockerStrongIsolation().image
        return subprocess.run([docker, "image", "inspect", image], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _sandbox_available(), reason="Docker and the agent sandbox image are required")


def test_the_sandbox_reaches_the_relay_but_not_the_internet(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_DOCKER_NETWORK", raising=False)
    result = check_egress("http://127.0.0.1:8000/api/agent-runs", "1.1.1.1:443")
    assert result["relay_reachable"] is True
    assert result["egress_blocked"] is True


def test_the_sandbox_cannot_reach_another_host_port_directly(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_DOCKER_NETWORK", raising=False)
    # The gateway host itself is reachable only through the relay's routes.
    result = check_egress("http://127.0.0.1:8000/api/agent-runs", "host.docker.internal:8000")
    assert result["egress_blocked"] is True


def test_a_preview_runs_in_the_sandbox_and_answers_on_loopback(tmp_path, monkeypatch) -> None:
    import json
    import socket
    import time
    import urllib.request

    from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
    from app.agent_runtime.isolation import remove_containers, start_sandboxed_preview

    monkeypatch.delenv("OMNIX_AGENT_DOCKER_NETWORK", raising=False)
    package = tmp_path / "web"
    package.mkdir()
    (package / "package.json").write_text(json.dumps({"name": "preview", "scripts": {"dev": "node server.js"}}))
    # A dev server without dependencies; it also tries to reach the internet.
    (package / "server.js").write_text(
        "const port = +process.argv[process.argv.indexOf('--port') + 1];\n"
        "let egress = 'unknown';\n"
        "fetch('https://example.com/').then(() => { egress = 'open'; }).catch(() => { egress = 'blocked'; });\n"
        "require('http').createServer((q, r) => r.end(egress)).listen(port, '0.0.0.0');\n"
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    spec = AgentRunSpec(run_id="run-preview-test", task="preview", model=ModelRef(provider_id="t", model_id="m"),
                        workspace=WorkspaceSpec(root=str(tmp_path)), capabilities=["workspace.edit"])
    process, containers = start_sandboxed_preview(spec, root=tmp_path, package="web", port=port)
    try:
        body = ""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode()
                if body != "unknown":
                    break
            except OSError:
                pass
            time.sleep(0.5)
        assert body == "blocked"
    finally:
        process.kill()
        remove_containers(containers)
