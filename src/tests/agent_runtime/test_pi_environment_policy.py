from __future__ import annotations

import json
from pathlib import Path

from app.agent_runtime.contracts import (
    AgentRunSpec,
    ExecutionPolicy,
    ModelRef,
    ResourceScope,
    WorkspaceSpec,
)
from app.agent_runtime.pi_runtime import agent_path_roots, build_agent_environment


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


def test_pi_worker_environment_can_bind_a_fresh_model_session(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-env-session",
        task="inspect",
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-test"),
    )

    env = build_agent_environment(spec, tmp_path, model_session_id="session-1")

    assert env["OMNIX_AGENT_MODEL_SESSION_ID"] == "session-1"


def test_pi_worker_environment_normalizes_windows_paths_before_launch(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-env-windows",
        task="inspect",
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-test"),
    )
    parent = {
        "PATH": r"C:\tools",
        "SYSTEMROOT": r"C:\Windows",
        "SYSTEMDRIVE": "%SystemDrive%",
        "PROGRAMDATA": r"%SystemDrive%\ProgramData",
        "USERPROFILE": r"C:\Users\runner",
        "LOCALAPPDATA": r"%USERPROFILE%\AppData\Local",
    }

    env = build_agent_environment(spec, tmp_path, parent_environment=parent)

    assert env["SYSTEMDRIVE"] == "C:"
    assert env["PROGRAMDATA"] == r"C:\ProgramData"
    assert env["LOCALAPPDATA"] == r"C:\Users\runner\AppData\Local"


def test_pi_projects_explicit_reference_repository_as_read_only_path_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    reference = tmp_path / "reference-repo"
    workspace.mkdir()
    reference.mkdir()
    spec = AgentRunSpec(
        run_id="run-reference-root",
        task="Compare the implementation with the reference repository",
        model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-test"),
        capabilities=["workspace.read", "workspace.search", "workspace.edit"],
        workspace=WorkspaceSpec(root=str(workspace)),
        resource_scopes=[ResourceScope(
            capability="workspace.read",
            resource_type="repository",
            resource_id=str(reference),
            constraints={"root_id": "upstream"},
        )],
    )

    roots = agent_path_roots(spec, workspace)
    env = build_agent_environment(spec, workspace, parent_environment={})

    assert roots == [
        {"root_id": "workspace", "path": str(workspace.resolve()), "access": "read_write"},
        {"root_id": "upstream", "path": str(reference.resolve()), "access": "read_only"},
    ]
    assert json.loads(env["OMNIX_AGENT_PATH_ROOTS"]) == roots


def test_pi_ignores_nonlocal_and_nonrepository_resource_scopes(tmp_path: Path) -> None:
    unissued_reference = tmp_path / "unissued-reference"
    unissued_reference.mkdir()
    spec = AgentRunSpec(
        run_id="run-nonlocal-scopes",
        task="Inspect",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read"],
        workspace=WorkspaceSpec(root=str(tmp_path)),
        resource_scopes=[
            ResourceScope(
                capability="workspace.read",
                resource_type="repository",
                resource_id="owner/remote-repository",
            ),
            ResourceScope(
                capability="workspace.read",
                resource_type="document",
                resource_id=str(tmp_path),
            ),
            ResourceScope(
                capability="workspace.search",
                resource_type="repository",
                resource_id=str(unissued_reference),
            ),
        ],
    )

    assert agent_path_roots(spec, tmp_path) == [
        {"root_id": "workspace", "path": str(tmp_path.resolve()), "access": "read_only"},
    ]
