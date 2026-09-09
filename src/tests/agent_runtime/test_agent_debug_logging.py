from __future__ import annotations

from io import StringIO
import json
import logging
from pathlib import Path
import threading

import pytest

from app.agent_runtime.contracts import AgentEvent, AgentRunSpec, ModelRef, WorkspaceSpec
from app.agent_runtime.debug_logging import (
    _reset_agent_debug_logging_for_tests,
    configure_agent_debug_logging,
    log_agent_activity,
)
from app.agent_runtime.pi_runtime import PiRpcSession
from app.agent_runtime.pi_runtime_core import _rpc_payload_for_log
from app.agent_runtime.repository import PostgresAgentRunRepository


@pytest.fixture
def agent_log_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OMNIX_AGENT_DEBUG_LOGS", "1")
    monkeypatch.setenv("OMNIX_AGENT_LOG_DIR", str(tmp_path / "agent-logs"))
    monkeypatch.setenv("OMNIX_AGENT_LOG_MAX_FIELD_CHARS", "256")
    _reset_agent_debug_logging_for_tests()
    configure_agent_debug_logging(force=True)
    yield tmp_path / "agent-logs"
    _reset_agent_debug_logging_for_tests()


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_agent_activity_is_written_to_daily_and_per_run_logs(agent_log_dir: Path) -> None:
    log_agent_activity(
        "test.activity",
        run_id="run/log-1",
        fields={
            "normal": "kept",
            "authorization": "Bearer should-not-appear",
            "thinking": "private reasoning should not appear",
            "nested": {"api_key": "also secret"},
        },
    )

    activity_files = list(agent_log_dir.glob("activity-*.jsonl"))
    run_file = agent_log_dir / "run-run_log-1.jsonl"
    assert activity_files
    assert run_file.exists()
    records = _records(run_file)
    record = next(item for item in records if item["event"] == "test.activity")
    serialized = json.dumps(record, sort_keys=True)
    assert record["run_id"] == "run/log-1"
    assert record["fields"]["normal"] == "kept"
    assert "Bearer should-not-appear" not in serialized
    assert "private reasoning should not appear" not in serialized
    assert "also secret" not in serialized


def test_agent_logger_captures_python_runtime_records_without_secrets(agent_log_dir: Path) -> None:
    logger = logging.getLogger("app.agent_runtime.test")
    logger.error(
        "runtime observer failed",
        extra={"run_id": "run-python", "token": "secret-token"},
    )

    run_records = _records(agent_log_dir / "run-run-python.jsonl")
    record = next(item for item in run_records if item["event"] == "python.log")
    serialized = json.dumps(record, sort_keys=True)
    assert record["level"] == "error"
    assert record["fields"]["message"] == "runtime observer failed"
    assert "secret-token" not in serialized


def test_rpc_log_transform_omits_thinking_delta_content() -> None:
    payload = _rpc_payload_for_log(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": "private chain of thought",
            },
        }
    )

    assert "private chain of thought" not in json.dumps(payload)
    assert payload["assistantMessageEvent"]["content"] == "[omitted-private-reasoning]"


def test_durable_event_append_is_mirrored_after_success(agent_log_dir: Path) -> None:
    event = AgentEvent(run_id="run-durable", event_type="tool.completed", payload={"ok": True})
    stored = event.model_copy(update={"sequence": 7})
    repository = object.__new__(PostgresAgentRunRepository)
    repository._append_event = lambda _event: stored

    assert repository.append_event(event) == stored
    records = _records(agent_log_dir / "run-run-durable.jsonl")
    persisted = next(item for item in records if item["event"] == "durable.event.persisted")
    assert persisted["fields"]["sequence"] == 7
    assert persisted["fields"]["event_type"] == "tool.completed"


def test_durable_event_append_failure_has_traceback(agent_log_dir: Path) -> None:
    event = AgentEvent(run_id="run-durable-fail", event_type="run.started")
    repository = object.__new__(PostgresAgentRunRepository)

    def fail(_event: AgentEvent) -> AgentEvent:
        raise RuntimeError("database unavailable")

    repository._append_event = fail
    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.append_event(event)

    records = _records(agent_log_dir / "run-run-durable-fail.jsonl")
    failed = next(item for item in records if item["event"] == "durable.event.append_failed")
    assert failed["error"]["type"] == "RuntimeError"
    assert "database unavailable" in failed["error"]["message"]
    assert "Traceback" in failed["error"]["traceback"]


def test_pi_process_and_rpc_activity_is_traceable(agent_log_dir: Path, tmp_path: Path) -> None:
    class OutputStream:
        def __init__(self, process: FakeProcess, lines: list[str]) -> None:
            self.process = process
            self.lines = lines

        def __iter__(self):
            yield from self.lines
            self.process.output_done.set()

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 731
            self.returncode: int | None = None
            self.output_done = threading.Event()
            self.stdin = StringIO()
            self.stdout = OutputStream(
                self,
                [
                    json.dumps({"type": "agent_start"}),
                    json.dumps(
                        {
                            "type": "tool_execution_start",
                            "toolCallId": "call-1",
                            "toolName": "read",
                            "args": {"path": "src/app.py"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_execution_end",
                            "toolCallId": "call-1",
                            "toolName": "read",
                            "isError": False,
                            "result": "content",
                        }
                    ),
                    json.dumps({"type": "agent_settled"}),
                ],
            )
            self.stderr = StringIO("diagnostic warning\n")

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.output_done.wait(timeout=timeout)
            self.returncode = 0
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

    spec = AgentRunSpec(
        run_id="run-pi-log",
        task="Inspect the failing validation",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.read"],
    )
    process = FakeProcess()
    session = PiRpcSession(
        spec,
        process_factory=lambda *_args, **_kwargs: process,
    )
    session.send({"type": "prompt", "message": "Inspect the failing validation"})
    session._reader.join(timeout=2)
    session._stderr_reader.join(timeout=2)
    session._monitor.join(timeout=2)
    session.close()

    records = _records(agent_log_dir / "run-run-pi-log.jsonl")
    events = {item["event"] for item in records}
    assert "pi.process.started" in events
    assert "pi.rpc.outbound" in events
    assert "pi.rpc.stdout.received" in events
    assert "pi.event.normalized" in events
    assert "pi.process.stderr" in events
    normalized = [item for item in records if item["event"] == "pi.event.normalized"]
    assert any(item["fields"]["event_type"] == "tool.completed" for item in normalized)
