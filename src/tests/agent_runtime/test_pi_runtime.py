from __future__ import annotations

from io import StringIO
from pathlib import Path
import threading

from app.agent_runtime.contracts import AgentRunCommand, AgentRunSnapshot, AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.pi_runtime import PiAgentRuntime, PiRpcSession, normalize_pi_event, pi_rpc_argv


def test_pi_rpc_command_is_headless_and_guarded(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-pi",
        task="Inspect",
        model=ModelRef(provider_id="openai", model_id="gpt-test", reasoning_effort="medium"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.read"],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert argv[:3] == ["pi", "--mode", "rpc"]
    assert "--extension" in argv
    assert "--tools" in argv
    assert "--no-context-files" in argv
    assert "--thinking" in argv


def test_pi_events_are_normalized_without_leaking_runtime_contracts() -> None:
    event = normalize_pi_event(
        "run-1",
        {"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "read", "args": {"path": "a.py"}},
    )
    assert event is not None
    assert event.event_type == "tool.started"
    assert event.payload["tool"] == "read"


def test_pi_rpc_projects_git_read_capabilities_to_guarded_shell(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-git-read",
        task="Inspect git state",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.git_status", "workspace.git_diff"],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert "--tools" in argv
    tools = argv[argv.index("--tools") + 1].split(",")
    assert ("powershell" if __import__("os").name == "nt" else "bash") in tools


def test_pi_rpc_without_local_capabilities_disables_builtin_tools(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-no-tools",
        task="Reason only",
        model=ModelRef(provider_id="lmstudio", model_id="qwen"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=[],
    )
    argv = pi_rpc_argv(spec, pi_path="pi")
    assert "--no-builtin-tools" in argv


def test_initial_prompt_names_governed_external_capabilities() -> None:
    spec = AgentRunSpec(
        run_id="run-research",
        task="Research the latest release",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        external_capabilities=["research.web_search"],
    )

    prompt = PiAgentRuntime._initial_prompt(spec)

    assert "Issued local capabilities: none" in prompt
    assert "Issued governed external capabilities: research.web_search" in prompt
    assert "Later user steering is authoritative" in prompt


def test_runtime_marks_steering_as_scope_superseding() -> None:
    received: list[str] = []
    session = type(
        "Session",
        (),
        {"steer": lambda _self, message, **_kwargs: received.append(message)},
    )()
    spec = AgentRunSpec(
        run_id="run-steer",
        task="Review routing",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: session}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    }

    runtime.command(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="steer",
            payload={"message": "Focus only on profile selection."},
        )
    )

    assert len(received) == 1
    assert "supersedes any conflicting earlier scope" in received[0]
    assert received[0].endswith("Focus only on profile selection.")


class _IdleProcess:
    def __init__(self, *, returncode: int | None = None, stderr: str = "") -> None:
        self._returncode = returncode
        self._stopped = threading.Event()
        if returncode is not None:
            self._stopped.set()
        self.stdin = StringIO()
        self.stdout = StringIO()
        self.stderr = StringIO(stderr)

    def poll(self):
        return self._returncode

    def wait(self, timeout=None):
        self._stopped.wait(timeout)
        return self._returncode

    def terminate(self) -> None:
        self._returncode = 0
        self._stopped.set()

    def kill(self) -> None:
        self._returncode = -9
        self._stopped.set()


def test_pi_session_without_workspace_uses_and_cleans_ephemeral_cwd(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def factory(argv, **kwargs):
        del argv
        captured["cwd"] = kwargs["cwd"]
        return _IdleProcess()

    spec = AgentRunSpec(
        run_id="run-research",
        task="research",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=None,
    )
    session = PiRpcSession(spec, pi_path="pi", process_factory=factory)
    cwd = Path(captured["cwd"])

    assert cwd.exists()
    assert cwd != tmp_path
    session.close()
    assert not cwd.exists()


def test_pi_session_emits_failure_when_process_exits_without_terminal_event() -> None:
    received = []
    done = threading.Event()

    def on_event(event):
        received.append(event)
        done.set()

    def factory(argv, **kwargs):
        del argv, kwargs
        return _IdleProcess(returncode=1, stderr="pi executable failed\n")

    spec = AgentRunSpec(
        run_id="run-failed-process",
        task="research",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=None,
    )
    session = PiRpcSession(spec, pi_path="pi", on_event=on_event, process_factory=factory)

    assert done.wait(timeout=1)
    assert any(event.event_type == "run.failed" for event in received)
    failure = next(event for event in received if event.event_type == "run.failed")
    assert "exit code 1" in str(failure.payload["error"])
    session.close()



def test_tool_events_keep_revision_that_authorized_the_tool_call() -> None:
    from app.agent_runtime.pi_runtime import normalize_pi_event

    started = normalize_pi_event(
        "run-1",
        {
            "type": "tool_execution_start",
            "toolCallId": "tool-1",
            "toolName": "bash",
            "args": {"command": "pytest"},
        },
        task_revision_id="rev-old",
    )
    completed = normalize_pi_event(
        "run-1",
        {
            "type": "tool_execution_end",
            "toolCallId": "tool-1",
            "toolName": "bash",
            "isError": False,
            "result": {"exitCode": 0},
        },
        task_revision_id="rev-old",
    )
    assert started is not None and started.payload["task_revision_id"] == "rev-old"
    assert completed is not None and completed.payload["task_revision_id"] == "rev-old"
