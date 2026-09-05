from __future__ import annotations

from pathlib import Path

from app.agent_runtime.contracts import (
    AgentRunSpec,
    ExecutionPolicy,
    ModelRef,
    WorkspaceSpec,
)
from app.agent_runtime.pi_runtime import build_agent_environment


def test_pi_worker_environment_is_minimal_and_explicit(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-env",
        task="inspect",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        workspace=WorkspaceSpec(
            root=str(tmp_path),
            allowed_paths=["src/**"],
            forbidden_paths=["src/secrets/**"],
        ),
        capabilities=["workspace.test"],
        execution=ExecutionPolicy(
            allowed_environment_keys=["EXPLICIT_SAFE_VALUE"],
        ),
    )
    parent = {
        "PATH": "/bin",
        "HOME": "/home/test",
        "SECRET_API_KEY": "must-not-leak",
        "EXPLICIT_SAFE_VALUE": "ok",
        "OMNIX_AGENT_MODEL_GATEWAY_URL": "http://gateway",
    }
    env = build_agent_environment(spec, tmp_path, parent_environment=parent)
    assert env["PATH"] == "/bin"
    assert env["EXPLICIT_SAFE_VALUE"] == "ok"
    assert "SECRET_API_KEY" not in env
    assert env["OMNIX_AGENT_MODEL_GATEWAY_URL"] == "http://gateway"
    assert env["OMNIX_AGENT_ALLOWED_PATHS"] == '["src/**"]'
    assert env["OMNIX_AGENT_FORBIDDEN_PATHS"] == '["src/secrets/**"]'
    assert env["OMNIX_AGENT_LOCAL_CAPABILITIES"] == '["workspace.test"]'
    assert env["OMNIX_AGENT_APPROVAL_POLICY"] == "ask_sensitive"
