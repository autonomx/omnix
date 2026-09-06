from __future__ import annotations

from collections import deque
from io import StringIO
from pathlib import Path
import threading

from app.agent_runtime.contracts import AgentRunCommand, AgentRunSnapshot, AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.pi_runtime import PiAgentRuntime, PiRpcSession, normalize_pi_event, pi_rpc_argv
from app.agent_runtime.pi_runtime_core import _assistant_text_delta


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


def test_pi_rpc_maps_disabled_reasoning_to_thinking_off(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-pi-no-thinking",
        task="Edit the requested file",
        model=ModelRef(provider_id="openai", model_id="gpt-test", reasoning_effort="none"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.read"],
    )

    argv = pi_rpc_argv(spec, pi_path="pi")

    assert argv[argv.index("--thinking") + 1] == "off"


def test_pi_events_are_normalized_without_leaking_runtime_contracts() -> None:
    event = normalize_pi_event(
        "run-1",
        {"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "read", "args": {"path": "a.py"}},
    )
    assert event is not None
    assert event.event_type == "tool.started"
    assert event.payload["tool"] == "read"


def test_pi_message_end_exposes_only_normal_assistant_text() -> None:
    event = normalize_pi_event(
        "run-activity",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "private reasoning"},
                    {"type": "text", "text": "I found the failing validation and I am correcting it."},
                ],
            },
        },
    )

    assert event is not None
    assert event.event_type == "model.message"
    assert event.payload["text"] == "I found the failing validation and I am correcting it."
    assert "private reasoning" not in str(event.payload)


def test_pi_message_end_preserves_final_summary_markdown() -> None:
    summary = (
        "Implemented the requested fix.\n\n"
        "- Updated `runtime.ts`.\n"
        "- Added regression coverage.\n\n"
        "Verification:\n\n- `npm test` passed."
    )

    event = normalize_pi_event(
        "run-summary",
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": summary}],
            },
        },
    )

    assert event is not None
    assert event.payload["text"] == summary


def test_pi_turn_end_preserves_terminal_assistant_text_as_a_fallback() -> None:
    event = normalize_pi_event(
        "run-review",
        {
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '{"verdict":"approve"}'}],
            },
        },
    )

    assert event is not None
    assert event.payload["phase"] == "turn_end"
    assert event.payload["text"] == '{"verdict":"approve"}'


def test_pi_extracts_only_explicit_assistant_text_deltas() -> None:
    assert _assistant_text_delta(
        {"assistantMessageEvent": {"type": "text_delta", "delta": '{"verdict":"approve"}'}}
    ) == '{"verdict":"approve"}'
    assert _assistant_text_delta(
        {"assistantMessageEvent": {"type": "thinking_delta", "delta": "private reasoning"}}
    ) == ""


def test_initial_prompt_requires_progress_updates_and_validation_recovery() -> None:
    spec = AgentRunSpec(
        run_id="run-progress",
        task="Fix the UI defect",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
    )

    prompt = PiAgentRuntime._initial_prompt(spec)

    assert "short normal-assistant progress updates" in prompt
    assert "do not reveal private chain-of-thought" in prompt
    assert "do not stop merely because a test, lint, or typecheck command failed" in prompt
    assert "do not chain commands with semicolons, pipes, redirection" in prompt
    assert "an unrelated passing test is not completion evidence" in prompt
    assert "Do not ask the user to provide a missing request" in prompt
    assert "do not wait for a reply" in prompt
    assert "Final task anchor: begin work on the Task and Objective above now" in prompt
    assert "never respond with a generic message that no task" in prompt
    assert "finish with one concise normal-assistant Markdown summary" in prompt


def test_initial_prompt_can_receive_ephemeral_chat_reference_context() -> None:
    spec = AgentRunSpec(
        run_id="run-initial-context",
        task="fix it",
        objective="fix it",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.read", "workspace.edit"],
    )
    context = "User: the Omnix light-mode Agent card text is unreadable"

    prompt = PiAgentRuntime._initial_prompt(spec, reference_context=context)

    assert "Task: fix it" in prompt
    assert "Canonical Chat reference context JSON follows." in prompt
    assert context in prompt
    assert context not in spec.model_dump_json()


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
    assert "Latest user steering (authoritative):\nFocus only on profile selection." in received[0]
    assert "Canonical Chat reference context JSON follows." not in received[0]


def test_runtime_steering_includes_chat_reference_context_without_making_it_authority() -> None:
    received: list[str] = []
    session = type(
        "Session",
        (),
        {"steer": lambda _self, message, **_kwargs: received.append(message)},
    )()
    spec = AgentRunSpec(
        run_id="run-steer-context",
        task="Inspect the current issue",
        objective="Inspect the current issue",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: session}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    }

    command = AgentRunCommand(
        run_id=spec.run_id,
        command_type="steer",
        payload={
            "message": "fix it",
            "effective_objective": "fix it",
        },
    )
    runtime.command_with_context(
        command,
        reference_context=(
            "User: the Omnix light-mode Agent card text is unreadable"
        ),
    )
    assert "reference_context" not in command.payload

    assert len(received) == 1
    assert "Canonical Chat reference context JSON follows." in received[0]
    assert "light-mode Agent card text is unreadable" in received[0]
    assert "Latest user steering (authoritative):\nfix it" in received[0]


def test_runtime_approval_prompt_carries_exact_command_for_retry() -> None:
    received: list[str] = []
    actions: list[str] = []
    session = type(
        "Session",
        (),
        {
            "abort": lambda _self: actions.append("abort"),
            "prompt": lambda _self, message, **_kwargs: (actions.append("prompt"), received.append(message)),
        },
    )()
    spec = AgentRunSpec(
        run_id="run-command-approval",
        task="Run a validation command",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: session}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="waiting_for_approval")
    }

    runtime.command_with_context(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="approve",
            payload={
                "approval_id": "command-1",
                "approval_request": {"command": "python -m pip --version"},
            },
        )
    )

    assert received
    assert actions == ["abort", "prompt"]
    assert "Task: Run a validation command" in received[0]
    assert "Objective: Run a validation command" in received[0]
    assert "python -m pip --version" in received[0]
    assert "retry the exact requested workspace command" in received[0]


def test_runtime_resume_aborts_the_interrupted_turn_first() -> None:
    actions: list[str] = []
    received: list[str] = []
    session = type(
        "Session",
        (),
        {
            "abort": lambda _self: actions.append("abort"),
            "prompt": lambda _self, message, **_kwargs: (actions.append("prompt"), received.append(message)),
        },
    )()
    spec = AgentRunSpec(
        run_id="run-resume",
        task="Continue the task",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    runtime = object.__new__(PiAgentRuntime)
    runtime._lock = threading.RLock()
    runtime._sessions = {spec.run_id: session}
    runtime._snapshots = {
        spec.run_id: AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    }

    runtime.command_with_context(
        AgentRunCommand(
            run_id=spec.run_id,
            command_type="resume",
            payload={"message": "resume cleanly"},
        )
    )

    assert actions == ["abort", "prompt"]
    assert "Task: Continue the task" in received[0]
    assert "Objective: Continue the task" in received[0]
    assert "Authoritative follow-up instruction:\nresume cleanly" in received[0]
    assert "do not ask the user to restate it" in received[0]


def test_pi_approval_follow_up_aborts_the_interrupted_turn_first() -> None:
    actions: list[tuple[str, str]] = []
    session = object.__new__(PiRpcSession)
    session.abort = lambda: actions.append(("abort", ""))
    session.prompt = lambda message, **_kwargs: actions.append(("prompt", message))

    session.prompt_after_interrupted_turn("retry the approved command")

    assert actions == [("abort", ""), ("prompt", "retry the approved command")]


def test_pi_quality_resume_does_not_abort_an_already_settled_turn() -> None:
    actions: list[tuple[str, str]] = []
    session = object.__new__(PiRpcSession)
    session._turn_active = False
    session.abort = lambda: actions.append(("abort", ""))
    session.prompt = lambda message, **_kwargs: actions.append(("prompt", message))

    session.prompt_after_interrupted_turn("continue with self-review")

    assert actions == [("prompt", "continue with self-review")]


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


def test_pi_prompt_rearms_terminal_monitor_for_follow_up_turn() -> None:
    sent = []
    session = object.__new__(PiRpcSession)
    session._terminal_seen = True
    session.send = lambda payload: sent.append(payload)

    session.prompt("Retry the failed validation")

    assert session._terminal_seen is False
    assert sent == [{"type": "prompt", "message": "Retry the failed validation"}]


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


def test_pi_stdout_reader_survives_event_sink_failure() -> None:
    session = object.__new__(PiRpcSession)
    session.spec = AgentRunSpec(
        run_id="run-sink-failure",
        task="inspect",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    session.process = type("Process", (), {"stdout": StringIO('{"type":"agent_start"}\n')})()
    session._task_revision_id = None
    session._tool_revision_ids = {}
    session._events = deque()
    session._stderr = deque(maxlen=10)
    session.on_event = lambda _event: (_ for _ in ()).throw(RuntimeError("observer failed"))

    session._read_stdout()

    assert session._events[0].event_type == "run.started"
    assert "event sink failed" in session._stderr[-1]


def test_pi_stdout_reader_recovers_terminal_text_from_deltas() -> None:
    session = object.__new__(PiRpcSession)
    session.spec = AgentRunSpec(
        run_id="run-delta-recovery",
        task="review",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    lines = [
        '{"type":"turn_start"}',
        '{"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"{\\"verdict\\":\\"approve\\"}"}}',
        '{"type":"agent_settled"}',
    ]
    session.process = type("Process", (), {"stdout": StringIO("\n".join(lines) + "\n")})()
    session._task_revision_id = "revision-1"
    session._tool_revision_ids = {}
    session._events = deque()
    session._stderr = deque(maxlen=10)
    session._assistant_text_parts = []
    session._terminal_assistant_text_emitted = False
    session._turn_active = False
    session._terminal_seen = False
    session.on_event = None

    session._read_stdout()

    recovered = next(
        event
        for event in session._events
        if event.event_type == "model.message" and event.payload.get("recovered_from_text_deltas")
    )
    assert recovered.payload["text"] == '{"verdict":"approve"}'
    assert recovered.payload["task_revision_id"] == "revision-1"
    assert session._events[-1].event_type == "run.settled"



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



def test_pi_prompt_carries_image_payload() -> None:
    sent = []
    session = object.__new__(PiRpcSession)
    session._terminal_seen = True
    session.send = lambda payload: sent.append(payload)
    images = [{"type": "image", "data": "YWJj", "mimeType": "image/png"}]

    session.prompt("Inspect the screenshot", images=images)

    assert session._terminal_seen is False
    assert sent == [{
        "type": "prompt",
        "message": "Inspect the screenshot",
        "images": images,
    }]


def test_pi_steer_carries_image_payload_and_revision() -> None:
    sent = []
    session = object.__new__(PiRpcSession)
    session._terminal_seen = True
    session._task_revision_id = None
    session.send = lambda payload: sent.append(payload)
    images = [{"type": "image", "data": "YWJj", "mimeType": "image/webp"}]

    session.steer("Use this updated screenshot", task_revision_id="rev-2", images=images)

    assert session._terminal_seen is False
    assert session._task_revision_id == "rev-2"
    assert sent == [{
        "type": "steer",
        "message": "Use this updated screenshot",
        "images": images,
    }]
