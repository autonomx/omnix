from __future__ import annotations

from pathlib import Path
import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.isolation import AgentIsolationError, DockerStrongIsolation, isolation_for_spec


def test_unattended_policy_selects_strong_backend() -> None:
    spec = AgentRunSpec(
        run_id="run-strong",
        task="inspect",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root="C:/work", isolation_policy="unattended"),
    )
    assert isolation_for_spec(spec).strong is True


def test_strong_backend_fails_closed_without_operator_configuration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OMNIX_AGENT_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_DOCKER_NETWORK", raising=False)
    isolation = DockerStrongIsolation(image=None, network=None)
    isolation.docker = "docker"
    spec = AgentRunSpec(
        run_id="run-strong",
        task="inspect",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(tmp_path), isolation_policy="docker_strong"),
    )
    with pytest.raises(AgentIsolationError):
        isolation.build_command(spec, argv=["pi", "--mode", "rpc"], cwd=tmp_path, env={})
