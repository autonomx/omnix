from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.repo_adapter import run_repository_tool_request
from app.chat import generation_jobs


ROOT = Path(__file__).resolve().parents[3]


def test_allow_automatic_does_not_widen_issued_command_capability() -> None:
    source = (ROOT / "src/app/agent_runtime/pi_guard_extension.ts").read_text(encoding="utf-8")
    capability_gate = '!commandAllowedByIssuedCapability && !localCapabilities.has("workspace.command")'
    approval_gate = 'approvalPolicy !== "allow_automatic"'
    assert capability_gate in source
    assert source.index(capability_gate) < source.index(approval_gate, source.index(capability_gate))


def test_repository_evidence_fails_closed_without_real_adapter(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_GITHUB_REAL_ADAPTER", raising=False)
    result = run_repository_tool_request(
        AssistantToolRequest(
            tool_id="github",
            action_id="github.inspect_ci",
            input={"repository": "does-not-exist/example", "ref": "deadbeef"},
        )
    )
    assert result.error == "github_runtime_adapter_unavailable"
    assert result.output == {}


def test_chat_dispatcher_worker_survives_unhandled_job_failure(monkeypatch) -> None:
    calls: list[str] = []
    second_completed = Event()

    def fake_run_chat_generation_job(**kwargs) -> None:
        job_id = kwargs["job"].id
        calls.append(job_id)
        if job_id == "job-1":
            raise RuntimeError("database failed while recording failure")
        second_completed.set()

    monkeypatch.setattr(generation_jobs, "_run_chat_generation_job", fake_run_chat_generation_job)
    dispatcher = generation_jobs._ChatGenerationDispatcher(worker_count=1)

    def work(job_id: str):
        return generation_jobs._ChatGenerationWork(
            chat_store=object(),
            job_store=object(),
            job=SimpleNamespace(id=job_id, input_payload={"session_id": "chat-1"}),
            request=object(),
            context_builder=None,
            completion_hook=None,
        )

    dispatcher.submit(work("job-1"))
    dispatcher.submit(work("job-2"))

    assert second_completed.wait(timeout=2)
    assert calls == ["job-1", "job-2"]


def test_task_graph_terminal_child_reconciles_from_waiting_for_approval() -> None:
    source = (ROOT / "src/app/agent_runtime/task_graph_runtime.py").read_text(encoding="utf-8")
    terminal_region = source.split(
        'if child.status not in {"completed", "failed", "cancelled"}:', 1
    )[1].split("def _claim_node", 1)[0]
    assert 'terminal_expected_statuses = ("running", "waiting_for_approval")' in terminal_region
    assert 'expected_statuses=("running",),' not in terminal_region
