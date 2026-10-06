"""Agent sandbox by default (WP-4.7): who runs sandboxed, the override, the container."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.agent_runtime import isolation
from app.platform.agent_runtime.api import StartAgentRunRequest
from app.platform.agent_runtime.contracts import AgentRunSpec, ModelRef, WorkspaceSpec
from app.platform.agent_runtime.isolation import (
    RELAY_CONTAINER,
    SANDBOX_NETWORK,
    AgentIsolationError,
    DockerStrongIsolation,
    IsolationPlan,
    LocalSupervisedIsolation,
    plan_isolation,
)
from app.platform.agent_runtime.local_workspace import LocalWorkspaceSelectionError, validate_local_workspace_root
from app.platform.agent_runtime.pi_runtime import PiRpcSession
from app.platform.agent_runtime.pi_runtime_core import build_agent_environment
from tests.agent_runtime.test_pi_runtime import _IdleProcess


def _spec(tmp_path: Path, *, capabilities=("workspace.read",), policy: str = "supervised_worktree", run_id: str = "run-sandbox"):
    return AgentRunSpec(
        run_id=run_id,
        task="inspect",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(tmp_path), isolation_policy=policy),
        capabilities=list(capabilities),
    )


@pytest.fixture
def docker_ready(monkeypatch):
    monkeypatch.setattr(DockerStrongIsolation, "validate", lambda self: None)


@pytest.fixture
def docker_missing(monkeypatch):
    def refuse(self):
        raise AgentIsolationError("the agent sandbox needs Docker, which is not running")

    monkeypatch.setattr(DockerStrongIsolation, "validate", refuse)


def test_read_only_runs_may_run_supervised(tmp_path, docker_missing) -> None:
    plan = plan_isolation(_spec(tmp_path))
    assert isinstance(plan.isolation, LocalSupervisedIsolation)
    assert plan.sandboxed is False and plan.unsandboxed_reason is None


def test_review_snapshots_stay_supervised(tmp_path, docker_missing) -> None:
    plan = plan_isolation(_spec(tmp_path, policy="immutable_review_snapshot"))
    assert plan.sandboxed is False


@pytest.mark.parametrize("capability", ["workspace.edit", "workspace.write", "workspace.command", "workspace.test"])
def test_a_mutating_run_is_sandboxed_even_when_it_asked_for_less(tmp_path, docker_ready, capability) -> None:
    plan = plan_isolation(_spec(tmp_path, capabilities=("workspace.read", capability)))
    assert isinstance(plan.isolation, DockerStrongIsolation)
    assert plan.sandboxed is True


def test_a_mutating_run_without_docker_fails_closed(tmp_path, docker_missing, monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_ALLOW_UNSANDBOXED", raising=False)
    with pytest.raises(AgentIsolationError, match="OMNIX_AGENT_ALLOW_UNSANDBOXED"):
        plan_isolation(_spec(tmp_path, capabilities=("workspace.edit",)))


def test_the_override_runs_it_unsandboxed_and_says_why(tmp_path, docker_missing, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_ALLOW_UNSANDBOXED", "true")
    plan = plan_isolation(_spec(tmp_path, capabilities=("workspace.command",)))
    assert plan.sandboxed is False
    assert "not running" in (plan.unsandboxed_reason or "")


def test_unattended_runs_never_take_the_override(tmp_path, docker_missing, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_ALLOW_UNSANDBOXED", "true")
    with pytest.raises(AgentIsolationError):
        plan_isolation(_spec(tmp_path, policy="unattended"))


def test_the_sandbox_container_is_locked_down(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_DOCKER_NETWORK", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_CONTAINER_BROKER_URL", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_CONTAINER_MODEL_GATEWAY_URL", raising=False)
    sandbox = DockerStrongIsolation(image="omnix-agent-sandbox:test")
    sandbox.docker = "docker"
    env = {
        "OMNIX_AGENT_BROKER_URL": "http://127.0.0.1:8000/api/agent-runs",
        "OMNIX_AGENT_MODEL_GATEWAY_URL": "http://127.0.0.1:8000/api/agent-model/v1",
        "HOME": "C:/Users/someone",
        "OMNIX_AGENT_RUN_TOKEN": "token",
    }
    command = sandbox.build_command(
        _spec(tmp_path, capabilities=("workspace.command",)),
        argv=["pi", "--mode", "rpc", "--tools", "read,powershell"], cwd=tmp_path, env=env,
    )
    assert command[command.index("--network") + 1] == SANDBOX_NETWORK
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges:true"
    assert "--read-only" in command
    envs = [command[i + 1] for i, item in enumerate(command) if item == "--env"]
    assert "HOME=/tmp/home" in envs and "HOME=C:/Users/someone" not in envs
    assert "OMNIX_AGENT_SANDBOXED=1" in envs
    assert f"OMNIX_AGENT_BROKER_URL=http://{RELAY_CONTAINER}:8000/api/agent-runs" in envs
    assert f"OMNIX_AGENT_MODEL_GATEWAY_URL=http://{RELAY_CONTAINER}:8000/api/agent-model/v1" in envs
    assert "OMNIX_AGENT_RUN_TOKEN" in envs  # by name only: the value stays out of argv
    assert command[command.index("--tools") + 1] == "read,bash"


def test_an_operator_network_replaces_the_managed_one(tmp_path) -> None:
    sandbox = DockerStrongIsolation(image="omnix-agent-sandbox:test", network="operator-net")
    sandbox.docker = "docker"
    command = sandbox.build_command(_spec(tmp_path), argv=["pi"], cwd=tmp_path,
                                    env={"OMNIX_AGENT_BROKER_URL": "http://10.0.0.5:8000/api/agent-runs"})
    assert command[command.index("--network") + 1] == "operator-net"
    assert "OMNIX_AGENT_BROKER_URL=http://10.0.0.5:8000/api/agent-runs" in command


def test_the_agent_never_gets_the_user_home(tmp_path) -> None:
    spec = _spec(tmp_path)
    parent = {"PATH": "x", "HOME": "/home/user", "USERPROFILE": "C:/Users/user"}
    env = build_agent_environment(spec, tmp_path, parent_environment=parent, home=str(tmp_path / "home"))
    assert env["HOME"] == str(tmp_path / "home")
    assert env.get("USERPROFILE") in {None, str(tmp_path / "home")}
    assert "OMNIX_AGENT_SANDBOXED" not in env
    sandboxed = build_agent_environment(spec, tmp_path, parent_environment=parent, sandboxed=True)
    assert sandboxed["OMNIX_AGENT_SANDBOXED"] == "1"


def test_an_unsandboxed_run_is_audited_and_announced(tmp_path, monkeypatch) -> None:
    recorded = []
    monkeypatch.setattr("app.security.audit.record", lambda action, **kw: recorded.append((action, kw)))
    events = []

    class _Launcher(LocalSupervisedIsolation):
        def launch(self, spec, *, argv, cwd, env):
            assert env["HOME"] != str(Path.home())
            assert "OMNIX_AGENT_SANDBOXED" not in env
            return _IdleProcess()

    plan = IsolationPlan(_Launcher(), sandboxed=False, unsandboxed_reason="Docker is not running")
    session = PiRpcSession(
        _spec(tmp_path, capabilities=("workspace.command",)), pi_path="pi", on_event=events.append,
        isolation_planner=lambda spec: plan, run_slots_factory=lambda: None,
    )
    try:
        assert [event.event_type for event in events] == ["run.unsandboxed"]
        assert events[0].payload["commands_need_approval"] is True
        assert recorded[0][0] == "agent.run.unsandboxed"
        assert recorded[0][1]["target_id"] == "run-sandbox"
    finally:
        session.close()


def test_the_session_holds_a_run_slot_until_it_closes(tmp_path) -> None:
    released = []

    class _Slot:
        def release(self):
            released.append(True)

    class _Slots:
        def acquire(self, run_id):
            assert run_id == "run-sandbox"
            return _Slot()

    plan = IsolationPlan(type("L", (LocalSupervisedIsolation,), {"launch": lambda self, spec, **kw: _IdleProcess()})(),
                         sandboxed=False)
    session = PiRpcSession(_spec(tmp_path), pi_path="pi", isolation_planner=lambda spec: plan, run_slots_factory=_Slots)
    session.close()
    assert released == [True]


def test_a_coding_request_defaults_to_the_sandbox_and_cannot_lower_it() -> None:
    request = StartAgentRunRequest(task="fix", provider_id="p", model_id="m", profile="coding")
    assert request.isolation_policy == "docker_strong"
    with pytest.raises(ValueError, match="only raise"):
        StartAgentRunRequest(task="fix", provider_id="p", model_id="m", profile="coding",
                             isolation_policy="supervised_worktree")
    research = StartAgentRunRequest(task="look", provider_id="p", model_id="m", profile="research")
    assert research.isolation_policy == "supervised_worktree"


def test_a_local_folder_outside_the_allow_list_is_refused(tmp_path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    elsewhere = tmp_path / "elsewhere"
    allowed.mkdir()
    elsewhere.mkdir()
    monkeypatch.setenv("OMNIX_AGENT_WORKSPACE_ROOTS", str(allowed))
    assert validate_local_workspace_root(str(allowed)) == str(allowed.resolve())
    with pytest.raises(LocalWorkspaceSelectionError, match="OMNIX_AGENT_WORKSPACE_ROOTS"):
        validate_local_workspace_root(str(elsewhere))


def test_relay_routes_cover_each_gateway_port(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_SANDBOX_GATEWAY_HOST", raising=False)
    routes = isolation._relay_routes(["http://127.0.0.1:8000/a", "http://127.0.0.1:8000/b", "http://127.0.0.1:8101/c"])
    assert routes == [(8000, "host.docker.internal:8000"), (8101, "host.docker.internal:8101")]
