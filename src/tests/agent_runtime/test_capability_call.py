"""A broker call settles its execution and its evidence query together, and parks for approval in one step."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.platform.agent_runtime.capability_call import CapabilityCall

RUNTIME = Path(__file__).parents[2] / "app" / "platform" / "agent_runtime"


class _Repository:
    def __init__(self, *, run_status: str = "running") -> None:
        self.calls: list[tuple] = []
        self.run_status = run_status

    def finish_capability_execution(self, run_id, execution_key, *, result_payload, error, state_changed):
        self.calls.append(("finish_execution", execution_key, error, state_changed))

    def finish_evidence_query(self, run_id, revision_id, execution_key, *, actual_sources, actual_extracts, failed):
        self.calls.append(("finish_evidence", revision_id, execution_key, actual_sources, actual_extracts, failed))

    def mark_capability_waiting_for_approval(self, run_id, execution_key):
        self.calls.append(("waiting", execution_key))

    def add_approval(self, approval):
        self.calls.append(("approval", approval.request_payload["execution_key"]))

    def get_run(self, run_id):
        return SimpleNamespace(status=self.run_status, revision=7)

    def update_state(self, run_id, *, expected_revision, status):
        self.calls.append(("run_state", expected_revision, status))


def test_an_evidence_query_is_finished_with_the_execution_and_counts_what_it_used() -> None:
    repository = _Repository()
    call = CapabilityCall.open("run-1", "research.web_search", "agent:run-1:k", task_revision_id="rev-1")
    payload = {"output": {"items": [{}, {}], "diagnostics": {"extracted_pages": 1}}}

    call.settle(repository, result_payload=payload, error=None, state_changed=False)

    assert call.execution_key.startswith("agent:run-1:k:evidence-revision:")
    assert repository.calls == [
        ("finish_execution", call.execution_key, None, False),
        ("finish_evidence", "rev-1", call.execution_key, 2, 1, False),
    ]


def test_a_refused_evidence_query_is_finished_as_failed_and_used_nothing() -> None:
    repository = _Repository()
    call = CapabilityCall.open("run-1", "research.web_search", "agent:run-1:k", task_revision_id="rev-1")

    call.settle(repository, result_payload={"error": "tool_disabled", "output": {"items": [{}]}}, error="tool_disabled")

    assert repository.calls[-1] == ("finish_evidence", "rev-1", call.execution_key, 0, 0, True)


def test_a_call_that_is_not_an_evidence_query_holds_no_query() -> None:
    repository = _Repository()
    call = CapabilityCall.open("run-1", "home.set_state", "agent:run-1:k", task_revision_id="rev-1")

    call.settle(repository, result_payload={}, error=None, state_changed=True)

    assert call.execution_key == "agent:run-1:k"
    assert repository.calls == [("finish_execution", "agent:run-1:k", None, True)]


def test_parking_records_one_approval_and_makes_the_run_wait() -> None:
    repository = _Repository()
    call = CapabilityCall.open("run-1", "home.set_state", "agent:run-1:k", task_revision_id=None)

    approval = call.park_for_approval(repository, None, request_input={"target": "Desk"})

    assert approval.request_payload == {"input": {"target": "Desk"}, "proposal_id": "agent:run-1:k",
                                        "execution_key": "agent:run-1:k"}
    assert repository.calls == [("waiting", "agent:run-1:k"), ("approval", "agent:run-1:k"),
                                ("run_state", 7, "waiting_for_approval")]


def test_a_call_already_waiting_on_its_approval_adds_no_second_one() -> None:
    repository = _Repository(run_status="waiting_for_approval")
    call = CapabilityCall.open("run-1", "home.set_state", "agent:run-1:k", task_revision_id=None)
    pending = call.park_for_approval(repository, None, request_input={})
    repository.calls.clear()

    assert call.park_for_approval(repository, pending, request_input={}) is pending
    assert repository.calls == [("waiting", "agent:run-1:k")]


def test_only_the_call_finishes_executions_and_evidence_queries() -> None:
    finishing = re.compile(r"\.(?:finish_capability_execution|finish_evidence_query)\(")
    callers = {path.name for path in RUNTIME.glob("*.py") if finishing.search(path.read_text(encoding="utf-8"))}
    # The repository and its implementing module define them; the call is the one place that uses them.
    assert callers == {"capability_call.py", "repository.py"}
