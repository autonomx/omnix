"""Pi RPC implementation of the generalized AgentRuntime contract."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from typing import Any

from .contracts import AgentArtifact, AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec
from .interfaces import AgentRuntime
from .isolation import launch_agent_process


class PiRuntimeError(RuntimeError):
    pass


def pi_guard_extension_path() -> Path:
    return Path(__file__).with_name("pi_guard_extension.ts").resolve()


def pi_model_provider_extension_path() -> Path:
    return Path(__file__).with_name("pi_model_provider_extension.ts").resolve()


def pi_broker_extension_path() -> Path:
    return Path(__file__).with_name("pi_broker_extension.ts").resolve()


def pi_rpc_argv(spec: AgentRunSpec, *, pi_path: str = "pi") -> list[str]:
    executable = shutil.which(pi_path) or pi_path
    model = f"{spec.model.provider_id}::{spec.model.model_id}"
    argv = [
        executable,
        "--mode",
        "rpc",
        "--no-session",
        "--name",
        spec.run_id,
        "--provider",
        "omnix",
        "--model",
        model,
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--extension",
        str(pi_guard_extension_path()),
        "--extension",
        str(pi_model_provider_extension_path()),
        "--extension",
        str(pi_broker_extension_path()),
    ]
    mapping = {
        "workspace.read": "read",
        "workspace.edit": "edit",
        "workspace.write": "write",
        "workspace.search": "grep",
        "workspace.list": "ls",
        "workspace.command": "powershell" if os.name == "nt" else "bash",
        "workspace.test": "powershell" if os.name == "nt" else "bash",
    }
    tools = sorted({tool for capability, tool in mapping.items() if capability in spec.capabilities})
    if tools:
        argv.extend(["--tools", ",".join(tools)])
    else:
        argv.append("--no-builtin-tools")
    if spec.model.reasoning_effort:
        argv.extend(["--thinking", spec.model.reasoning_effort])
    return argv


def normalize_pi_event(run_id: str, payload: dict[str, Any]) -> AgentEvent | None:
    event_type = str(payload.get("type") or "")
    if event_type == "agent_start":
        return AgentEvent(run_id=run_id, event_type="run.started", payload={"source": "pi"})
    if event_type == "agent_settled":
        return AgentEvent(run_id=run_id, event_type="run.settled", payload={"source": "pi", "raw": payload})
    if event_type in {"message_start", "message_update", "message_end", "turn_start", "turn_end"}:
        return AgentEvent(run_id=run_id, event_type="model.message", payload={"source": "pi", "raw": payload})
    if event_type == "tool_execution_start":
        return AgentEvent(
            run_id=run_id,
            event_type="tool.started",
            payload={
                "source": "pi",
                "tool_call_id": payload.get("toolCallId"),
                "tool": payload.get("toolName"),
                "args": payload.get("args") or {},
            },
        )
    if event_type == "tool_execution_update":
        return AgentEvent(run_id=run_id, event_type="tool.output", payload={"source": "pi", "raw": payload})
    if event_type == "tool_execution_end":
        return AgentEvent(
            run_id=run_id,
            event_type="tool.completed",
            payload={
                "source": "pi",
                "tool_call_id": payload.get("toolCallId"),
                "tool": payload.get("toolName"),
                "is_error": bool(payload.get("isError")),
                "result": payload.get("result"),
            },
        )
    if event_type in {"error", "agent_error"}:
        return AgentEvent(run_id=run_id, event_type="run.failed", payload={"source": "pi", "raw": payload})
    return None


class PiRpcSession:
    def __init__(
        self,
        spec: AgentRunSpec,
        *,
        pi_path: str = "pi",
        on_event: Callable[[AgentEvent], None] | None = None,
        process_factory: Callable[..., subprocess.Popen[str]] | None = None,
    ) -> None:
        if spec.workspace is None:
            raise PiRuntimeError("Pi runtime requires an issued workspace")
        self.spec = spec
        self.on_event = on_event
        self._events: deque[AgentEvent] = deque(maxlen=10_000)
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._closed = False
        cwd = Path(spec.workspace.worktree or spec.workspace.root).expanduser().resolve()
        env = {
            **os.environ,
            "OMNIX_AGENT_RUN_ID": spec.run_id,
            "OMNIX_AGENT_WORKSPACE": str(cwd),
            "OMNIX_AGENT_COMMAND_POLICY": spec.execution.command_policy,
            "OMNIX_AGENT_NETWORK_POLICY": spec.execution.network_policy,
            "OMNIX_AGENT_PROVIDER_ID": spec.model.provider_id,
            "OMNIX_AGENT_MODEL_ID": spec.model.model_id,
            "OMNIX_AGENT_MODEL_KEY": f"{spec.model.provider_id}::{spec.model.model_id}",
            "OMNIX_AGENT_MODEL_GATEWAY_URL": os.environ.get(
                "OMNIX_AGENT_MODEL_GATEWAY_URL",
                "http://127.0.0.1:8000/api/agent-model/v1",
            ),
            "OMNIX_AGENT_BROKER_URL": os.environ.get(
                "OMNIX_AGENT_BROKER_URL",
                "http://127.0.0.1:8000/api/agent-runs",
            ),
            "OMNIX_AGENT_EXTERNAL_CAPABILITIES": json.dumps(spec.external_capabilities),
            "OMNIX_AGENT_REASONING_EFFORT": spec.model.reasoning_effort or "",
        }
        argv = pi_rpc_argv(spec, pi_path=pi_path)
        if process_factory is not None:
            self.process = process_factory(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        else:
            self.process = launch_agent_process(spec, argv=argv, cwd=cwd, env=env)
        self._reader = threading.Thread(target=self._read_stdout, name=f"pi-rpc-{spec.run_id[:8]}", daemon=True)
        self._stderr = deque(maxlen=200)
        self._stderr_reader = threading.Thread(target=self._read_stderr, name=f"pi-stderr-{spec.run_id[:8]}", daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def prompt(self, message: str) -> None:
        self.send({"type": "prompt", "message": message})

    def steer(self, message: str) -> None:
        self.send({"type": "steer", "message": message})

    def abort(self) -> None:
        self.send({"type": "abort"})

    def send(self, payload: dict[str, Any]) -> None:
        if self._closed or self.process.poll() is not None or self.process.stdin is None:
            raise PiRuntimeError(self._process_error("Pi RPC process is not running"))
        self.process.stdin.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def events(self) -> list[AgentEvent]:
        return list(self._events)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def _read_stdout(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        for line in stream:
            text = line[:-1] if line.endswith("\n") else line
            if text.endswith("\r"):
                text = text[:-1]
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                self._stderr.append(f"non-json stdout: {text[:500]}")
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "response":
                self._responses.put(payload)
                continue
            event = normalize_pi_event(self.spec.run_id, payload)
            if event is not None:
                self._events.append(event)
                if self.on_event is not None:
                    self.on_event(event)

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None:
            return
        for line in stream:
            if line.strip():
                self._stderr.append(line.rstrip())

    def _process_error(self, prefix: str) -> str:
        detail = "\n".join(self._stderr)
        return f"{prefix}: {detail[-2000:]}" if detail else prefix


class PiAgentRuntime(AgentRuntime):
    """Process-local Pi runtime. Durable orchestration is layered above this class."""

    def __init__(self, *, pi_path: str = "pi", event_sink: Callable[[AgentEvent], None] | None = None) -> None:
        self.pi_path = pi_path
        self.event_sink = event_sink
        self._sessions: dict[str, PiRpcSession] = {}
        self._snapshots: dict[str, AgentRunSnapshot] = {}
        self._artifacts: dict[str, list[AgentArtifact]] = {}
        self._lock = threading.RLock()

    def start(self, spec: AgentRunSpec) -> AgentRunSnapshot:
        with self._lock:
            if spec.run_id in self._sessions:
                return self._snapshots[spec.run_id]
            snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="starting")
            self._snapshots[spec.run_id] = snapshot
            session = PiRpcSession(spec, pi_path=self.pi_path, on_event=self._on_event)
            self._sessions[spec.run_id] = session
            running = snapshot.model_copy(update={"status": "running", "revision": snapshot.revision + 1})
            self._snapshots[spec.run_id] = running
            session.prompt(self._initial_prompt(spec))
            return running

    def command(self, command: AgentRunCommand) -> AgentRunSnapshot:
        with self._lock:
            session = self._sessions.get(command.run_id)
            snapshot = self._snapshots.get(command.run_id)
            if session is None or snapshot is None:
                raise KeyError(command.run_id)
            if command.command_type == "steer":
                session.steer(str(command.payload.get("message") or ""))
            elif command.command_type == "pause":
                session.abort()
                snapshot = snapshot.model_copy(update={"status": "paused", "desired_state": "paused", "revision": snapshot.revision + 1})
            elif command.command_type == "resume":
                snapshot = snapshot.model_copy(update={"status": "running", "desired_state": "running", "revision": snapshot.revision + 1})
                session.prompt(str(command.payload.get("message") or "Resume the task from the current state and re-check your work."))
            elif command.command_type == "cancel":
                session.abort()
                session.close()
                snapshot = snapshot.model_copy(update={"status": "cancelled", "desired_state": "cancelled", "revision": snapshot.revision + 1})
            elif command.command_type in {"approve", "reject"}:
                snapshot = snapshot.model_copy(
                    update={"status": "running", "desired_state": "running", "revision": snapshot.revision + 1}
                )
                session.prompt(f"Omnix approval decision: {command.command_type}. {command.payload}")
            self._snapshots[command.run_id] = snapshot
            return snapshot

    def close_run(self, run_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(run_id, None)
            self._snapshots.pop(run_id, None)
        if session is not None:
            session.close()

    def active_run_ids(self) -> set[str]:
        with self._lock:
            return set(self._sessions)

    def get_status(self, run_id: str) -> AgentRunSnapshot | None:
        return self._snapshots.get(run_id)

    def stream_events(self, run_id: str, *, after_sequence: int = 0) -> Iterable[AgentEvent]:
        session = self._sessions.get(run_id)
        if session is None:
            return []
        rows = session.events()
        return rows[max(0, after_sequence):]

    def get_artifacts(self, run_id: str) -> list[AgentArtifact]:
        return list(self._artifacts.get(run_id, []))

    def _on_event(self, event: AgentEvent) -> None:
        with self._lock:
            snapshot = self._snapshots.get(event.run_id)
            if snapshot is not None:
                if event.event_type == "run.started":
                    self._snapshots[event.run_id] = snapshot.model_copy(
                        update={"status": "running", "desired_state": "running", "revision": snapshot.revision + 1}
                    )
                elif event.event_type == "run.failed":
                    self._snapshots[event.run_id] = snapshot.model_copy(update={"status": "failed", "revision": snapshot.revision + 1})
        if self.event_sink is not None:
            self.event_sink(event)

    @staticmethod
    def _initial_prompt(spec: AgentRunSpec) -> str:
        criteria = "\n".join(f"- {item.description}" for item in spec.success_criteria)
        authority = ", ".join(spec.capabilities)
        return (
            f"Task: {spec.task}\n"
            f"Objective: {spec.objective or spec.task}\n"
            f"Issued capabilities: {authority or 'none'}\n"
            f"Success criteria:\n{criteria or '- Complete the requested task and report evidence.'}\n"
            "Stay inside the issued workspace. Do not publish, push, merge, send messages, control devices, "
            "or access external systems unless Omnix exposes an explicit governed capability."
        )
